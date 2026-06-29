import frappe
from frappe import _
import whisper
import tempfile
import os
import base64

_model = None


def get_model():
    """Load Whisper model once and reuse across requests."""
    global _model
    if _model is None:
        _model = whisper.load_model("base")  # change to "small" for better accuracy
    return _model


@frappe.whitelist()
def transcribe_audio():
    """
    Accepts an uploaded audio file (from the mic recording in aiko_chat.js),
    transcribes it with Whisper, returns the text.
    """
    if "audio" not in frappe.request.files:
        frappe.throw(_("No audio file received"))

    audio_file = frappe.request.files["audio"]

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        audio_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        model = get_model()
        result = model.transcribe(tmp_path, fp16=False)
        text = result.get("text", "").strip()
        return {"success": True, "text": text}
    except Exception as e:
        frappe.log_error(f"Whisper transcription failed: {e}", "AIKO Voice Transcribe")
        return {"success": False, "error": str(e)}
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@frappe.whitelist()
def transcribe_audio_b64():
    """
    Accepts base64-encoded audio (avoids 417 errors from multipart FormData uploads).
    """
    audio_base64 = frappe.local.form_dict.get("audio_base64")
    if not audio_base64:
        frappe.throw(_("No audio data received"))

    audio_bytes = base64.b64decode(audio_base64)

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = get_model()
        result = model.transcribe(tmp_path, fp16=False)
        return {"success": True, "text": result.get("text", "").strip()}
    except Exception as e:
        frappe.log_error(f"Whisper transcription failed: {e}", "AIKO Voice Transcribe")
        return {"success": False, "error": str(e)}
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)