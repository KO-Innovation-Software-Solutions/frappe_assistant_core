from __future__ import annotations

import ast
import html as _html
import json as _json
import re
from collections import defaultdict
from typing import Optional

import frappe


MAX_EXTRACTED_CHARS = 16_000


def _aiko_log(title: str, message: str) -> None:
    """Write to Frappe Error Log only when AIKO_DEBUG is enabled.

    No-op in production; enable with:  bench set-config -g AIKO_DEBUG 1
    """
    try:
        if frappe.conf.get("AIKO_DEBUG"):
            frappe.log_error(title=title, message=message)
    except Exception:
        pass


# ===========================================================================
# Pure helper functions
# ===========================================================================

def stringify_mcp_content(content) -> str:
    """Pull clean text out of an MCP CallToolResult.content list."""
    if isinstance(content, list):
        return "\n".join(
            (t if (t := getattr(item, "text", None)) is not None else str(item))
            for item in content
        )
    return str(content)


def truncate(text: str, limit: int = MAX_EXTRACTED_CHARS) -> str:
    return text if len(text) <= limit else (
        f"{text[:limit]}\n\n[...truncated, {len(text) - limit} more characters omitted...]"
    )


# ---------------------------------------------------------------------------
# HTML rendering helpers (pure)
# ---------------------------------------------------------------------------

def _trailing_label(words: list, max_words: int = 8) -> tuple:
    """Peel off the trailing run that looks like a field label from a word
    list ending just before a colon.

    Stops as soon as it hits a word containing 2+ digits (those belong to a
    VALUE — a date, amount, registration number).

    Returns (label, rest).
    """
    label_words: list[str] = []
    i = len(words) - 1
    while i >= 0 and len(label_words) < max_words:
        w = words[i]
        if re.search(r"\d{2,}", w):
            break
        label_words.insert(0, w)
        i -= 1
    label = " ".join(label_words).strip(" .,-")
    return label, words[: i + 1]


def _looks_like_label(text: str, max_words: int = 6) -> bool:
    """Return True if *text* looks like a field label rather than a value."""
    words = text.strip().split()
    return (
        len(words) <= max_words
        and not any(re.search(r"\d{4,}", w) for w in words)
        and not (words and re.match(r"^\d", words[0]))
    )


def _extract_line_items_table(text: str):
    """Detect and extract a line-items table from extracted PDF text.

    Strategy:
    1. Pipe-delimited detection (clean extractions).
    2. Keyword-boundary detection (messy/flat) — returns [["_raw_", raw_block]].

    Returns (pre_text, table_rows | None, post_text).
    """
    # 1. Pipe-delimited (clean)
    pipe_block = re.search(r"((?:[^\n]*\|[^\n]*\n){3,})", text, re.MULTILINE)
    if pipe_block:
        block = pipe_block.group(1)
        rows = []
        for line in block.strip().splitlines():
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c]
            if cells:
                rows.append(cells)
        if len(rows) >= 2:
            return text[: pipe_block.start()], rows, text[pipe_block.end():]

    # 2. Keyword-boundary (messy)
    header_pat = re.compile(
        r"\b(Sr[\s.]*No|HSN[/\\]S|Particulars|Part\s*#|UOM|Qty|Rate)\b",
        re.IGNORECASE,
    )
    footer_pat = re.compile(
        r"\b(Sub[\s-]*Total|Grand[\s-]*Total|Tax[\s-]*Payable|Final\s+Parts|"
        r"Final\s+Labour|Gross\s+Amount|Amount\s+in\s+Words)\b",
        re.IGNORECASE,
    )
    header_m = header_pat.search(text)
    if not header_m:
        return text, None, ""

    footer_m = footer_pat.search(text, header_m.start())
    table_start = header_m.start()
    table_end = footer_m.start() if footer_m else len(text)
    raw_block = text[table_start:table_end].strip()
    if not raw_block:
        return text, None, ""

    return text[:table_start], [["_raw_", raw_block]], text[table_end:]


def _structure_flat_text(text: str, min_pairs: int = 3) -> Optional[str]:
    """Reformat flat 'Label : Value' text (job cards, invoices) into a
    styled responsive HTML card.

    Returns None when the text doesn't look like a label:value form.
    """
    def esc(s: str) -> str:
        return _html.escape(str(s or ""), quote=True)

    pre_text, line_rows, post_text = _extract_line_items_table(text)

    def _parse_pairs(raw: str):
        cleaned = re.sub(r"-{2,}\s*Page\s*\d+\s*-{2,}", " ", raw)
        chunks = cleaned.split(":")
        if len(chunks) < 2:
            return [], ""

        header_words = chunks[0].strip().split()
        label, header_words = _trailing_label(header_words)
        header = " ".join(header_words).strip()

        pairs = []
        for idx in range(1, len(chunks)):
            words = chunks[idx].strip().split()
            if idx == len(chunks) - 1:
                value = " ".join(words).strip(" .,-")
                if label and _looks_like_label(label):
                    pairs.append((label, value))
                break
            next_label, value_words = _trailing_label(words)
            value = " ".join(value_words).strip(" .,-")
            if label and _looks_like_label(label):
                pairs.append((label, value))
            label = next_label
        return pairs, header

    pairs_pre, header = _parse_pairs(pre_text)
    pairs_post, _ = _parse_pairs(post_text) if post_text.strip() else ([], "")
    pairs = pairs_pre + pairs_post

    if len(pairs) < min_pairs and not line_rows:
        return None

    CSS = (
        "<style>"
        ".ak{font-family:system-ui,sans-serif;border:1px solid #e2e8f0;border-radius:10px;"
        "overflow:hidden;margin:8px 0;background:#fff;max-width:100%}"
        ".ak-hd{display:flex;align-items:center;gap:8px;padding:9px 14px;"
        "background:#f8fafc;border-bottom:1px solid #e2e8f0;flex-wrap:wrap}"
        ".ak-title{font-size:13px;font-weight:600;color:#334155;margin:0;flex:1;min-width:0}"
        ".ak-badge{font-size:11px;font-weight:500;padding:2px 9px;border-radius:20px;"
        "background:#dbeafe;color:#1d4ed8;white-space:nowrap}"
        ".ak-wrap{overflow-x:auto}"
        ".ak-t{width:100%;border-collapse:collapse;font-size:13px;table-layout:auto}"
        ".ak-t th{text-align:left;font-size:11px;font-weight:600;color:#94a3b8;"
        "text-transform:uppercase;letter-spacing:.05em;padding:6px 12px;"
        "background:#f8fafc;border-bottom:1px solid #e2e8f0;white-space:nowrap}"
        ".ak-t td{padding:7px 12px;border-bottom:1px solid #f1f5f9;"
        "vertical-align:top;color:#1e293b;word-break:break-word}"
        ".ak-t tr:last-child td{border-bottom:none}"
        ".ak-t tr:hover td{background:#f8fafc}"
        ".ak-lbl{color:#64748b;font-weight:500;white-space:nowrap;width:1%;padding-right:20px!important}"
        ".ak-nil{color:#94a3b8;font-style:italic}"
        ".ak-sec{font-size:11px;font-weight:600;color:#94a3b8;text-transform:uppercase;"
        "letter-spacing:.05em;padding:10px 12px 4px;border-top:1px solid #f1f5f9;"
        "background:#fafafa}"
        ".ak-num{text-align:right!important}"
        "</style>"
    )

    title_esc = esc(header.strip()) if header.strip() else "Extracted Document"
    total_fields = len(pairs)
    badge_text = f"{total_fields} fields" if total_fields else "line items"

    field_rows_html = "".join(
        f'<tr><td class="ak-lbl">{esc(f.replace(chr(10), " ").strip())}</td>'
        + (f'<td>{esc((v or "").replace(chr(10), " ").strip())}</td>'
           if (v or "").replace("\n", " ").strip()
           else '<td class="ak-nil">not detected</td>')
        + '</tr>\n'
        for f, v in pairs
    )

    line_items_html = ""
    if line_rows:
        is_raw = len(line_rows) == 1 and line_rows[0][0] == "_raw_"
        if is_raw:
            raw_text_block = esc(line_rows[0][1])
            line_items_html = (
                '<tr><td colspan="2" style="padding:0">'
                '<div class="ak-sec">Line Items (raw — columns merged by extractor)</div>'
                '<div style="padding:10px 12px;background:#fafafa;font-family:monospace;'
                'font-size:12px;color:#475569;white-space:pre-wrap;overflow-x:auto;'
                f'border-top:1px solid #f1f5f9;line-height:1.6">{raw_text_block}</div>'
                '</td></tr>'
            )
        else:
            header_row = line_rows[0]
            data_rows = line_rows[1:]
            th_cells = "".join(f'<th>{esc(c)}</th>' for c in header_row)
            item_rows = "".join(
                "<tr>" + "".join(
                    f'<td{"  class=\"ak-num\"" if re.match(r"^[\d,.\\s]+$", c.strip()) else ""}>{esc(c)}</td>'
                    for c in row
                ) + "</tr>\n"
                for row in data_rows
            )
            line_items_html = (
                '<tr><td colspan="2" style="padding:0">'
                '<div class="ak-sec">Line Items</div>'
                '<div class="ak-wrap">'
                '<table class="ak-t" style="min-width:520px">'
                f'<thead><tr>{th_cells}</tr></thead>'
                f'<tbody>{item_rows}</tbody>'
                '</table></div></td></tr>'
            )

    return (
        f'{CSS}'
        f'<div class="ak">'
        f'<div class="ak-hd">'
        f'<span class="ak-title">📄 {title_esc}</span>'
        f'<span class="ak-badge">{badge_text}</span>'
        f'</div>'
        f'<div class="ak-wrap">'
        f'<table class="ak-t">'
        f'<thead><tr><th>Field</th><th>Value</th></tr></thead>'
        f'<tbody>{field_rows_html}{line_items_html}</tbody>'
        f'</table></div>'
        f'</div>'
    )


