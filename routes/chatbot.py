# routes/chatbot.py — full-featured, fixed endpoints, compatible with UI
from flask import Blueprint, request, jsonify, render_template, current_app as app
from pathlib import Path
import time, json, logging, re

from services.ehs_chatbot import SmartEHSChatbot, SmartIntentClassifier, five_whys_manager
from services.capa_manager import CAPAManager
from utils.uploads import is_allowed, save_upload

# If you previously had NORMALIZE_INPUTS, keep it False to avoid collapsing user text.
NORMALIZE_INPUTS = False

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/chatbot")

# -------------------------
# Singleton bot (very light)
# -------------------------
_CHATBOT = None
def get_chatbot():
    global _CHATBOT
    if _CHATBOT is None:
        _CHATBOT = SmartEHSChatbot(logger=app.logger)
    return _CHATBOT

_INTENTS = SmartIntentClassifier()

# -------------------------
# Helpers
# -------------------------
def _normalize_intent_text(t: str) -> str:
    if not NORMALIZE_INPUTS:
        return t or ""
    s = (t or "").strip().lower()
    s = re.sub(r"[^\w\s/]+$", "", s)
    if re.search(r"\breport( an)? incident\b|\bincident report\b|\bstart .*incident\b", s):
        return "Report incident"
    if re.search(r"\bsafety concern\b|\bnear miss\b|\bunsafe\b", s):
        return "Safety concern"
    if re.search(r"\b(find )?sds\b|\bsafety data sheet\b", s):
        return "Find SDS"
    return t

def _user_id_from_req() -> str:
    return f"{request.remote_addr}-{(request.headers.get('User-Agent','') or '')[:24]}"

def _fmt_bot(result):
    """
    Normalize bot outputs for the UI.
    Prefers 'reply', bubbles next_expected/done/result if present.
    """
    out = {"type": "bot", "message": "", "done": False}
    if isinstance(result, dict):
        out["message"] = result.get("reply") or result.get("message") or ""
        if "next_expected" in result:
            out["next_expected"] = result["next_expected"]
        if "done" in result:
            out["done"] = bool(result["done"])
        if result.get("done") and "result" in result:
            out["result"] = result["result"]
    else:
        out["message"] = str(result)
    if not out["message"]:
        out["message"] = "Sorry—I'm not sure I caught that. Could you rephrase?"
    return out

# ------------------------------------------------
# UI route (optional): render the chatbot template
# ------------------------------------------------
@chatbot_bp.get("/")
def chat_ui():
    return render_template("chatbot.html")

# --------------------------------------
# Main chat endpoint used by the frontend
# --------------------------------------
@chatbot_bp.post("/chat")
def chat():
    """
    Accepts:
      - 'message' (text)
      - optional file 'upload'
      - optional 'user_id' (else derived from IP+UA)
    Returns JSON:
      { type: 'bot', message: str, next_expected?: str, done: bool, result?: {...} }
    """
    t0 = time.monotonic()
    data = request.form or request.json or {}
    user_message = (data.get("message") or "").strip()
    user_id = (data.get("user_id") or _user_id_from_req())

    if not user_message and "upload" not in request.files:
        return jsonify({"type": "bot", "message": "Please type a message or attach a file."}), 400

    # Optional upload handling — convert to a note the bot can see
    if "upload" in request.files and request.files["upload"].filename:
        f = request.files["upload"]
        if not is_allowed(f.filename):
            return jsonify({"type":"bot","message":"This file type is not allowed. Please upload PDF/PNG/JPG/TXT."}), 400
        saved = save_upload(f)
        user_message = (user_message + f"\n\n[Attached file: {saved.name}]").strip()

    # Light normalization (if enabled)
    user_message_norm = _normalize_intent_text(user_message)

    bot = get_chatbot()

    # QUICK INTENTS → give a useful first prompt (not "OK")
    intent = _INTENTS.quick_intent(user_message_norm)
    if intent == "Report incident":
        # Start or continue the incident flow
        result = bot.process_message("", user_id=user_id, context={"source": "web"})
        # If process_message started a new flow, it'll return the opening prompt.
        # If a flow already exists, it will continue.
        if not result or not isinstance(result, dict) or not result.get("reply"):
            # Fallback: explicitly start
            result = bot.start_incident(user_id)
        return jsonify(_fmt_bot(result)), 200

    elif intent == "Safety concern":
        # Use the same incident flow; the event_type question will be asked.
        result = bot.start_incident(user_id)
        return jsonify(_fmt_bot(result)), 200

    elif intent == "Find SDS":
        # Hand off to SDS flow in your UI
        return jsonify({
            "type": "bot",
            "message": "Sure—what product or chemical are you looking for? You can also open the SDS page from the menu.",
            "next_expected": "sds_query",
            "done": False
        }), 200

    # DEFAULT: normal chat handling with the full bot reply
    try:
        result = bot.process_message(user_message_norm or user_message, user_id=user_id, context={"source": "web"})
    except Exception as e:
        app.logger.exception("chat:bot_crash")
        return jsonify({"type": "bot", "message": f"Sorry—something went wrong handling that. ({e})"}), 500

    app.logger.info("chat:smart %.3fs", time.monotonic() - t0)
    return jsonify(_fmt_bot(result)), 200

