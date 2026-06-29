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
    words = text.strip().split()
    return (
        len(words) <= max_words
        and not any(re.search(r"\d{4,}", w) for w in words)
        and not (words and re.match(r"^\d", words[0]))
    )


def _extract_line_items_table(text: str):
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

    Returns (display_content, ok, plain_text).
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
    """Encapsulates all file / OCR / DocType-write logic for AikoAgent."""

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

    _CREATE_VEHICLE_RE = re.compile(
        r'(?:yes[,\s]*create\s+vehicle|create\s+vehicle\s+([A-Z0-9]+))',
        re.IGNORECASE,
    )
    _USE_REG_RE = re.compile(
        r'use\s+([A-Z]{2}\d{2}[A-Z]{1,3}\d{1,4})',
        re.IGNORECASE,
    )

    def detect_pending_resolution(self, message: str):
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
        registration = registration.strip().upper()
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
            _aiko_log("AIKO Vehicle created", f"Created Vehicle: {registration}")
            return {"ok": True, "name": doc.name, "existed": False}
        except Exception as e:
            _aiko_log("AIKO Vehicle create error",
                      f"registration={registration} error={e}\n{frappe.get_traceback()}")
            return {"ok": False, "error": str(e)}

    def is_display_only(self, message: str) -> bool:
        lower = message.lower()
        _write_words = ("create", "save", "insert", "add to", "update", "push", "submit")
        return not any(w in lower for w in _write_words)

    def detect_doctype_intent(self, message: str):
        lower = message.lower()
        action_words = ("create", "save", "insert", "add", "update", "push", "make")
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

    @staticmethod
    def build_multimodal_message(
        message: str, file_data: str, file_type: str, file_name: str
    ) -> dict:
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

    async def extract(self, file_url: str, operation: str) -> tuple:
        """Call extract_file_content via MCP session deterministically.

        Returns (display_content, note, plain_text).
        """
        try:
            result = await self.session.call_tool(
                "extract_file_content", {"file_url": file_url, "operation": operation}
            )
            raw_text = stringify_mcp_content(result.content)
            _aiko_log("AIKO extract_file_content raw_text",
                      f"file_url={file_url} op={operation}\nraw_text={raw_text[:2000]}")
            display_content, ok, plain_text = parse_extraction_result(raw_text)
            _aiko_log("AIKO _parse_extraction_result",
                      f"ok={ok} plain_text[:500]={plain_text[:500] if plain_text else repr(plain_text)}")
        except Exception as e:
            _aiko_log("AIKO extract_file_content EXCEPTION",
                      f"file_url={file_url} op={operation} error={e}\n{frappe.get_traceback()}")
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
                _aiko_log("AIKO OCR retry result",
                          f"ocr_ok={ocr_ok} plain_text[:500]={ocr_plain[:500] if ocr_plain else repr(ocr_plain)}")
                if ocr_ok:
                    note = "(Text extraction was empty; automatically retried with OCR.)\n\n"
                    return ocr_display, note, ocr_plain
            except Exception as e2:
                _aiko_log("AIKO OCR retry EXCEPTION", str(e2))

        return display_content, "", plain_text


    async def update_doctype(
        self,
        message: str,
        extracted_text: str,
        doctype: str,
        field_map: dict,
        record_name,
        file_name: str,
    ) -> dict:
        """Create or update a Service Entry / Fuel Entry.

        Flow:
        1. Single LLM call — extracts all fields from document + chat message,
           detects conflicts between the two sources in one shot.
        2. Resolve Link fields (Vendor, Vehicle) to exact Frappe names.
        3. Pre-save Link validation — remove bad links rather than hard-fail.
        4. Write to Frappe.
        """

        field_list = "\n".join(f"  - {fname}" for fname in sorted(set(field_map.values())))
        header_text = extracted_text[:8000]

        extract_prompt = (
            f"Extract values from this service/fuel document AND the user's chat message "
            f"for a Frappe '{doctype}' record.\n"
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
            f"or the letterhead at the top of the bill.\n"
            f"- If the user's chat message explicitly states a field value AND it differs "
            f"from the document, add a '_conflicts' key: a dict of "
            f"{{fieldname: {{\"bill\": <doc_value>, \"chat\": <chat_value>}}}}.\n"
            f"- Document value always takes priority unless '_conflicts' is present.\n"
            + (
                f"- _line_items: array of objects for each service row in the bill table. "
                f"Each object must have:\n"
                f"    \"service_task\": the exact Particulars/description text for that row,\n"
                f"    \"labor\": the labour amount for that row (0 if parts-only),\n"
                f"    \"parts\": the parts cost for that row (0 if labour-only).\n"
                f"  If only one total is shown per row, put it in labor.\n"
                if doctype == "Service Entry" else ""
            )
            + f"\nDOCUMENT:\n{header_text}\n\n"
            f"USER CHAT MESSAGE: {message}\n\n"
            f"JSON only, nothing else."
        )

        system_msgs = [
            {
                "role": "system",
                "content": "You extract structured data. Return only valid JSON, no explanation."
            }
        ]

        usage = {"input_tokens": 0, "output_tokens": 0}
        llm_fields: dict = {}
        raw_answer = ""

        try:
            raw_answer, _, usage = await self.provider.process_query(
                extract_prompt, None, system_msgs
            )
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
            _aiko_log("AIKO LLM field-extract error", str(e))

        _aiko_log("AIKO LLM field-extract result",
                  f"doctype={doctype}\nllm_fields={llm_fields}\nraw_answer={raw_answer[:500]}")

        conflicts: dict = llm_fields.pop("_conflicts", {}) or {}
        if conflicts:
            lines = [
                f"**Conflict detected** between what you typed and what was extracted "
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
            _aiko_log("AIKO conflict — awaiting user confirmation", f"conflicts={conflicts}")
            return {
                "content": "\n\n".join(lines),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "_conflicts": conflicts,
                "_pending_confirmation": True,
            }

        valid_fieldnames = set(field_map.values())
        _bad_vals = {None, "", "null", "N/A", "Unknown", "n/a", "unknown", "none", "None"}
        clean_fields = {
            k: v for k, v in llm_fields.items()
            if k in valid_fieldnames and v not in _bad_vals
        }

        # Pull line items out — child rows, not scalar fields
        line_items_rows = clean_fields.pop("_line_items", [])
        if not isinstance(line_items_rows, list):
            line_items_rows = []

        # Remove vendor if it looks wrong
        if "vendor" in clean_fields:
            bad_vendor_words = (
                "insurance", "job card", "free service", "paid service",
                "warranty", "scheduled", "emergency", "n/a", "unknown",
            )
            if any(w in clean_fields["vendor"].lower() for w in bad_vendor_words):
                _aiko_log("AIKO vendor rejected",
                          f"Rejected bad vendor value: {clean_fields['vendor']!r}")
                del clean_fields["vendor"]

        if not clean_fields:
            return {
                "content": (
                    f"❌ Could not extract any fields from **{file_name}** for a {doctype}.\n\n"
                    f"LLM returned: `{raw_answer[:300]}`\n\n"
                    f"Try uploading a clearer scan or enter the values manually."
                ),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }

        def _resolve_vendor(raw_value: str, is_service: bool) -> str:
            if not raw_value:
                return raw_value
            vendor_type_col = "is_service_vendor" if is_service else "is_fuel_vendor"

            def _norm(s):
                return re.sub(r'[\s\.\-_&,]+', '', s).upper()

            raw_norm = _norm(raw_value)
            all_vendors = frappe.db.sql(
                f"SELECT name FROM `tabVendor` WHERE {vendor_type_col} = 1",
                as_dict=True,
            )
            if not all_vendors:
                return raw_value

            for row in all_vendors:
                if _norm(row["name"]) == raw_norm:
                    return row["name"]

            for row in all_vendors:
                stored_norm = _norm(row["name"])
                if raw_norm in stored_norm or stored_norm in raw_norm:
                    return row["name"]

            raw_tokens = set(re.findall(r'[A-Z]{2,}', raw_norm))
            for row in all_vendors:
                stored_tokens = set(re.findall(r'[A-Z]{2,}', _norm(row["name"])))
                if raw_tokens and stored_tokens:
                    shorter = raw_tokens if len(raw_tokens) <= len(stored_tokens) else stored_tokens
                    longer = stored_tokens if shorter is raw_tokens else raw_tokens
                    if shorter.issubset(longer):
                        return row["name"]

            return raw_value

        def _resolve_vehicle(raw_value: str) -> str:
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
            resolved = _resolve_vendor(clean_fields["vendor"], is_service=(doctype == "Service Entry"))
            _aiko_log("AIKO vendor resolution",
                      f"raw={clean_fields['vendor']!r} resolved={resolved!r}")
            clean_fields["vendor"] = resolved

        if "vehicle" in clean_fields:
            resolved = _resolve_vehicle(clean_fields["vehicle"])
            _aiko_log("AIKO vehicle resolution",
                      f"raw={clean_fields['vehicle']!r} resolved={resolved!r}")
            clean_fields["vehicle"] = resolved

        # Cast and sanitize numeric fields
        _READ_ONLY_FIELDS = {"total_amount", "fuel_economy", "cost_per_meter",
                             "subtotal", "discount_amount", "tax_amount", "total"}
        for _ro in _READ_ONLY_FIELDS:
            clean_fields.pop(_ro, None)

        _float_fields = ("fuel_quantity", "price_per_litre",
                         "labor", "parts", "discount_value", "tax_value")
        for _fld in _float_fields:
            if _fld in clean_fields:
                try:
                    clean_fields[_fld] = float(str(clean_fields[_fld]).replace(",", ""))
                except (ValueError, TypeError):
                    pass

        if "odometer" in clean_fields:
            try:
                odo_val = str(clean_fields["odometer"]).replace(",", "").strip()
                clean_fields["odometer"] = int(float(odo_val)) if doctype == "Fuel Entry" else odo_val
            except (ValueError, TypeError):
                pass

        for _fld in ("parts", "discount_value", "tax_value"):
            try:
                if _fld in clean_fields and float(clean_fields[_fld]) == 0:
                    del clean_fields[_fld]
            except (ValueError, TypeError):
                pass

        _aiko_log("AIKO final merged fields",
                  f"doctype={doctype}\nclean_fields={clean_fields}")

        action_word_lower = message.lower()
        is_update_intent = any(w in action_word_lower for w in ("update", "save", "push"))
        is_create_intent = any(w in action_word_lower for w in ("create", "insert", "add", "make", "new"))

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
                    _aiko_log("AIKO auto-resolved record_name",
                              f"doctype={doctype} vehicle={vehicle_val} → record_name={record_name}")

        _DOCTYPE_LINK_FIELDS: dict[str, dict] = {
            "Fuel Entry": {
                "vehicle":   ("Vehicle",        True),
                "vendor":    ("Vendor",          False),
                "fuel_type": ("Fuel Type",       False),
                "unit":      ("Fuel Entry Unit", False),
                "trip":      ("Trip",            False),
            },
            "Service Entry": {
                "vehicle": ("Vehicle", True),
                "vendor":  ("Vendor",  False),
                "trip":    ("Trip",    False),
            },
        }

        link_fields: dict = _DOCTYPE_LINK_FIELDS.get(doctype, {
            "vendor": ("Vendor", False),
            "vehicle": ("Vehicle", True),
            "fuel_type": ("Fuel Type", False),
            "unit": ("Fuel Entry Unit", False),
            "trip": ("Trip", False),
        })

        _by_doctype: dict = defaultdict(list)
        for fieldname, (target_doctype, is_mandatory) in link_fields.items():
            if fieldname in clean_fields:
                _by_doctype[target_doctype].append((fieldname, clean_fields[fieldname], is_mandatory))

        missing_links: dict = {}
        for target_doctype, field_tuples in _by_doctype.items():
            vals = [v for _, v, _ in field_tuples]
            found_rows = frappe.db.sql(
                f"SELECT name FROM `tab{target_doctype}` WHERE UPPER(name) IN %s",
                ([v.upper() for v in vals],),
            )
            found_upper: dict = {r[0].upper(): r[0] for r in found_rows}
            for fieldname, val, is_mandatory in field_tuples:
                canonical = found_upper.get(val.upper() if val else "")
                if canonical:
                    clean_fields[fieldname] = canonical
                else:
                    _aiko_log("AIKO Link validation - not found",
                              f"{fieldname}={val!r} not in {target_doctype} mandatory={is_mandatory}")
                    if not is_mandatory:
                        clean_fields.pop(fieldname, None)
                    else:
                        missing_links[fieldname] = (val, target_doctype, is_mandatory)
                        del clean_fields[fieldname]

        _MANDATORY_FIELDS: dict[str, list] = {
            "Fuel Entry":    ["vehicle", "fuel_quantity", "fuel_date"],
            "Service Entry": ["vehicle", "odometer", "completion_date"],
        }
        mandatory_fields = _MANDATORY_FIELDS.get(doctype, [])
        empty_mandatory: list = [f for f in mandatory_fields if not clean_fields.get(f)]

        if missing_links or empty_mandatory:
            _lower_msg = message.lower()
            _bill_preferred = any(w in _lower_msg for w in ("take bill", "use bill", "from bill"))

            lines: list[str] = []

            if missing_links:
                lines.append(
                    f"**Cannot save {doctype} — the following linked records were not "
                    f"found in Frappe:**\n"
                )
                for fieldname, (val, target_doctype, is_mand) in missing_links.items():
                    label = fieldname.replace("_", " ").title()
                    mand_tag = " *(mandatory)*" if is_mand else ""
                    lines.append(
                        f"- **{label}**{mand_tag}: `{val}` — not found in **{target_doctype}**"
                    )
                lines.append("")

            if empty_mandatory:
                lines.append(
                    f"**Cannot save {doctype} — the following mandatory fields are "
                    f"missing and could not be extracted:**\n"
                )
                for fieldname in empty_mandatory:
                    label = fieldname.replace("_", " ").title()
                    lines.append(f"- **{label}** *(mandatory)*")
                lines.append("")

            _vehicle_missing_link = "vehicle" in missing_links
            _vehicle_empty = "vehicle" in empty_mandatory
            _has_vehicle_issue = _vehicle_missing_link or _vehicle_empty

            if _has_vehicle_issue:
                vehicle_val = missing_links["vehicle"][0] if _vehicle_missing_link else None
                if vehicle_val:
                    if _bill_preferred:
                        lines.append(
                            f"The vehicle **`{vehicle_val}`** from the bill does not exist "
                            f"in Frappe yet.\n\n"
                            f"Reply with one of:\n"
                            f"- **`yes, create vehicle`** — create `{vehicle_val}` first, "
                            f"then save the {doctype}\n"
                            f"- **`use <REG>`** — provide the correct existing vehicle registration\n"
                            f"- **`skip vehicle`** — save {doctype} without the vehicle field "
                            f"*(not recommended — it is mandatory)*"
                        )
                    else:
                        lines.append(
                            f"Vehicle **`{vehicle_val}`** was read from the bill but does "
                            f"not exist in Frappe.\n\n"
                            f"Reply with one of:\n"
                            f"- **`create vehicle {vehicle_val}`** — create the vehicle record "
                            f"first, then save the {doctype}\n"
                            f"- **`use <REG>`** — provide the correct existing vehicle registration\n"
                            f"- **`skip vehicle`** — save {doctype} without the vehicle field "
                            f"*(not recommended — it is mandatory)*"
                        )
                else:
                    lines.append(
                        f"**Vehicle** is mandatory for {doctype} but could not be "
                        f"extracted from the bill.\n\n"
                        f"Reply with one of:\n"
                        f"- **`vehicle <REG>`** — e.g. `vehicle TN45CA7234`\n"
                        f"- **`create vehicle <REG>`** — create the vehicle then save the {doctype}"
                    )

                other_missing = {k: v for k, v in missing_links.items() if k != "vehicle"}
                if other_missing:
                    lines.append("")
                    lines.append(
                        "For the other missing linked records:\n"
                        "- Create them in Frappe first and retry, **or**\n"
                        "- Reply with the correct existing record name for each field, **or**\n"
                        "- Reply **`skip <fieldname>`** to omit a non-mandatory field."
                    )
            else:
                lines.append(
                    "To proceed:\n"
                    "- Create the missing records in Frappe first, then retry, **or**\n"
                    "- Reply with the correct existing record names, **or**\n"
                    "- Reply **`skip <fieldname>`** to omit a non-mandatory field."
                )

            _aiko_log("AIKO Link/mandatory validation — prompting user",
                      f"missing_links={missing_links}\nempty_mandatory={empty_mandatory}")

            return {
                "content": "\n".join(lines),
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
            _aiko_log(f"AIKO {doctype} save error", frappe.get_traceback())
            return {
                "content": (
                    f"Failed to save the {doctype} record: `{e}`\n\n"
                    f"Fields attempted:\n"
                    + "\n".join(f"- **{k}**: {v}" for k, v in clean_fields.items())
                ),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }

        field_rows = "\n".join(f"| {k} | {v} |" for k, v in clean_fields.items())
        if line_items_rows:
            field_rows += f"\n| line items | {len(line_items_rows)} row(s) added to Service Line Items |"

        try:
            frappe.publish_realtime("list_update", {"doctype": doctype}, after_commit=True)
        except Exception:
            pass

        saved_record = doc.name
        final_answer = (
            f"Successfully {action_done} in **{doctype}**.\n\n"
            f"**Record:** `{saved_record}`\n\n"
            f"| Field | Value |\n|---|---|\n{field_rows}\n\n"
        )

        _vendor_dropped = (
            "vendor" in link_fields
            and "vendor" not in clean_fields
            and "vendor" not in missing_links
        )
        if _vendor_dropped:
            final_answer += (
                f"\n\n**Vendor** was read from the bill but could not be matched "
                f"in Frappe and was not saved. "
                f"Reply with `vendor <exact name>` to update it on `{saved_record}`."
            )

        return {
            "content": final_answer,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "doctype_updated": f"{doctype}: {saved_record}",
        }