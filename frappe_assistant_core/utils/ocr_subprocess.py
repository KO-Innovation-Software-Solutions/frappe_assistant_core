# Frappe Assistant Core - AI Assistant integration for Frappe Framework
# Copyright (C) 2025 Paul Clinton
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Isolated PaddleOCR worker.

extract_file_content.py's `_perform_paddle_ocr()` spawns this module as a
separate process:

    python -m frappe_assistant_core.utils.ocr_subprocess

so that a PaddleOCR hang, crash, or out-of-memory event kills only this
child process rather than the Frappe web worker.

Contract
--------
stdin  (one JSON object):
    {
        "file_path": "/tmp/fac_ocr_xxx.png",  # or .pdf
        "file_type": "image" | "pdf",
        "language": "en",                     # short code or raw PaddleOCR lang
        "max_pages": 50,
        "max_memory_mb": 2048
    }

stdout (one JSON object, success case):
    {"success": true, "content": "<full extracted text>", "pages": 3, ...}

stdout (one JSON object, failure case):
    {"success": false, "error": "<message>"}

The parent process only reads the single JSON line written to stdout and
checks the process exit code / stderr text on failure, so this module must
never print anything else to stdout and should always exit 0 on success,
non-zero on failure.
"""

import json
import sys


# Short codes used in Assistant Core Settings / the extract_file_content
# `language` argument, mapped to the identifiers PaddleOCR's PP-OCR models
# expect. Anything not listed here is passed straight through, so a raw
# PaddleOCR lang code (e.g. "chinese_cht") still works.
LANG_MAP = {
    "en": "en",
    "english": "en",
    "fr": "french",
    "french": "french",
    "de": "german",
    "german": "german",
    "es": "es",
    "spanish": "es",
    "pt": "pt",
    "portuguese": "pt",
    "it": "it",
    "italian": "it",
    "nl": "nl",
    "dutch": "nl",
    "ch": "ch",
    "chinese": "ch",
    "cht": "chinese_cht",
    "ko": "korean",
    "korean": "korean",
    "ja": "japan",
    "japan": "japan",
    "japanese": "japan",
    "ar": "arabic",
    "arabic": "arabic",
    "hi": "devanagari",
    "ru": "cyrillic",
    "ta": "ta",
    "te": "te",
    "ka": "ka",
}


def _set_memory_limit(max_memory_mb: int) -> None:
    """Best-effort address-space cap (Linux only) so a runaway OCR call
    raises MemoryError in *this* process instead of exhausting the host."""
    try:
        import resource

        limit_bytes = max(int(max_memory_mb or 2048), 256) * 1024 * 1024
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        new_hard = hard if hard != resource.RLIM_INFINITY else limit_bytes
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, new_hard))
    except Exception:
        # Not Linux, or insufficient privilege to lower the limit — proceed
        # without a hard cap; the parent's timeout is still in effect.
        pass


def _build_engine(lang: str):
    """Construct a PaddleOCR engine, tolerating API differences across
    paddleocr versions (e.g. `show_log` was removed in newer releases)."""
    from paddleocr import PaddleOCR

    try:
        return PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
    except TypeError:
        return PaddleOCR(use_angle_cls=True, lang=lang)


def _run_ocr(engine, image_array):
    """Call engine.ocr(), tolerating the `cls` kwarg being removed/renamed
    across paddleocr versions."""
    try:
        return engine.ocr(image_array, cls=True)
    except TypeError:
        return engine.ocr(image_array)


def _lines_from_result(result) -> list:
    """Flatten PaddleOCR's nested result structure into reading-order text
    lines. PaddleOCR returns `[[ [box, (text, score)], ... ]]` per image —
    one outer list per input image, one inner entry per detected line,
    already sorted top-to-bottom by the engine."""
    lines = []
    for page_result in result or []:
        for detection in page_result or []:
            try:
                text = detection[1][0]
            except (IndexError, TypeError):
                continue
            if text and text.strip():
                lines.append(text.strip())
    return lines


def _ocr_pil_image(engine, pil_image) -> str:
    import numpy as np

    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")
    result = _run_ocr(engine, np.array(pil_image))
    return "\n".join(_lines_from_result(result))


def _ocr_image_file(engine, file_path: str) -> str:
    from PIL import Image

    with Image.open(file_path) as image:
        return _ocr_pil_image(engine, image)


def _ocr_pdf_file(engine, file_path: str, max_pages: int) -> dict:
    """Render each PDF page to an image with PyMuPDF, then OCR each page.
    Used for scanned PDFs that have no extractable text layer."""
    import fitz  # PyMuPDF
    from PIL import Image

    doc = fitz.open(file_path)
    try:
        num_pages = min(len(doc), max(int(max_pages or 50), 1))
        page_texts = []

        for page_num in range(num_pages):
            page = doc[page_num]
            # 200 DPI is a good accuracy/speed/memory tradeoff for OCR.
            pix = page.get_pixmap(dpi=200)
            pil_image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            page_text = _ocr_pil_image(engine, pil_image)
            if page_text.strip():
                page_texts.append(f"--- Page {page_num + 1} ---\n{page_text}")

        return {
            "content": "\n\n".join(page_texts),
            "pages": num_pages,
            "ocr_pages_with_text": len(page_texts),
        }
    finally:
        doc.close()


def _respond(payload: dict, exit_code: int = 0) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    sys.exit(exit_code)


def main() -> None:
    raw_request = sys.stdin.read()
    try:
        request = json.loads(raw_request)
    except json.JSONDecodeError as e:
        _respond({"success": False, "error": f"Invalid request JSON: {e}"}, 1)
        return

    file_path = request.get("file_path")
    file_type = request.get("file_type", "image")
    language = request.get("language", "en")
    max_pages = request.get("max_pages", 50)
    max_memory_mb = request.get("max_memory_mb", 2048)

    if not file_path:
        _respond({"success": False, "error": "Missing file_path in OCR request"}, 1)
        return

    _set_memory_limit(max_memory_mb)

    lang = LANG_MAP.get(str(language).lower().strip(), language)

    try:
        engine = _build_engine(lang)
    except Exception as e:
        _respond({"success": False, "error": f"Failed to initialise PaddleOCR (lang='{lang}'): {e}"}, 1)
        return

    try:
        if file_type == "pdf":
            result = _ocr_pdf_file(engine, file_path, max_pages)
            content = result["content"]
            response = {
                "success": True,
                "content": content,
                "pages": result["pages"],
                "ocr_pages_with_text": result["ocr_pages_with_text"],
            }
            if not content.strip():
                response["message"] = "No text detected in PDF"
        else:
            content = _ocr_image_file(engine, file_path)
            response = {"success": True, "content": content}
            if not content.strip():
                response["message"] = "No text detected in image"

        _respond(response, 0)

    except MemoryError:
        # Matches the "Cannot allocate memory" pattern the parent process
        # greps stderr for, but we also surface it cleanly via stdout JSON.
        sys.stderr.write("MemoryError: Cannot allocate memory during PaddleOCR run\n")
        _respond({"success": False, "error": "PaddleOCR ran out of memory while processing this file"}, 1)
    except Exception as e:
        _respond({"success": False, "error": f"PaddleOCR processing failed: {e}"}, 1)


if __name__ == "__main__":
    main()