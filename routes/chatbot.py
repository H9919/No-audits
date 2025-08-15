# routes/chatbot.py — original interface restored + sticky session + fixed replies
from flask import Blueprint, request, jsonify, render_template, current_app as app, make_response
from pathlib import Path
import time, json, logging, re, secrets

from services.ehs_chatbot import SmartEHSChatbot, SmartIntentClassifier, five_whys_manager
from services.capa_manager import CAPAManager
from utils.uploads import is_allowed, save_upload

# Keep inputs as typed (avoid collapsing everything to a keyword)
NORMALIZE_INPUTS = False
COOKIE_NAME = "ehs_uid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

chatbot_bp = Blueprint("chatbot", __name__)

_quick = SmartIntentClassifier()
_CHATBOT = None

def get_chatbot() -> SmartEHSChatbot:
    global _CHATBOT
    if _CHATBOT is None:
        _CHATBOT = SmartEHSChatbot(logger=app.logger)
        app.logger.info("SmartEHSChatbot initialized")
    return _CHATBOT

def _normalize_intent_text(t: str) -> str:
    """Optional soft normalization. Left off by default."""
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

def _get_or_create_uid() -> str:
    uid = request.cookies.get(COOKIE_NAME)
    if not uid:
        uid = secrets.token_hex(12)
    return uid

def _attach_uid_cookie(resp, uid: str):
    try:
        resp.set_cookie(COOKIE_NAME, uid, max_age=COOKIE_MAX_AGE, samesite="Lax", httponly=False)
    except Exception:
        pass

