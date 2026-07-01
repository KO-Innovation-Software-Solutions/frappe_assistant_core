import base64
import os
import tempfile

import frappe
from frappe import _

from frappe_assistant_core.aiko.providers.whisper import transcribe_audio


@frappe.whitelist()
def transcribe(file_url: str = None, model_size: str = "medium", language: str = None):
    """
    Transcribe an uploaded audio file already saved in Frappe (File doctype),
    or accept a fresh upload via request.files.
    """
    if not file_url and "file" in frappe.request.files:
        uploaded_file = frappe.request.files["file"]
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_file:
            tmp_file.write(uploaded_file.stream.read())
            file_path = tmp_file.name
    elif file_url:
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        file_path = file_doc.get_full_path()
    else:
        frappe.throw(_("Provide either file_url or a multipart file upload"))

    try:
        result = transcribe_audio(file_path, model_size=model_size, language=language)
        return {
            "success": True,
            "text": result["text"],
            "language": result["language"],
            "confidence": result["language_probability"],
        }
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AIKO Voice Transcription Failed")
        frappe.throw(_("Transcription failed. Check error log."))


@frappe.whitelist()
def transcribe_base64(audio_base64: str, model_size: str = "medium", language: str = None):
    """
    Transcribe audio sent as a base64 string (avoids multipart upload issues
    with Werkzeug dev server on local setups).
    """
    try:
        audio_bytes = base64.b64decode(audio_base64)
    except Exception:
        frappe.throw(_("Invalid base64 audio data"))

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_file:
        tmp_file.write(audio_bytes)
        tmp_path = tmp_file.name

    try:
        result = transcribe_audio(tmp_path, model_size=model_size, language=language)
        return {
            "success": True,
            "text": result["text"],
            "language": result["language"],
            "confidence": result["language_probability"],
        }
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AIKO Voice Transcription Failed")
        frappe.throw(_("Transcription failed. Check error log."))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)



