import frappe
import requests
import os

@frappe.whitelist()
def synthesize_speech(text):
    if not text:
        frappe.throw("No text provided")

    text = text.strip()

    coqui_service_url = frappe.conf.get("tts_service_url")
    if not coqui_service_url:
        frappe.log_error("tts_service_url not set in site config", "TTS Service Error")
        return {"error": "TTS service URL is not configured"}

    try:
        response = requests.post(
            f"{coqui_service_url}/synthesize",
            json={"text": text},
            timeout=60
        )
        response.raise_for_status()

        filename = response.json().get("filename")
        if not filename:
            frappe.log_error("TTS service returned no filename", "TTS Service Error")
            return {"error": "TTS service returned no filename"}

        output_dir = frappe.get_site_path("public", "files", "tts_audio")
        os.makedirs(output_dir, exist_ok=True)

        dest_path = os.path.join(output_dir, filename)

        audio_response = requests.get(
            f"{coqui_service_url}/audio/{filename}",
            timeout=30
        )
        audio_response.raise_for_status()

        with open(dest_path, "wb") as f:
            f.write(audio_response.content)

        return {"audio_url": f"/files/tts_audio/{filename}"}

    except requests.exceptions.Timeout:
        frappe.log_error("TTS service timed out", "TTS Service Error")
        return {"error": "TTS service timed out. The text may be too long."}

    except requests.exceptions.ConnectionError:
        frappe.log_error("Cannot connect to TTS service", "TTS Service Error")
        return {"error": "TTS service is not running. Please start the Coqui server."}

    except Exception as e:
        frappe.log_error(str(e), "TTS Service Error")
        return {"error": "TTS service unavailable"}