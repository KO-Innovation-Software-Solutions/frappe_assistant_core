# frappe_assistant_core/aiko/providers/whisper.py
import frappe
from faster_whisper import WhisperModel

_model_cache = {}

def get_model(model_size: str = "medium", device: str = "auto", compute_type: str = "default"):
    cache_key = f"{model_size}:{device}:{compute_type}"
    if cache_key not in _model_cache:
        frappe.logger("aiko").info(f"Loading faster-whisper model: {cache_key}")
        _model_cache[cache_key] = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type
        )
    return _model_cache[cache_key]


def transcribe_audio(file_path: str, model_size: str = "medium", language: str = None) -> dict:
    model = get_model(model_size=model_size)

    segments, info = model.transcribe(
        file_path,
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    full_text = " ".join(segment.text.strip() for segment in segments)

    return {
        "text": full_text.strip(),
        "language": info.language,
        "language_probability": info.language_probability,
    }