# ---------------------------
# Start incident explicitly
# ---------------------------
@chatbot_bp.post("/chat/start")
def chat_start():
    user_id = (request.form.get("user_id") if request.form else None) or _user_id_from_req()
    bot = get_chatbot()
    res = bot.start_incident(user_id)
    return jsonify(_fmt_bot(res)), 200

# ---------------------------
# 5-Whys helper endpoints
# ---------------------------
@chatbot_bp.post("/why/start")
def why_start():
    data = request.form or request.json or {}
    user_id = (data.get("user_id") or _user_id_from_req())
    problem = (data.get("problem") or "").strip()
    if not problem:
        return jsonify({"ok": False, "error": "Please provide a short problem statement."}), 400
    five_whys_manager.start(user_id, problem)
    return jsonify({"ok": True, "step": 1, "prompt": "Why 1?", "problem": problem})

@chatbot_bp.post("/why/answer")
def why_answer():
    data = request.form or request.json or {}
    user_id = (data.get("user_id") or _user_id_from_req())
    answer = (data.get("answer") or "").strip()
    force_complete = bool(data.get("force_complete"))
    if not answer and not force_complete:
        return jsonify({"ok": False, "error": "Please provide an answer."}), 400
    sess = five_whys_manager.answer(user_id, answer) if answer else five_whys_manager.get(user_id)
    if not sess:
        return jsonify({"ok": False, "error": "No active 5-Whys session. Start first."}), 400
    done = five_whys_manager.is_complete(user_id) or force_complete
    if done:
        chain = sess["whys"]
        return jsonify({"ok": True, "complete": True, "whys": chain})
    next_step = len(sess["whys"]) + 1
    return jsonify({"ok": True, "complete": False, "prompt": f"Why {next_step}?", "progress": len(sess["whys"])})

# ---------------------------
# CAPA suggestion helper
# ---------------------------
@chatbot_bp.post("/suggest_capa")
def suggest_capa():
    data = request.form or request.json or {}
    desc = (data.get("description") or "").strip()
    if not desc:
        return jsonify({"ok": False, "error": "Please provide a short description."}), 400
    mgr = CAPAManager()
    res = mgr.suggest_corrective_actions(desc)
    out = {"ok": True}
    out.update(res)
    return jsonify(out)

# ---------------------------
# Session reset (dev helper)
# ---------------------------
@chatbot_bp.post("/chat/reset")
def chat_reset():
    global _CHATBOT
    _CHATBOT = None
    return jsonify({"ok": True, "message": "Session reset."})

# ---------------------------
# Optional: quick health
# ---------------------------
@chatbot_bp.get("/health")
def chat_health():
    return jsonify({"ok": True, "service": "chatbot", "ts": time.time()})
