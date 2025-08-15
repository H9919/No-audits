# routes/chatbot.py — full-featured, fixed endpoints, compatible with your original UI
from flask import Blueprint, request, jsonify, render_template, current_app as app
from pathlib import Path
import time, json, logging, re

from services.ehs_chatbot import SmartEHSChatbot, SmartIntentClassifier, five_whys_manager
from services.capa_manager import CAPAManager
from utils.uploads import is_allowed, save_upload

# Toggle this to quickly test with/without input normalization (kept from your original)
NORMALIZE_INPUTS = True

def _normalize_intent_text(t: str) -> str:
    s = (t or "").strip().lower()
    s = re.sub(r"[^\w\s/]+$", "", s)
    if re.search(r"\breport( an)? incident\b", s) or re.search(r"\bincident report\b", s) or re.search(r"\bstart .*incident\b", s):
        return "Report incident"
    if re.search(r"\bsafety concern\b|\bnear miss\b|\bunsafe\b", s):
        return "Safety concern"
    if re.search(r"\b(find )?sds\b|\bsafety data sheet\b", s):
        return "Find SDS"
    if re.search(r"\brisk assessment\b|\berc\b|\blikelihood\b", s):
        return "Risk assessment"
    if re.search(r"\burgent\b|\bpriority\b|\boverdue\b", s):
        return "What's urgent?"
    if re.search(r"\btour\b|\bgetting started\b|\bguide\b|\bonboard\b", s):
        return "Help with this page"
    return t or ""

chatbot_bp = Blueprint("chatbot", __name__)

_quick = SmartIntentClassifier()
_CHATBOT = None

def get_chatbot() -> SmartEHSChatbot:
    global _CHATBOT
    if _CHATBOT is None:
        _CHATBOT = SmartEHSChatbot()
        app.logger.info("SmartEHSChatbot initialized")
    return _CHATBOT

@chatbot_bp.route("/chat", methods=["GET", "POST"])
def chat_interface():
    # GET: render chat-first dashboard (same template as your original)
    if request.method == "GET":
        return render_template("enhanced_dashboard.html")

    # POST: process chat message
    t0 = time.monotonic()
    payload = request.get_json(silent=True) or {}
    raw_msg = (request.form.get("message") or payload.get("message") or "").strip()
    user_message = _normalize_intent_text(raw_msg) if NORMALIZE_INPUTS else raw_msg
    user_id = (request.form.get("user_id") or "main_chat_user").strip()
    uploaded_file = request.files.get("file")

    if not user_message and not uploaded_file:
        return jsonify({"message": "Please type a message or attach a file.", "type": "error"}), 400

    # Lightweight intent for telemetry/metadata only (do NOT branch on this)
    try:
        intent, conf = _quick.classify_intent(user_message or raw_msg)
    except Exception:
        intent, conf = None, 0.0

    # File ack path (early return just for uploads)
    if uploaded_file:
        if is_allowed(uploaded_file.filename, uploaded_file.mimetype):
            try:
                save_upload(uploaded_file, Path("data/tmp"))
            except Exception as e:
                app.logger.warning("file save failed: %s", e)
            app.logger.info("chat:fast_file %.3fs", time.monotonic() - t0)
            return jsonify({
                "message": f"📎 Received your file: {uploaded_file.filename}. What would you like me to do with it?",
                "type": "file_ack",
                "intent": intent,
                "confidence": conf
            })
        return jsonify({
            "message": "This file type is not allowed. Please upload PDF/PNG/JPG/TXT.",
            "type": "error"
        }), 400

    # ✅ Always delegate conversational logic to the stateful bot
    bot = get_chatbot()
    t1 = time.monotonic()
    try:
        result = bot.process_message(user_message, user_id=user_id, context={"source": "web"})
    except Exception as e:
        app.logger.exception("chat:bot_crash")
        return jsonify({"message": f"Sorry—something went wrong handling that. ({e})", "type": "error"}), 500

    app.logger.info("chat:smart %.3fs (total %.3fs)", time.monotonic() - t1, time.monotonic() - t0)

    # Normalize response and attach quick-intent telemetry for the UI (non-breaking)
    if isinstance(result, dict):
        # 🔧 KEY FIX: surface the bot's 'reply' as 'message' so your UI shows real prompts instead of "OK"
        if "message" not in result:
            if "reply" in result and isinstance(result["reply"], str) and result["reply"].strip():
                result["message"] = result["reply"]
            else:
                result["message"] = "OK"

        result.setdefault("type", "message")
        # Do not overwrite bot's own intent fields if present
        if "quick_intent" not in result:
            result["quick_intent"] = intent
        if "quick_confidence" not in result:
            result["quick_confidence"] = conf
        return jsonify(result)

    # If the bot returned a plain string
    return jsonify({
        "message": str(result),
        "type": "message",
        "quick_intent": intent,
        "quick_confidence": conf
    })

# ---------- 5 Whys endpoints (unchanged) ----------

@chatbot_bp.post("/five_whys/start")
@chatbot_bp.post("/chat/five_whys/start")
def five_whys_start():
    problem = (request.form.get("problem") or "").strip()
    user_id = (request.form.get("user_id") or "main_chat_user").strip()
    if not problem:
        return jsonify({"ok": False, "error": "Please provide a problem statement."}), 400
    five_whys_manager.start(user_id, problem)
    return jsonify({"ok": True, "step": 1, "prompt": "Why 1?", "problem": problem})

@chatbot_bp.post("/five_whys/answer")
@chatbot_bp.post("/chat/five_whys/answer")
def five_whys_answer():
    answer = (request.form.get("answer") or "").strip()
    user_id = (request.form.get("user_id") or "main_chat_user").strip()
    incident_id = (request.form.get("incident_id") or "").strip()
    force_complete = (request.form.get("complete") or "").lower() == "true"

    sess = five_whys_manager.answer(user_id, answer)
    if not sess:
        return jsonify({"ok": False, "error": "No active 5-Whys session. Start first."}), 400

    done = five_whys_manager.is_complete(user_id) or force_complete
    if done:
        chain = sess["whys"]
        try:
            DATA_DIR = Path("data")
            INCIDENTS_JSON = DATA_DIR / "incidents.json"
            if incident_id and INCIDENTS_JSON.exists():
                items = json.loads(INCIDENTS_JSON.read_text())
                if incident_id in items:
                    items[incident_id]["root_cause_whys"] = chain
                    INCIDENTS_JSON.write_text(json.dumps(items, indent=2))
        except Exception:
            # Non-fatal; just don't persist
            pass
        return jsonify({"ok": True, "complete": True, "whys": chain, "message": "5 Whys completed."})
    else:
        # Your original used sess["step"] — keep compatible behavior
        next_step = (sess.get("step") or len(sess.get("whys", []))) + 1
        return jsonify({"ok": True, "complete": False, "prompt": f"Why {next_step}?", "progress": len(sess['whys'])})

# ---------- CAPA suggestions (unchanged) ----------

@chatbot_bp.post("/capa/suggest")
@chatbot_bp.post("/chat/capa/suggest")
def capa_suggest():
    desc = (request.form.get("description") or "").strip()
    if not desc:
        return jsonify({"ok": False, "error": "Please provide a short description."}), 400
    mgr = CAPAManager()
    res = mgr.suggest_corrective_actions(desc)
    out = {"ok": True}
    out.update(res)
    return jsonify(out)

# ---------- Session reset (unchanged) ----------

@chatbot_bp.post("/chat/reset")
def chat_reset():
    global _CHATBOT
    _CHATBOT = None
    return jsonify({"ok": True, "message": "Session reset."})