def parse_extraction_result(raw_text: str) -> tuple:
    """Parse the JSON dict the extract_file_content tool returns.

    Returns (display_content, ok, plain_text) where:
      display_content  — HTML card (or plain text if structuring was skipped)
      ok               — False if extraction failed or came back empty
      plain_text       — ALWAYS raw extracted text with no HTML; used by the
                         DocType update path so regex / LLM never see HTML
    """
    try:
        data = _json.loads(raw_text)
    except Exception:
        try:
            data = ast.literal_eval(raw_text)
        except Exception:
            text = raw_text or ""
            return text, bool(text.strip()), text

    if isinstance(data, dict):
        inner = data.get("result") if isinstance(data.get("result"), dict) else data

        if not inner.get("success"):
            err = f"[Extraction failed: {inner.get('error', 'unknown error')}]"
            return err, False, err

        content = inner.get("content") or ""
        if not content and inner.get("tables"):
            content = _json.dumps(inner["tables"], indent=2)
        if not content.strip():
            backend = inner.get("ocr_backend")
            msg = inner.get("message") or "No text was detected in the file."
            backend_note = f" (backend: {backend})" if backend else ""
            err = f"[No content extracted: {msg}{backend_note}]"
            return err, False, err

        plain_text = content
        warning = inner.get("warning")
        if warning:
            plain_text = f"{plain_text}\n\n[Note: {warning}]"

        structured = _structure_flat_text(content)
        display_content = structured if structured else content
        if warning:
            display_content = f"{display_content}\n\n[Note: {warning}]"

        return display_content, True, plain_text

    text = str(data)
    return text, bool(text.strip()), text


# ===========================================================================
# FileHandler
# ===========================================================================