def _fmt_bot(result):
    """
    Normalize bot outputs for the UI.
    Prefers 'reply'; bubbles next_expected/done/result if present.
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

# ---------------- UI (restore original chat page) ----------------
@chatbot_bp.route("/chat", methods=["GET", "POST"])
def chat_interface():
    # GET: show the real chat UI, not the placeholder dashboard
    if request.method == "GET":
        uid = _get_or_create_uid()
        resp = make_response(render_template("chatbot.html"))
        _attach_uid_cookie(resp, uid)
        return resp

    # POST: process chat message
    t0 = time.monotonic()
    payload = request.get_json(silent=True) or {}
    raw_msg = (request.form.get("message") or payload.get("message") or "").strip()
    user_message = _normalize_intent_text(raw_msg)
    user_id = (request.form.get("user_id") or payload.get("user_id") or _get_or_create_uid()).strip()
    uploaded_file = request.files.get("file") or request.files.get("upload")

    if not user_message and not uploaded_file:
        resp = jsonify({"message": "Please type a message or attach a file.", "type": "error"})
        _attach_uid_cookie(resp, user_id)
        return resp, 400

    # Lightweight intent for telemetry only
    try:
        intent, conf = _quick.classify_intent(user_message or raw_msg)
    except Exception:
        intent, conf = None, 0.0

    # File ack path
    if uploaded_file:
        if is_allowed(uploaded_file.filename, getattr(uploaded_file, "mimetype", "")):
            try:
                save_upload(uploaded_file, Path("data/tmp"))
            except Exception as e:
                app.logger.warning("file save failed: %s", e)
            app.logger.info("chat:fast_file %.3fs", time.monotonic() - t0)
            resp = jsonify({
                "message": f"📎 Received your file: {uploaded_file.filename}. What would you like me to do with it?",
                "type": "file_ack",
                "intent": intent,
                "confidence": conf
            })
            _attach_uid_cookie(resp, user_id)
            return resp
        resp = jsonify({
            "message": "This file type is not allowed. Please upload PDF/PNG/JPG/TXT.",
            "type": "error"
        })
        _attach_uid_cookie(resp, user_id)
        return resp, 400

    # Delegate to stateful bot
    bot = get_chatbot()
    t1 = time.monotonic()
    try:
        result = bot.process_message(user_message, user_id=user_id, context={"source": "web"})
    except Exception as e:
        app.logger.exception("chat:bot_crash")
        resp = jsonify({"message": f"Sorry—something went wrong handling that. ({e})", "type": "error"})
        _attach_uid_cookie(resp, user_id)
        return resp, 500

    app.logger.info("chat:smart %.3fs (total %.3fs)", time.monotonic() - t1, time.monotonic() - t0)

    # Surface the bot's real reply to your UI
    if isinstance(result, dict):
        if "message" not in result:
            if "reply" in result and isinstance(result["reply"], str) and result["reply"].strip():
                result["message"] = result["reply"]
            else:
                result["message"] = "OK"
        result.setdefault("type", "message")
        result.setdefault("quick_intent", intent)
        result.setdefault("quick_confidence", conf)
        resp = jsonify(result)
        _attach_uid_cookie(resp, user_id)
        return resp

    resp = jsonify({
        "message": str(result),
        "type": "message",
        "quick_intent": intent,
        "quick_confidence": conf
    })
    _attach_uid_cookie(resp, user_id)
    return resp

# ---------------- 5 Whys ----------------
@chatbot_bp.post("/five_whys/start")
@chatbot_bp.post("/chat/five_whys/start")
def five_whys_start():
    problem = (request.form.get("problem") or (request.json.get("problem") if request.is_json else "") or "").strip()
    user_id = (request.form.get("user_id") or _get_or_create_uid()).strip()
    if not problem:
        resp = jsonify({"ok": False, "error": "Please provide a problem statement."})
        _attach_uid_cookie(resp, user_id)
        return resp, 400
    five_whys_manager.start(user_id, problem)
    resp = jsonify({"ok": True, "step": 1, "prompt": "Why 1?", "problem": problem})
    _attach_uid_cookie(resp, user_id)
    return resp

@chatbot_bp.post("/five_whys/answer")
@chatbot_bp.post("/chat/five_whys/answer")
def five_whys_answer():
    answer = (request.form.get("answer") or (request.json.get("answer") if request.is_json else "") or "").strip()
    user_id = (request.form.get("user_id") or _get_or_create_uid()).strip()
    incident_id = (request.form.get("incident_id") or "").strip()
    force_complete = (request.form.get("complete") or "").lower() == "true"

    sess = five_whys_manager.answer(user_id, answer)
    if not sess:
        resp = jsonify({"ok": False, "error": "No active 5-Whys session. Start first."})
        _attach_uid_cookie(resp, user_id)
        return resp, 400

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
            pass
        resp = jsonify({"ok": True, "complete": True, "whys": chain, "message": "5 Whys completed."})
        _attach_uid_cookie(resp, user_id)
        return resp
    next_step = len(sess.get("whys", [])) + 1
    resp = jsonify({"ok": True, "complete": False, "prompt": f"Why {next_step}?", "progress": len(sess['whys'])})
    _attach_uid_cookie(resp, user_id)
    return resp

# ---------------- CAPA suggestion ----------------
@chatbot_bp.post("/capa/suggest")
@chatbot_bp.post("/chat/capa/suggest")
def capa_suggest():
    desc = (request.form.get("description") or (request.json.get("description") if request.is_json else "") or "").strip()
    if not desc:
        return jsonify({"ok": False, "error": "Please provide a short description."}), 400
    mgr = CAPAManager()
    res = mgr.suggest_corrective_actions(desc)
    out = {"ok": True}
    out.update(res)
    return jsonify(out)

# ---------------- Session reset ----------------
@chatbot_bp.post("/chat/reset")
def chat_reset():
    global _CHATBOT
    _CHATBOT = None
    resp = jsonify({"ok": True, "message": "Session reset."})
    _attach_uid_cookie(resp, _get_or_create_uid())
    return resp

# Aliases (in case your loader expects them)
bp = chatbot_bp
chatbot = chatbot_bp
blueprint = chatbot_bp