class FileHandler:
    """Encapsulates all file / OCR / DocType-write logic for AikoAgent.

    Parameters
    ----------
    provider
        The active LLM provider instance (OpenAIProvider or OllamaProvider).
    session
        The active MCP ClientSession (may be None for pure-LLM calls).
    messages
        Shared message list owned by AikoAgent (passed by reference so
        history appends are visible to the agent).
    thread_id
        Used only for logging context.
    """

    # ------------------------------------------------------------------ #
    # DocType field maps
    # ------------------------------------------------------------------ #
    _SERVICE_ENTRY_FIELD_MAP = {
        "vehicle": "vehicle",
        "vehicle no": "vehicle",
        "vehicle number": "vehicle",
        "reg no": "vehicle",
        "registration": "vehicle",
        "start date": "start_date",
        "start": "start_date",
        "completion date": "completion_date",
        "completion": "completion_date",
        "end date": "completion_date",
        "date": "completion_date",
        "type": "repair_priority_class",
        "repair type": "repair_priority_class",
        "priority": "repair_priority_class",
        "odometer": "odometer",
        "km": "odometer",
        "mileage": "odometer",
        "vendor": "vendor",
        "workshop": "vendor",
        "garage": "vendor",
        "labor": "labor",
        "labour": "labor",
        "parts": "parts",
        "discount type": "discount_type",
        "discount value": "discount_value",
        "tax type": "tax_type",
        "tax value": "tax_value",
    }

    _FUEL_ENTRY_FIELD_MAP = {
        "vehicle": "vehicle",
        "vehicle no": "vehicle",
        "vehicle number": "vehicle",
        "reg no": "vehicle",
        "registration": "vehicle",
        "fuel date": "fuel_date",
        "date": "fuel_date",
        "refuel date": "fuel_date",
        "odometer": "odometer",
        "km": "odometer",
        "mileage": "odometer",
        "fuel type": "fuel_type",
        "fuel": "fuel_type",
        "fuel quantity": "fuel_quantity",
        "quantity": "fuel_quantity",
        "litres": "fuel_quantity",
        "liters": "fuel_quantity",
        "price per litre": "price_per_litre",
        "price per liter": "price_per_litre",
        "rate": "price_per_litre",
        "unit price": "price_per_litre",
        "vendor": "vendor",
        "station": "vendor",
        "fuel station": "vendor",
        "petrol station": "vendor",
    }

    _DOCTYPE_ALIASES = {
        "service entry": ("Service Entry", _SERVICE_ENTRY_FIELD_MAP),
        "service": ("Service Entry", _SERVICE_ENTRY_FIELD_MAP),
        "maintenance": ("Service Entry", _SERVICE_ENTRY_FIELD_MAP),
        "repair": ("Service Entry", _SERVICE_ENTRY_FIELD_MAP),
        "fuel entry": ("Fuel Entry", _FUEL_ENTRY_FIELD_MAP),
        "fuel": ("Fuel Entry", _FUEL_ENTRY_FIELD_MAP),
        "refuel": ("Fuel Entry", _FUEL_ENTRY_FIELD_MAP),
        "petrol": ("Fuel Entry", _FUEL_ENTRY_FIELD_MAP),
        "diesel": ("Fuel Entry", _FUEL_ENTRY_FIELD_MAP),
    }

    _DISPLAY_ONLY_PATTERNS = (
        "extract", "read", "show", "display", "what", "content", "text",
        "tell me", "give me", "summarize", "summary", "details", "list",
        "items", "fields", "data", "information", "info", "parse",
    )

    def __init__(self, provider, session, messages: list, thread_id: str):
        self.provider = provider
        self.session = session
        self.messages = messages
        self.thread_id = thread_id

    # ------------------------------------------------------------------ #
    # Public: routing helpers
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Public: pending resolution helpers
    # ------------------------------------------------------------------ #

    # Patterns the user can reply with after the "missing linked record" prompt.
    # Checked in agent.py BEFORE routing to the normal LLM path.
    _CREATE_VEHICLE_RE = re.compile(
        r'(?:yes[,\s]*create\s+vehicle|create\s+vehicle\s+([A-Z0-9]+))',
        re.IGNORECASE,
    )
    _USE_REG_RE = re.compile(
        r'use\s+([A-Z]{2}\d{2}[A-Z]{1,3}\d{1,4})',
        re.IGNORECASE,
    )

    def detect_pending_resolution(self, message: str):
        """Check if the user is responding to a missing-link prompt.

        Returns one of:
          ("create_vehicle", reg_number_or_None)
          ("use_vehicle",    reg_number)
          None  — not a pending-resolution reply; route normally
        """
        m_create = self._CREATE_VEHICLE_RE.search(message)
        if m_create:
            reg = (m_create.group(1) or "").upper().strip() or None
            return ("create_vehicle", reg)

        m_use = self._USE_REG_RE.search(message)
        if m_use:
            return ("use_vehicle", m_use.group(1).upper())

        return None

    @staticmethod
    def create_vehicle_in_frappe(registration: str) -> dict:
        """Create a minimal Vehicle record in Frappe.

        Returns {"ok": True, "name": <created name>} or
                {"ok": False, "error": <message>}.
        """
        registration = registration.strip().upper()
        # Idempotent — return existing if already there (case-insensitive)
        existing_rows = frappe.db.sql(
            "SELECT name FROM `tabVehicle` WHERE UPPER(name) = %s LIMIT 1",
            (registration,),
        )
        if existing_rows:
            return {"ok": True, "name": existing_rows[0][0], "existed": True}
        try:
            doc = frappe.get_doc({
                "doctype": "Vehicle",
                "name": registration,
                "license_plate": registration,
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            _aiko_log(
                title="AIKO Vehicle created",
                message=f"Created Vehicle: {registration}"
            )
            return {"ok": True, "name": doc.name, "existed": False}
        except Exception as e:
            _aiko_log(
                title="AIKO Vehicle create error",
                message=f"registration={registration} error={e}\n{frappe.get_traceback()}"
            )
            return {"ok": False, "error": str(e)}

    def is_display_only(self, message: str) -> bool:
        """Return True when the user just wants to view file content."""
        lower = message.lower()
        return not any(w in lower for w in (
            "create", "save", "insert", "add to", "update", "push", "submit",
            "table", "tabular", "grid", "breakdown", "items", "list items",
        ))

    def detect_doctype_intent(self, message: str):
        """Return (doctype_name, field_map, record_name_hint) if the user
        wants to create/update a Service Entry or Fuel Entry.

        Returns None if no matching intent found.
        """
        lower = message.lower()
        action_words = ("create", "save", "insert", "add", "update", "push", "submit", "make")
        if not any(w in lower for w in action_words):
            return None

        for alias, (doctype, field_map) in self._DOCTYPE_ALIASES.items():
            if alias in lower:
                record_match = re.search(
                    r'\b(SE-\d{4}-\d+|FE-\d{4}-\d+)\b', message, re.IGNORECASE
                )
                record_name = record_match.group(1).upper() if record_match else None
                return doctype, field_map, record_name

        return None

    # ------------------------------------------------------------------ #
    # Public: multimodal message builder
    # ------------------------------------------------------------------ #

    @staticmethod
    def build_multimodal_message(
        message: str, file_data: str, file_type: str, file_name: str
    ) -> dict:
        """Build a user message in OpenAI/Ollama multimodal format."""
        if file_type.startswith("image/"):
            return {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{file_type};base64,{file_data}"},
                    },
                    {"type": "text", "text": message},
                ],
            }
        return {
            "role": "user",
            "content": (
                f"[Attached file: {file_name} ({file_type}) — "
                f"binary content omitted; please process based on the description below]\n\n"
                f"{message}"
            ),
        }

    # ------------------------------------------------------------------ #
    # Public: extraction
    # ------------------------------------------------------------------ #

    async def extract(self, file_url: str, operation: str) -> tuple:
        """Call extract_file_content via MCP session deterministically.

        Returns (display_content, note, plain_text) where:
          display_content  — HTML card or plain text, shown to the user
          note             — empty or "retried with OCR" notice
          plain_text       — raw extracted text with NO HTML, for regex/LLM
        """
        try:
            result = await self.session.call_tool(
                "extract_file_content", {"file_url": file_url, "operation": operation}
            )
            raw_text = stringify_mcp_content(result.content)
            _aiko_log(
                title="AIKO extract_file_content raw_text",
                message=f"file_url={file_url} op={operation}\nraw_text={raw_text[:2000]}"
            )
            display_content, ok, plain_text = parse_extraction_result(raw_text)
            _aiko_log(
                title="AIKO _parse_extraction_result",
                message=(
                    f"ok={ok} plain_text[:500]="
                    f"{plain_text[:500] if plain_text else repr(plain_text)}"
                )
            )
        except Exception as e:
            _aiko_log(
                title="AIKO extract_file_content EXCEPTION",
                message=f"file_url={file_url} op={operation} error={e}\n{frappe.get_traceback()}"
            )
            err = f"[Extraction error: {e}]"
            return err, "", err

        # Auto-retry with OCR if plain-text extraction came back empty
        if operation == "extract" and not ok:
            try:
                ocr_result = await self.session.call_tool(
                    "extract_file_content", {"file_url": file_url, "operation": "ocr"}
                )
                ocr_raw = stringify_mcp_content(ocr_result.content)
                ocr_display, ocr_ok, ocr_plain = parse_extraction_result(ocr_raw)
                _aiko_log(
                    title="AIKO OCR retry result",
                    message=(
                        f"ocr_ok={ocr_ok} plain_text[:500]="
                        f"{ocr_plain[:500] if ocr_plain else repr(ocr_plain)}"
                    )
                )
                if ocr_ok:
                    note = "(Text extraction was empty; automatically retried with OCR.)\n\n"
                    return ocr_display, note, ocr_plain
            except Exception as e2:
                _aiko_log(title="AIKO OCR retry EXCEPTION", message=str(e2))

        return display_content, "", plain_text

    # ------------------------------------------------------------------ #
    # Public: DocType write
    # ------------------------------------------------------------------ #

    async def update_doctype(
        self,
        message: str,
        extracted_text: str,
        doctype: str,
        field_map: dict,
        record_name,
        file_name: str,
    ) -> dict:
        """Deterministically create or update a Service Entry / Fuel Entry.

        Flow:
        1. Regex pre-parser extracts key fields from the raw text.
        2. LLM fills in anything regex missed (first 3000 chars only).
        3. Merge — regex wins on vehicle (chassis confusion guard).
        4. Resolve Link fields (Vendor, Vehicle) to exact Frappe names.
        5. Pre-save Link validation — remove bad links rather than hard-fail.
        6. Write to Frappe.
        """
        # ---------------------------------------------------------------- #
        # STEP 1: Regex pre-parser
        # ---------------------------------------------------------------- #
        def _regex_extract(text: str, dt: str) -> dict:
            fields: dict = {}

            # Primary: labelled registration field
            regn_match = re.search(
                r'(?:Vehicle\s*Reg(?:n|istration)?\.?\s*No\.?\s*[:\-]?\s*|'
                r'Reg(?:n|istration)?\s*No\.?\s*[:\-]?\s*|'
                r'Vehicle\s*No\.?\s*[:\-]?\s*|'
                r'Vehicle\s*Number\s*[:\-]?\s*|'
                r'Veh\.?\s*No\.?\s*[:\-]?\s*)'
                r'([A-Z]{2}\d{2}[A-Z]{1,3}\d{1,4})',
                text, re.IGNORECASE
            )
            if regn_match:
                fields["vehicle"] = regn_match.group(1).upper()
            else:
                # Fallback: any standalone registration-pattern token in the text
                # (fuel bills often print it bare without a label)
                bare_match = re.search(
                    r'\b([A-Z]{2}\d{2}[A-Z]{1,3}\d{1,4})\b',
                    text, re.IGNORECASE
                )
                if bare_match:
                    fields["vehicle"] = bare_match.group(1).upper()

            kms_match = re.search(
                r'(?:Kms?\.?\s*[:\-]?\s*|Odometer\s*[:\-]?\s*)(\d[\d,]*)',
                text, re.IGNORECASE
            )
            if kms_match:
                fields["odometer"] = kms_match.group(1).replace(",", "")

            if dt == "Service Entry":
                date_match = re.search(
                    r'(?:Job\s*Card\s*Date|Completion\s*Date|Service\s*Date)\s*[:\-]?\s*'
                    r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
                    text, re.IGNORECASE
                )
                if date_match:
                    raw_date = date_match.group(1)
                    parts = re.split(r'[/\-]', raw_date)
                    if len(parts) == 3:
                        d, m, y = parts
                        if len(y) == 2:
                            y = "20" + y
                        try:
                            fields["completion_date"] = f"{y}-{int(m):02d}-{int(d):02d} 00:00:00"
                            fields.setdefault("start_date", fields["completion_date"])
                        except ValueError:
                            pass

                srt_match = re.search(
                    r'Service\s*Request\s*Type\s*[:\-]?\s*(Paid\s*Service|Warranty|Free\s*Service)',
                    text, re.IGNORECASE
                )
                if srt_match:
                    srt = srt_match.group(1).strip().lower()
                    if "paid" in srt:
                        fields["repair_priority_class"] = "Non Scheduled"
                    elif "warranty" in srt:
                        fields["repair_priority_class"] = "Scheduled"

                labour_match = re.search(
                    r'(?:Final\s*Labo(?:u)?r\s*Invoice\s*Amount|Labo(?:u)?r\s*(?:Invoice\s*)?Amount)'
                    r'\s*[:\-]?\s*([\d,]+\.?\d*)',
                    text, re.IGNORECASE
                )
                if labour_match:
                    fields["labor"] = labour_match.group(1).replace(",", "")
                else:
                    gross_match = re.search(
                        r'Gross\s*Amount\s*[:\-]?\s*([\d,]+\.?\d*)',
                        text, re.IGNORECASE
                    )
                    if gross_match:
                        fields["labor"] = gross_match.group(1).replace(",", "")

                parts_match = re.search(
                    r'(?:Final\s*Parts\s*Invoice\s*Amount|Parts\s*Amount)\s*[:\-]?\s*([\d,]+\.?\d*)',
                    text, re.IGNORECASE
                )
                if parts_match:
                    val = parts_match.group(1).replace(",", "")
                    try:
                        if float(val) > 0:
                            fields["parts"] = val
                    except ValueError:
                        pass

                tax_match = re.search(
                    r'(?:Total\s*Tax|Tax\s*Amount)\s*[:\-]?\s*([\d,]+\.?\d*)',
                    text, re.IGNORECASE
                )
                if tax_match:
                    fields["tax_value"] = tax_match.group(1).replace(",", "")
                    fields["tax_type"] = "Fixed"

                # ── Vendor ────────────────────────────────────────────────
                # Strategy 1: "For <NAME>" near bottom (signature line)
                vendor_name = None
                for_match = re.search(
                    r'For\s+([\w][\w\s]{2,60}?'
                    r'(?:MOTORS|AUTOMOBILES?|AUTOMOTIVES?|AUTO|AGENCIES|DEALERSHIP|'
                    r'WORKS?|SERVICES?|ENTERPRISES?|SOLUTIONS?))',
                    text[-4000:], re.IGNORECASE | re.DOTALL,
                )
                if for_match:
                    vendor_name = re.sub(r'\s+', ' ', for_match.group(1)).strip().title()

                # Strategy 2: "Dealer Name / Workshop Name" label
                if not vendor_name:
                    lbl_match = re.search(
                        r'(?:Dealer\s*Name|Workshop\s*Name?)\s*[:\-]\s*(.+?)(?:\n|$)',
                        text, re.IGNORECASE,
                    )
                    if lbl_match:
                        vendor_name = lbl_match.group(1).strip().title()

                # Strategy 3: letterhead — first non-blank line that contains
                # a known dealer keyword (catches bills printed on dealer stationery)
                if not vendor_name:
                    for line in text.splitlines()[:20]:
                        line = line.strip()
                        if re.search(
                            r'(?:MOTORS|AUTOMOBILES?|AUTOMOTIVES?|AUTO|AGENCIES|'
                            r'DEALERSHIP|WORKS?|SERVICES?|ENTERPRISES?)',
                            line, re.IGNORECASE
                        ) and len(line) > 5:
                            vendor_name = re.sub(r'\s+', ' ', line).strip().title()
                            break

                if vendor_name:
                    fields["vendor"] = vendor_name

                # ── Service Line Items ─────────────────────────────────────
                # Service Line Items child table schema (service_line_items.json):
                #   service_task  → Link to "Service Task"  (mandatory)
                #   labor         → Currency
                #   parts         → Currency
                #   subtotal      → Currency (read_only, computed)
                #
                # From a service bill the closest mapping is:
                #   Particulars / Description  → service_task name
                #   Labour amount per row      → labor
                #   Parts amount per row       → parts
                #
                # We use the LLM (step 2) to fill service_task values properly;
                # regex here only pulls raw row text so the LLM can map them.
                line_items = []

                # Pattern A: structured rows — Sr No + Particulars + amounts
                # Typical Maruti / dealer job card layout:
                #   1  AB1234  PART#  Oil Filter PAID  Nos  1  250.00  250.00
                row_pat = re.compile(
                    r'(?m)^\s*(\d{1,3})\s+'       # Sr No
                    r'(?:[\w/]{3,}\s+){0,3}'        # optional HSN/SAC, part#, etc.
                    r'([A-Za-z][\w\s&/()\.,-]{3,60}?)'  # Particulars
                    r'\s+(?:PAID|FREE|AMC|WARRANTY)?'
                    r'\s+(?:[A-Za-z]+\s+)?'         # UOM (Nos, Ltr, etc.)
                    r'(\d+(?:\.\d+)?)\s+'         # Qty
                    r'([\d,]+\.?\d*)\s+'           # Rate
                    r'([\d,]+\.?\d*)\s*$'          # Total Amt
                )
                for m in row_pat.finditer(text):
                    desc = re.sub(r'\s+', ' ', m.group(2)).strip().rstrip(".,")
                    if len(desc) < 3:
                        continue
                    try:
                        rate = float(m.group(4).replace(",", ""))
                        total = float(m.group(5).replace(",", ""))
                        qty   = float(m.group(3))
                    except ValueError:
                        continue
                    line_items.append({
                        "_desc": desc,
                        "labor": total,   # default: treat row total as labor
                        "parts": 0.0,
                    })

                # Pattern B: fallback — lines with "PAID" or "FREE" keyword
                # and two trailing numbers (rate, total)
                if not line_items:
                    fb_pat = re.compile(
                        r'([A-Za-z][\w\s&/()\.,-]{3,60?})'
                        r'\s+(?:PAID|FREE|AMC)'
                        r'(?:[\w\s]*)'
                        r'([\d,]+\.?\d*)\s+([\d,]+\.?\d*)',
                        re.IGNORECASE,
                    )
                    for m in fb_pat.finditer(text):
                        desc = re.sub(r'\s+', ' ', m.group(1)).strip().rstrip(".,")
                        if len(desc) < 3:
                            continue
                        try:
                            total = float(m.group(3).replace(",", ""))
                        except ValueError:
                            continue
                        line_items.append({
                            "_desc": desc,
                            "labor": total,
                            "parts": 0.0,
                        })

                if line_items:
                    fields["_line_items"] = line_items
                    _aiko_log(
                        title="AIKO service line_items extracted",
                        message=f"count={len(line_items)} items={line_items[:3]}"
                    )

            elif dt == "Fuel Entry":
                date_match = re.search(
                    r'(?:Date|Fuel\s*Date)\s*[:\-]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
                    text, re.IGNORECASE
                )
                if date_match:
                    parts = re.split(r'[/\-]', date_match.group(1))
                    if len(parts) == 3:
                        d, m, y = parts
                        if len(y) == 2:
                            y = "20" + y
                        try:
                            fields["fuel_date"] = f"{y}-{int(m):02d}-{int(d):02d} 00:00:00"
                        except ValueError:
                            pass

                qty_match = re.search(
                    r'(?:Qty|Quantity|Litres?|Liters?)\s*[:\-]?\s*([\d]+\.?\d*)',
                    text, re.IGNORECASE
                )
                if qty_match:
                    fields["fuel_quantity"] = qty_match.group(1)

                ppl_match = re.search(
                    r'(?:Price\s*[Pp]er\s*[Ll]i(?:t(?:re|er))?|Rate)\s*[:\-]?\s*([\d]+\.?\d*)',
                    text, re.IGNORECASE
                )
                if ppl_match:
                    fields["price_per_litre"] = ppl_match.group(1)

            return fields

        regex_fields = _regex_extract(extracted_text, doctype)
        _aiko_log(
            title="AIKO regex_extract result",
            message=f"doctype={doctype} file={file_name}\nregex_fields={regex_fields}"
        )

        # ---------------------------------------------------------------- #
        # STEP 2: LLM call — skipped when regex already found all key fields
        # ---------------------------------------------------------------- #
        # Key fields that matter most; if regex has all of these we skip the
        # LLM round-trip entirely (saves 2-5 s per request).
        _key_fields = {"vehicle", "completion_date", "fuel_date"}
        _regex_has_keys = _key_fields.intersection(regex_fields.keys())
        _skip_llm = len(_regex_has_keys) >= 2  # at least vehicle + a date

        field_list = "\n".join(f"  - {fname}" for fname in sorted(set(field_map.values())))
        header_text = extracted_text[:3000]

        extract_prompt = (
            f"Extract values from this service/fuel document for a Frappe '{doctype}' record.\n"
            f"Return ONLY a JSON object with these keys (omit any you can't find):\n"
            f"{field_list}\n\n"
            f"RULES (follow exactly):\n"
            f"- vehicle: REGISTRATION NUMBER only (e.g. TN45CA7234). "
            f"NEVER use Chassis No (17-char VIN like MAT...).\n"
            f"- Dates: YYYY-MM-DD 00:00:00 format. 'Job Card Date' maps to completion_date.\n"
            f"- Numbers: digits only, no units or commas.\n"
            f"- repair_priority_class: 'Paid Service' → 'Non Scheduled'; "
            f"'Warranty' → 'Scheduled'; 'Emergency' → 'Emergency'\n"
            f"- discount_type / tax_type: 'Percentage %' or 'Fixed'\n"
            f"- labor: the 'Final Labour Invoice Amount' or 'Gross Amount' (digits only)\n"
            f"- vendor: the workshop/dealer name — check 'For <NAME>' near the signature, "
            f"or the letterhead at the top of the bill (first few lines).\n"
            + (
            f"- _line_items: array of objects for each service row in the bill table. "
            f"Each object must have:\n"
            f"    \"service_task\": the exact Particulars/description text for that row,\n"
            f"    \"labor\": the labour amount for that row (0 if parts-only),\n"
            f"    \"parts\": the parts cost for that row (0 if labour-only).\n"
            f"  If only one total is shown per row, put it in labor.\n"
            if doctype == "Service Entry" else ""
            )
            + f"\nDOCUMENT:\n{header_text}\n\nJSON only, nothing else."
        )

        system_msg = {
            "role": "system",
            "content": "You extract structured data. Return only valid JSON, no explanation."
        }
        llm_messages = [system_msg, {"role": "user", "content": extract_prompt}]

        usage = {"input_tokens": 0, "output_tokens": 0}
        llm_fields: dict = {}
        raw_answer = ""
        if _skip_llm:
            _aiko_log(
                title="AIKO LLM skipped",
                message=f"regex already found key fields {_regex_has_keys} — LLM call skipped"
            )
        else:
            try:
                # session=None — no MCP tools for this pure JSON extraction call
                result = await self.provider.process_query_with_messages(None, llm_messages)
                raw_answer, _, usage = result

                if raw_answer and raw_answer.strip():
                    jtext = re.sub(r'^```(?:json)?|```$', '', raw_answer.strip(), flags=re.MULTILINE).strip()
                    if bm := re.search(r'\{.*\}', jtext, re.DOTALL):
                        jtext = bm.group(0)
                    try:
                        llm_fields = _json.loads(jtext)
                    except Exception:
                        try:
                            llm_fields = ast.literal_eval(jtext)
                        except Exception:
                            llm_fields = {}
            except Exception as e:
                _aiko_log(title="AIKO LLM field-extract error", message=str(e))

            _aiko_log(
                title="AIKO LLM field-extract result",
                message=f"doctype={doctype}\nllm_fields={llm_fields}\nraw_answer={raw_answer[:500]}"
            )

        # ---------------------------------------------------------------- #
        # STEP 3: Merge — regex wins; LLM fills gaps
        # ---------------------------------------------------------------- #
        valid_fieldnames = set(field_map.values())
        _bad_vals = (None, "", "null", "N/A", "Unknown")
        merged = {k: v for k, v in llm_fields.items() if k in valid_fieldnames and v not in _bad_vals}
        merged.update({k: v for k, v in regex_fields.items() if k in valid_fieldnames and v not in _bad_vals[:3]})

        # Merge _line_items — not a real field, kept separately.
        # LLM result wins over regex if it found structured rows; otherwise keep regex result.
        _llm_items = llm_fields.get("_line_items")
        _regex_items = regex_fields.get("_line_items")
        if isinstance(_llm_items, list) and _llm_items:
            merged["_line_items"] = _llm_items
        elif isinstance(_regex_items, list) and _regex_items:
            merged["_line_items"] = _regex_items

        # Remove vendor if it looks wrong
        if "vendor" in merged:
            bad_vendor_words = (
                "insurance", "job card", "free service", "paid service",
                "warranty", "scheduled", "emergency", "n/a", "unknown",
            )
            if any(w in merged["vendor"].lower() for w in bad_vendor_words):
                _aiko_log(
                    title="AIKO vendor rejected",
                    message=f"Rejected bad vendor value: {merged['vendor']!r}"
                )
                del merged["vendor"]

        if not merged:
            return {
                "content": (
                    f"❌ Could not extract any fields from **{file_name}** for a {doctype}.\n\n"
                    f"Regex found: `{regex_fields}`\n"
                    f"LLM returned: `{raw_answer[:300]}`\n\n"
                    f"Try uploading a clearer scan or enter the values manually."
                ),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }

        # Pull line items out before any field validation — they are child rows,
        # not scalar fields, and must not pass through link/cast/mandatory checks.
        line_items_rows = merged.pop("_line_items", [])
        clean_fields = merged

        # ---------------------------------------------------------------- #
        # STEP 3a: Parse values mentioned in the user's chat message
        #          and detect conflicts with what was extracted from the bill.
        #
        # Covers: vehicle, vendor, odometer, labor, parts, tax_value,
        #         discount_value, completion_date / fuel_date.
        #
        # Outcomes:
        #   • Field missing in bill   → inject from chat silently.
        #   • Field present & SAME    → no action.
        #   • Field present & DIFFERS → ask user to confirm which to use;
        #                               return early and wait for reply.
        # ---------------------------------------------------------------- #
        def _parse_chat_fields(msg: str, dt: str) -> dict:
            """Extract any field values the user typed in chat."""
            chat: dict = {}

            # Vehicle registration  e.g. "TN45CA7234", "vehicle is TN45CA7234"
            v_match = re.search(
                r'\b([A-Z]{2}\d{2}[A-Z]{1,3}\d{1,4})\b', msg, re.IGNORECASE
            )
            if v_match:
                chat["vehicle"] = v_match.group(1).upper()

            # Odometer  e.g. "odometer 45230", "45230 km"
            odo_match = re.search(
                r'(?:odometer|odo|km|kms|mileage)\s*[:\-]?\s*([\d,]+)'
                r'|(\b[\d,]{4,6}\b)\s*kms?\b',
                msg, re.IGNORECASE
            )
            if odo_match:
                raw_odo = (odo_match.group(1) or odo_match.group(2) or "").replace(",", "")
                if raw_odo:
                    chat["odometer"] = raw_odo

            # Labor / labour amount  e.g. "labour 1500", "labor amount 2000"
            lab_match = re.search(
                r'labo(?:u)?r\s*(?:amount|charge|cost)?\s*[:\-]?\s*([\d,]+\.?\d*)',
                msg, re.IGNORECASE
            )
            if lab_match:
                chat["labor"] = lab_match.group(1).replace(",", "")

            # Parts amount  e.g. "parts 800"
            parts_match = re.search(
                r'parts?\s*(?:amount|cost|charge)?\s*[:\-]?\s*([\d,]+\.?\d*)',
                msg, re.IGNORECASE
            )
            if parts_match:
                chat["parts"] = parts_match.group(1).replace(",", "")

            # Tax value  e.g. "tax 180"
            tax_match = re.search(
                r'tax\s*(?:value|amount)?\s*[:\-]?\s*([\d,]+\.?\d*)',
                msg, re.IGNORECASE
            )
            if tax_match:
                chat["tax_value"] = tax_match.group(1).replace(",", "")

            # Discount value  e.g. "discount 100"
            disc_match = re.search(
                r'discount\s*(?:value|amount)?\s*[:\-]?\s*([\d,]+\.?\d*)',
                msg, re.IGNORECASE
            )
            if disc_match:
                chat["discount_value"] = disc_match.group(1).replace(",", "")

            # Date  e.g. "date 12/05/2025", "05-12-2025"
            date_match = re.search(
                r'(?:date\s*[:\-]?\s*)?(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
                msg, re.IGNORECASE
            )
            if date_match:
                dp = re.split(r'[/\-]', date_match.group(1))
                if len(dp) == 3:
                    d, m, y = dp
                    if len(y) == 2:
                        y = "20" + y
                    try:
                        formatted = f"{y}-{int(m):02d}-{int(d):02d} 00:00:00"
                        date_key = "fuel_date" if dt == "Fuel Entry" else "completion_date"
                        chat[date_key] = formatted
                    except ValueError:
                        pass

            # Vendor / workshop name  e.g. "vendor ABC Motors", "workshop XYZ Auto"
            vend_match = re.search(
                r'(?:vendor|workshop|garage|station|dealer)\s*[:\-]?\s*([A-Za-z][A-Za-z0-9\s&]{2,50})',
                msg, re.IGNORECASE
            )
            if vend_match:
                chat["vendor"] = vend_match.group(1).strip()

            return chat

        chat_fields = _parse_chat_fields(message, doctype)
        _aiko_log(
            title="AIKO chat_fields parsed",
            message=f"doctype={doctype}\nchat_fields={chat_fields}"
        )

        # Separate conflicts from safe injections
        conflicts: dict = {}   # {fieldname: {"bill": val, "chat": val}}
        for fieldname, chat_val in chat_fields.items():
            bill_val = clean_fields.get(fieldname)
            if not bill_val:
                # Missing in bill — inject from chat silently
                clean_fields[fieldname] = chat_val
                _aiko_log(
                    title="AIKO chat field injected (bill empty)",
                    message=f"{fieldname}: bill=<empty> → using chat value {chat_val!r}"
                )
            else:
                # Normalise for comparison (strip spaces, uppercase, drop decimals noise)
                def _norm(v):
                    return re.sub(r'\.0+$', '', str(v).strip().upper().replace(" ", ""))
                if _norm(bill_val) != _norm(chat_val):
                    conflicts[fieldname] = {"bill": bill_val, "chat": chat_val}

        if conflicts:
            # Build a readable confirmation prompt for the user
            lines = [
                f"⚠️ **Conflict detected** between what you typed and what was extracted "
                f"from **{file_name}**. Please confirm which value to use:\n"
            ]
            for fieldname, vals in conflicts.items():
                label = fieldname.replace("_", " ").title()
                lines.append(
                    f"**{label}**\n"
                    f"  • 📄 From bill: `{vals['bill']}`\n"
                    f"  • 💬 From your message: `{vals['chat']}`"
                )
            lines.append(
                "\nReply with:\n"
                "- **`use bill`** — keep all bill values\n"
                "- **`use mine`** — use all values you typed\n"
                "- Or specify per field, e.g. `vehicle from bill, date from mine`"
            )
            _aiko_log(
                title="AIKO conflict — awaiting user confirmation",
                message=f"conflicts={conflicts}"
            )
            return {
                "content": "\n\n".join(lines),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "_conflicts": conflicts,          # caller can inspect if needed
                "_pending_confirmation": True,
            }

        # ---------------------------------------------------------------- #
        # STEP 3b: Resolve Link fields
        # ---------------------------------------------------------------- #
        def _resolve_vendor(raw_value: str, is_service: bool) -> str:
            """Single-query vendor resolution — replaces 3 sequential SQL round-trips."""
            if not raw_value:
                return raw_value
            vendor_type_col = "is_service_vendor" if is_service else "is_fuel_vendor"
            stripped = raw_value.replace(" ", "").upper()
            tokens = [t for t in raw_value.upper().split() if len(t) > 2]
            first_token = tokens[0] if tokens else stripped[:4]

            # One query: exact match first (ORDER BY CASE), then fuzzy fallback
            rows = frappe.db.sql(
                f"""SELECT name,
                       CASE WHEN UPPER(REPLACE(name,' ','')) = %s THEN 0
                            WHEN UPPER(REPLACE(name,' ','')) LIKE %s THEN 1
                            ELSE 2 END AS score
                    FROM `tabVendor`
                    WHERE {vendor_type_col} = 1
                      AND (
                          UPPER(REPLACE(name,' ','')) LIKE %s
                          OR UPPER(name) LIKE %s
                      )
                    ORDER BY score
                    LIMIT 1""",
                (stripped, f"%{stripped}%", f"%{stripped}%", f"%{first_token}%"),
                as_dict=True,
            )
            return rows[0]["name"] if rows else raw_value

        def _resolve_vehicle(raw_value: str) -> str:
            """Single-query vehicle resolution."""
            if not raw_value:
                return raw_value
            stripped = raw_value.replace(" ", "").upper()
            rows = frappe.db.sql(
                """SELECT name,
                       CASE WHEN UPPER(REPLACE(name,' ','')) = %s THEN 0 ELSE 1 END AS score
                    FROM `tabVehicle`
                    WHERE UPPER(REPLACE(name,' ','')) LIKE %s
                    ORDER BY score LIMIT 1""",
                (stripped, f"%{stripped}%"),
                as_dict=True,
            )
            return rows[0]["name"] if rows else raw_value

        if "vendor" in clean_fields:
            resolved_vendor = _resolve_vendor(
                clean_fields["vendor"], is_service=(doctype == "Service Entry")
            )
            _aiko_log(
                title="AIKO vendor resolution",
                message=f"raw={clean_fields['vendor']!r} resolved={resolved_vendor!r}"
            )
            clean_fields["vendor"] = resolved_vendor

        if "vehicle" in clean_fields:
            resolved_vehicle = _resolve_vehicle(clean_fields["vehicle"])
            _aiko_log(
                title="AIKO vehicle resolution",
                message=f"raw={clean_fields['vehicle']!r} resolved={resolved_vehicle!r}"
            )
            clean_fields["vehicle"] = resolved_vehicle

        # Cast numeric fields to proper Python types so Frappe's computed fields
        # (e.g. total_amount = fuel_quantity * price_per_litre) never get
        # "can't multiply sequence by non-int of type 'float'" errors.
        _float_fields = ("fuel_quantity", "price_per_litre", "odometer",
                         "labor", "parts", "discount_value", "tax_value")
        for _fld in _float_fields:
            if _fld in clean_fields:
                try:
                    clean_fields[_fld] = float(str(clean_fields[_fld]).replace(",", ""))
                except (ValueError, TypeError):
                    pass  # leave as-is; Frappe will surface a validation error

        # Drop zero / falsy numeric fields
        for _fld in ("parts", "discount_value", "tax_value"):
            try:
                if _fld in clean_fields and float(clean_fields[_fld]) == 0:
                    del clean_fields[_fld]
            except (ValueError, TypeError):
                pass

        _aiko_log(
            title="AIKO final merged fields",
            message=f"doctype={doctype}\nclean_fields={clean_fields}"
        )

        # ---------------------------------------------------------------- #
        # Resolve record_name for "update" intent
        # ---------------------------------------------------------------- #
        action_word_lower = message.lower()
        is_update_intent = any(
            w in action_word_lower for w in ("update", "save", "push")
        )
        is_create_intent = any(
            w in action_word_lower for w in ("create", "insert", "add", "make", "new")
        )

        if not record_name and is_update_intent and not is_create_intent:
            vehicle_val = clean_fields.get("vehicle")
            if vehicle_val:
                existing = frappe.db.get_value(
                    doctype,
                    {"vehicle": vehicle_val, "docstatus": 0},
                    "name",
                    order_by="creation desc",
                )
                if existing:
                    record_name = existing
                    _aiko_log(
                        title="AIKO auto-resolved record_name",
                        message=f"doctype={doctype} vehicle={vehicle_val} → record_name={record_name}"
                    )

        # ---------------------------------------------------------------- #
        # Pre-save Link validation + mandatory field check — STRICT mode
        #
        # Every linked field must point to an EXISTING record in Frappe.
        # If a value is present but the record doesn't exist, or a mandatory
        # field is entirely absent, we return a STANDARDISED blocking response
        # so the user sees the same prompt every time for the same situation.
        # ---------------------------------------------------------------- #
        # Per-doctype link field definitions
        #   key   → fieldname in clean_fields
        #   value → (target DocType, is_mandatory)
        #
        # is_mandatory = True  means the field is reqd:1 in the DocType JSON.
        # Adding a new DocType? Just extend this dict.
        # ---------------------------------------------------------------- #
        _DOCTYPE_LINK_FIELDS: dict[str, dict] = {
            "Fuel Entry": {
                "vehicle":   ("Vehicle",         True),
                "vendor":    ("Vendor",           False),
                "fuel_type": ("Fuel Type",        False),
                "unit":      ("Fuel Entry Unit",  False),
                "trip":      ("Trip",             False),
            },
            "Service Entry": {
                "vehicle": ("Vehicle",  True),
                "vendor":  ("Vendor",   False),
                "trip":    ("Trip",     False),
            },
        }

        link_fields: dict = _DOCTYPE_LINK_FIELDS.get(doctype, {})
        # Fallback — keep old flat dict for any unknown doctype
        if not link_fields:
            link_fields = {
                "vendor": ("Vendor", False),
                "vehicle": ("Vehicle", True),
                "fuel_type": ("Fuel Type", False),
                "unit": ("Fuel Entry Unit", False),
                "trip": ("Trip", False),
            }

        # Batch existence check — one query per target DocType
        _by_doctype: dict = defaultdict(list)  # target_doctype → [(fieldname, val, is_mandatory)]
        for fieldname, (target_doctype, is_mandatory) in link_fields.items():
            if fieldname in clean_fields:
                _by_doctype[target_doctype].append((fieldname, clean_fields[fieldname], is_mandatory))

        missing_links: dict = {}   # fieldname -> (val, target_doctype, is_mandatory)
        for target_doctype, field_tuples in _by_doctype.items():
            vals = [v for _, v, _ in field_tuples]
            # Case-insensitive existence check — MySQL IN %s is collation-dependent;
            # UPPER() on both sides guarantees consistent behaviour regardless of
            # how the vehicle/vendor name was typed or stored in Frappe.
            found_rows = frappe.db.sql(
                f"SELECT name FROM `tab{target_doctype}` WHERE UPPER(name) IN %s",
                ([v.upper() for v in vals],),
            )
            # Map UPPER(name) -> actual Frappe name so canonical casing is preserved
            found_upper: dict = {r[0].upper(): r[0] for r in found_rows}
            for fieldname, val, is_mandatory in field_tuples:
                canonical = found_upper.get(val.upper() if val else "")
                if canonical:
                    # Put exact Frappe record name back (correct case)
                    clean_fields[fieldname] = canonical
                else:
                    _aiko_log(
                        title="AIKO Link validation - not found",
                        message=f"{fieldname}={val!r} not in {target_doctype} mandatory={is_mandatory}"
                    )
                    missing_links[fieldname] = (val, target_doctype, is_mandatory)
                    del clean_fields[fieldname]

        # After removing bad link values, check whether any mandatory field
        # is now absent from clean_fields (either was never extracted, or
        # just got removed because it didn't exist in Frappe).
        _MANDATORY_FIELDS: dict[str, list] = {
            "Fuel Entry":    ["vehicle", "fuel_quantity", "fuel_date"],
            "Service Entry": ["vehicle", "odometer", "completion_date"],
        }
        mandatory_fields = _MANDATORY_FIELDS.get(doctype, [])
        empty_mandatory: list = [
            f for f in mandatory_fields if not clean_fields.get(f)
        ]

        # ---------------------------------------------------------------- #
        # Standardized blocking response
        #
        # Triggered when EITHER:
        #   • missing_links  — a linked field value doesn't exist in Frappe
        #   • empty_mandatory — a required field has no value at all
        #
        # Response format is ALWAYS identical regardless of how we got here,
        # so the user sees the same prompt every time for the same situation.
        # ---------------------------------------------------------------- #
        if missing_links or empty_mandatory:
            _lower_msg = message.lower()
            _bill_preferred = any(
                w in _lower_msg for w in ("take bill", "use bill", "from bill")
            )

            lines: list[str] = []

            # --- Section 1: non-existent linked records ---
            if missing_links:
                lines.append(
                    f"⚠️ **Cannot save {doctype} — the following linked records were not "
                    f"found in Frappe:**\n"
                )
                for fieldname, (val, target_doctype, is_mand) in missing_links.items():
                    label = fieldname.replace("_", " ").title()
                    mand_tag = " *(mandatory)*" if is_mand else ""
                    lines.append(
                        f"- **{label}**{mand_tag}: `{val}` — not found in **{target_doctype}**"
                    )
                lines.append("")

            # --- Section 2: mandatory fields with no value at all ---
            if empty_mandatory:
                lines.append(
                    f"⚠️ **Cannot save {doctype} — the following mandatory fields are "
                    f"missing and could not be extracted:**\n"
                )
                for fieldname in empty_mandatory:
                    label = fieldname.replace("_", " ").title()
                    lines.append(f"- **{label}** *(mandatory)*")
                lines.append("")

            # --- Resolution instructions — vehicle gets special handling ---
            _vehicle_missing_link = "vehicle" in missing_links
            _vehicle_empty = "vehicle" in empty_mandatory
            _has_vehicle_issue = _vehicle_missing_link or _vehicle_empty

            if _has_vehicle_issue:
                vehicle_val = (
                    missing_links["vehicle"][0] if _vehicle_missing_link else None
                )
                if vehicle_val:
                    # We have a value but it doesn't exist in Frappe yet
                    if _bill_preferred:
                        lines.append(
                            f"💡 The vehicle **`{vehicle_val}`** from the bill does not exist "
                            f"in Frappe yet.\n\n"
                            f"Reply with one of:\n"
                            f"- **`yes, create vehicle`** — create `{vehicle_val}` first, "
                            f"then save the {doctype}\n"
                            f"- **`use <REG>`** — provide the correct existing vehicle registration\n"
                            f"- **`skip vehicle`** — save {doctype} without the vehicle field *(not recommended — it is mandatory)*"
                        )
                    else:
                        lines.append(
                            f"💡 Vehicle **`{vehicle_val}`** was read from the bill but does "
                            f"not exist in Frappe.\n\n"
                            f"Reply with one of:\n"
                            f"- **`create vehicle {vehicle_val}`** — create the vehicle record "
                            f"first, then save the {doctype}\n"
                            f"- **`use <REG>`** — provide the correct existing vehicle registration\n"
                            f"- **`skip vehicle`** — save {doctype} without the vehicle field *(not recommended — it is mandatory)*"
                        )
                else:
                    # Vehicle field completely absent — could not extract it at all
                    lines.append(
                        f"💡 **Vehicle** is mandatory for {doctype} but could not be "
                        f"extracted from the bill.\n\n"
                        f"Reply with one of:\n"
                        f"- **`vehicle <REG>`** — e.g. `vehicle TN45CA7234`\n"
                        f"- **`create vehicle <REG>`** — create the vehicle then save the {doctype}"
                    )

                # Non-vehicle missing links get their own resolution hint
                other_missing = {k: v for k, v in missing_links.items() if k != "vehicle"}
                if other_missing:
                    lines.append("")
                    lines.append("For the other missing linked records:")
                    lines.append(
                        "- Create them in Frappe first and retry, **or**\n"
                        "- Reply with the correct existing record name for each field, **or**\n"
                        "- Reply **`skip <fieldname>`** to omit a non-mandatory field."
                    )
            else:
                # No vehicle issue — generic resolution instructions
                lines.append(
                    "To proceed:\n"
                    "- Create the missing records in Frappe first, then retry, **or**\n"
                    "- Reply with the correct existing record names, **or**\n"
                    "- Reply **`skip <fieldname>`** to omit a non-mandatory field."
                )

            _aiko_log(
                title="AIKO Link/mandatory validation — prompting user",
                message=(
                    f"missing_links={missing_links}\n"
                    f"empty_mandatory={empty_mandatory}"
                )
            )

            import json as _json
            _pending_payload = _json.dumps({
                "doctype": doctype,
                "vehicle": missing_links.get("vehicle", (None,))[0],
                "extracted_text": extracted_text[:4000],
                "file_name": file_name,
                "field_map": {k: v for k, v in field_map.items()},
            }, ensure_ascii=False)
            _context_comment = f"\n\n<!-- AIKO_PENDING: {_pending_payload} -->"

            return {
                "content": "\n".join(lines) + _context_comment,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "_missing_links": {k: v[0] for k, v in missing_links.items()},
                "_empty_mandatory": empty_mandatory,
                "_pending_link_resolution": True,
            }


        try:
            if record_name:
                doc = frappe.get_doc(doctype, record_name)
                for fieldname, value in clean_fields.items():
                    doc.set(fieldname, value)
            else:
                doc = frappe.get_doc({"doctype": doctype, **clean_fields})

            doc.flags.ignore_mandatory = True
            doc.flags.ignore_validate_update_after_submit = True

            if line_items_rows and doctype == "Service Entry":
                for item in line_items_rows:
                    task_name = item.get("service_task") or item.get("_desc", "")
                    if not task_name:
                        continue
                    # Resolve service_task: case-insensitive LIKE match against Service Task
                    task_stripped = task_name.replace(" ", "").upper()
                    task_rows = frappe.db.sql(
                        """SELECT name FROM `tabService Task`
                           WHERE UPPER(REPLACE(name, ' ', '')) LIKE %s
                           LIMIT 1""",
                        (f"%{task_stripped[:20]}%",),
                    )
                    resolved_task = task_rows[0][0] if task_rows else task_name
                    row = doc.append("table_hoqw", {})
                    row.service_task = resolved_task
                    row.labor = float(str(item.get("labor", 0)).replace(",", "") or 0)
                    row.parts = float(str(item.get("parts", 0)).replace(",", "") or 0)

            if record_name:
                doc.save(ignore_permissions=True)
                frappe.db.commit()
                action_done = f"updated **{record_name}**"
            else:
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                action_done = f"created **{doc.name}**"



        except Exception as e:
            _aiko_log(
                title=f"AIKO {doctype} save error",
                message=frappe.get_traceback()
            )
            return {
                "content": (
                    f"❌ Failed to save the {doctype} record: `{e}`\n\n"
                    f"Fields attempted:\n"
                    + "\n".join(f"- **{k}**: {v}" for k, v in clean_fields.items())
                ),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }

        field_rows = "\n".join(f"| {k} | {v} |" for k, v in clean_fields.items())
        if line_items_rows:
            field_rows += f"\n| line items | {len(line_items_rows)} row(s) added to Service Line Items |"

        # Trigger list-view refresh in Frappe desk automatically
        try:
            frappe.publish_realtime(
                "list_update",
                {"doctype": doctype},
                after_commit=True,
            )
        except Exception:
            pass



        final_answer = (
            f"✅ Successfully {action_done} in **{doctype}**.\n\n"
            f"| Field | Value |\n|---|---|\n{field_rows}\n\n"
   
        )

        return {
            "content": final_answer,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }