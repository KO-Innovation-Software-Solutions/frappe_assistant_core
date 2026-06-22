import ast
import asyncio
import json as _json
import re
from typing import Optional
import urllib.parse

import frappe
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from frappe.utils import get_url

from .providers import OpenAIProvider, OllamaProvider

MAX_HISTORY_MESSAGES = 20
# Cap how much extracted text we hand the LLM in one go (separate from the
# providers' own per-tool-result truncation — this is for the up-front
# deterministic extraction, which can be the entire document at once).
MAX_EXTRACTED_CHARS = 16000


def _stringify_mcp_content(content) -> str:
    """Pull clean text out of an MCP CallToolResult.content list.

    Mirrors the same helper in providers/ollama.py and providers/openai.py —
    duplicated here (rather than imported) so this module doesn't depend on
    provider-internal names. `content` is normally a list of TextContent
    Pydantic objects; str() on those returns their verbose repr instead of
    the actual text, so we pull `.text` explicitly where present.
    """
    if isinstance(content, list):
        parts = []
        for item in content:
            text = getattr(item, "text", None)
            parts.append(text if text is not None else str(item))
        return "\n".join(parts)
    return str(content)


def _trailing_label(words: list, max_words: int = 8) -> tuple:
    """From a list of words ending right before a colon, peel off the
    trailing run that looks like a field label and return (label, rest).

    Stops as soon as it hits a word containing 2+ digits, since in a
    form/invoice-style document a digit run is almost always part of a
    VALUE (a date, an amount, a registration/chassis number) and never
    part of a label like 'Job Card No.' or 'Customer GSTIN'.
    """
    label_words = []
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
    """Return True if `text` looks like a field label rather than a value.

    A label is short (≤ max_words words), contains no digit runs of 4+
    characters (those are codes/amounts/dates), and does not look like a
    street address (no digits at the start of a word that precede a word
    like Street/Road/Nagar/Colony etc).
    """
    words = text.strip().split()
    if len(words) > max_words:
        return False
    # digit runs of 4+ chars → value territory (phone, pin, amount, chassis)
    if any(re.search(r"\d{4,}", w) for w in words):
        return False
    # starts with a digit → likely a number value
    if words and re.match(r"^\d", words[0]):
        return False
    return True


def _extract_line_items_table(text: str):
    """Detect and extract a line-items table from extracted PDF text.

    PDF text extraction rarely preserves clean pipe delimiters. Instead the
    table header keywords (Sr, HSN, Particulars, Qty, Rate, Amount) and
    numeric data rows end up concatenated into a single run of text.

    Strategy:
    1. Try pipe-delimited detection first (clean extractions).
    2. Fall back to keyword-boundary detection: find where the table header
       starts (Sr / HSN / Particulars) and where the footer starts
       (Sub Total / Grand Total / Tax Payable), then extract everything
       in between as a raw block returned as [["_raw_", raw_block]].
       The caller renders this as a styled section rather than trying to
       re-parse columns that are already lost in the flat extraction.

    Returns (pre_text, table_rows, post_text).
    table_rows is a list-of-lists (clean pipe case),
    [["_raw_", raw_string]] (messy fallback), or None if nothing detected.
    """
    # ---- 1. Pipe-delimited (clean) ----------------------------------------
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

    # ---- 2. Keyword-boundary detection (messy/flat extraction) -------------
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
    """Reformat flat 'Label : Value' style text (job cards, invoices, forms)
    into a styled responsive HTML card, purely as a presentation step.

    Improvements over the plain-markdown version:
    • Responsive layout — label column uses max-content width so it never
      wraps on narrow screens.
    • Label bleed guard — values that are too long or start with a digit are
      never mis-classified as labels, so street addresses / amounts stay in
      the value column where they belong.
    • Line-items table detection — if the extracted text contains a
      pipe-delimited table block (Sr | Particulars | Qty | Rate | Amount …),
      it is rendered as a proper <table> instead of being crammed into a
      single value cell.
    • Empty-value styling — "not detected" shown in muted italic.

    Returns None when the text doesn't look like a label:value form.
    """
    import html as _html

    def esc(s: str) -> str:
        return _html.escape(str(s or ""), quote=True)

    # ------------------------------------------------------------------ #
    # 1. Separate any embedded line-items table from the header/footer text
    # ------------------------------------------------------------------ #
    pre_text, line_rows, post_text = _extract_line_items_table(text)

    # ------------------------------------------------------------------ #
    # 2. Parse label:value pairs from the non-table portions
    # ------------------------------------------------------------------ #
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

    # Need at least min_pairs OR a detected line-items table to bother rendering
    if len(pairs) < min_pairs and not line_rows:
        return None

    # ------------------------------------------------------------------ #
    # 3. Build HTML
    # ------------------------------------------------------------------ #
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

    # Field rows
    field_rows_html = ""
    for f, v in pairs:
        f_clean = f.replace("\n", " ").strip()
        v_clean = (v or "").replace("\n", " ").strip()
        if v_clean:
            v_cell = f'<td>{esc(v_clean)}</td>'
        else:
            v_cell = '<td class="ak-nil">not detected</td>'
        field_rows_html += f'<tr><td class="ak-lbl">{esc(f_clean)}</td>{v_cell}</tr>\n'

    # Line items table
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
            item_rows = ""
            for row in data_rows:
                tds = ""
                for cell in row:
                    num_cls = ' class="ak-num"' if re.match(r'^[\d,.\s]+$', cell.strip()) else ''
                    tds += f'<td{num_cls}>{esc(cell)}</td>'
                item_rows += f"<tr>{tds}</tr>" + "\n"
            line_items_html = (
                '<tr><td colspan="2" style="padding:0">'
                '<div class="ak-sec">Line Items</div>'
                '<div class="ak-wrap">'
                '<table class="ak-t" style="min-width:520px">'
                f'<thead><tr>{th_cells}</tr></thead>'
                f'<tbody>{item_rows}</tbody>'
                '</table></div></td></tr>'
            )
    html_out = (
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

    return html_out


def _parse_extraction_result(raw_text: str) -> tuple:
    """Parse the JSON dict the extract_file_content tool returns and pull
    out just the human-readable content, instead of feeding the model the
    whole {"success": ..., "content": ..., "file_info": {...}} wrapper.

    Returns (display_content, ok, plain_text) where:
      - display_content  is the HTML card (or plain text if structuring was skipped)
      - ok               is False if extraction failed or came back empty
      - plain_text       is ALWAYS the original raw extracted text with no HTML —
                         used by the DocType update path so regex / LLM never see HTML
    """
    try:
        data = _json.loads(raw_text)
    except Exception:
        # json.loads failed — BaseTool may have serialized the result dict with
        # str() instead of json.dumps(), producing Python repr (single quotes,
        # True/False instead of true/false). Try ast.literal_eval before giving
        # up, so we can still pull content out of a repr-encoded dict.
        try:
            data = ast.literal_eval(raw_text)
        except Exception:
            # Genuinely plain text (or unparseable) — use as-is.
            text = raw_text or ""
            return text, bool(text.strip()), text

    if isinstance(data, dict):
        # BaseTool.execute() return values are wrapped by the MCP layer into
        # {"success": <bool>, "result": <the actual dict from execute()>}.
        # The old code read "content" from the outer wrapper — which never
        # has a "content" key — so it always fell through to the
        # "No text was detected" branch even when OCR succeeded.
        # Fix: unwrap the "result" envelope when present so we read the
        # inner dict that actually carries "content", "tables", "message" etc.
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

        # Keep the original plain text for the DocType update path (regex/LLM).
        # _structure_flat_text produces HTML — that's great for display but
        # breaks regex patterns and confuses the LLM with tags and CSS.
        plain_text = content

        warning = inner.get("warning")
        if warning:
            plain_text = f"{plain_text}\n\n[Note: {warning}]"

        # Reformat into a Field/Value table when the text looks like a
        # form/invoice/job-card (lots of "Label : Value" pairs) rather than
        # prose. This is a pure presentation step — it never changes plain_text.
        structured = _structure_flat_text(content)
        display_content = structured if structured else content
        if warning:
            display_content = f"{display_content}\n\n[Note: {warning}]"

        return display_content, True, plain_text

    text = str(data)
    return text, bool(text.strip()), text


def _truncate(text: str, limit: int = MAX_EXTRACTED_CHARS) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n\n[...truncated, {omitted} more characters omitted...]"


class AikoAgent:
    """Unified MCP Agent for Frappe"""

    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.settings = frappe.get_single("Assistant Core Settings")
        provider_name = self.settings.get("llm_provider", "ollama").lower()
        if provider_name == "openai":
            self.provider = OpenAIProvider(self.settings)
        else:
            self.provider = OllamaProvider(self.settings)
        self.session: Optional[ClientSession] = None
        self._streams_context = None
        self._session_context = None

        self.messages = [
            {
                "role": "system",
                "content": (
                    "You are an AI assistant integrated with Frappe via MCP tools. "
                    "When you receive a file extraction result, you MUST present the "
                    "extracted content directly and completely in your reply — all fields, "
                    "all table rows, all amounts. Never say a custom parser or script is "
                    "needed. Never say you cannot process the content. Never suggest the "
                    "user install tools or write code. The extraction is already done — "
                    "your job is to read it and present it clearly.\n\n"
                    "BEFORE calling any tool, always check whether the question can already "
                    "be answered from THIS CONVERSATION's own history — for example, a "
                    "previously extracted file's text, a table you already presented, "
                    "amounts, names, or line items shown earlier. If the user asks a "
                    "follow-up about something already extracted or discussed (e.g. 'item "
                    "details', 'the prices', 'how many', 'total'), answer directly from the "
                    "earlier content in this conversation. Do NOT call a tool just because a "
                    "word in the question (like 'item') resembles the name of a Frappe "
                    "DocType or report — the user is almost always referring to data already "
                    "in this conversation, not asking you to look up Frappe's Item/Stock "
                    "module. Only call a tool when the requested information is genuinely "
                    "not available anywhere earlier in this conversation.\n\n"
                    "For all other tasks where the answer truly isn't already in this "
                    "conversation, use available MCP tools as needed and answer accurately."
                ),
            }
        ]
        self._load_history()

    def _load_history(self):
        session_name = frappe.db.get_value(
            "Aiko Chat Session", {"thread_id": self.thread_id}, "name"
        )
        if not session_name:
            return
        # order_by must be "creation desc" here — we want the MOST RECENT N
        # messages. With "asc" + a fixed limit, any session with more than
        # MAX_HISTORY_MESSAGES messages would silently fetch the OLDEST N
        # instead, meaning a just-uploaded file's extraction (the most
        # recent message) could be dropped from context entirely on a
        # long-running thread — the model would have no idea a file was
        # ever discussed. We fetch desc, then reverse back to chronological
        # order before adding to the prompt.
        past_messages = frappe.db.get_list(
            "Aiko Chat Message",
            filters={
                "session": session_name,
                "role": ["in", ["user", "assistant"]],
            },
            fields=["role", "content"],
            order_by="creation desc",
            limit=MAX_HISTORY_MESSAGES,
        )
        for msg in reversed(past_messages):
            self.messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

    def _trim_history(self):
        if len(self.messages) > MAX_HISTORY_MESSAGES:
            system_prompt = self.messages[0]
            self.messages = [system_prompt] + self.messages[-MAX_HISTORY_MESSAGES:]

    async def connect_to_streamable_http_server(self):
        """Connect to the Frappe MCP server"""
        user = frappe.session.user
        user_doc = frappe.get_doc("User", user)
        api_key = user_doc.api_key
        api_secret = user_doc.get_password("api_secret")

        mcp_url = get_url("/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp")
        parsed = urllib.parse.urlparse(mcp_url)
        internal_url = mcp_url.replace(parsed.hostname, "127.0.0.1")
        if not parsed.port:
            internal_url = internal_url.replace(
                "127.0.0.1", f"127.0.0.1:{frappe.conf.webserver_port or 8000}"
            )

        headers = {
            "Authorization": f"token {api_key}:{api_secret}",
            "Host": parsed.hostname,
        }

        self._streams_context = streamablehttp_client(url=internal_url, headers=headers)
        read_stream, write_stream, _ = await self._streams_context.__aenter__()

        self._session_context = ClientSession(read_stream, write_stream)
        self.session = await self._session_context.__aenter__()

        await self.session.initialize()

    async def cleanup(self):
        try:
            if self._session_context:
                await self._session_context.__aexit__(None, None, None)
        except Exception:
            pass
        try:
            if self._streams_context:
                await self._streams_context.__aexit__(None, None, None)
        except Exception:
            pass

    def _build_multimodal_message(
        self, message: str, file_data: str, file_type: str, file_name: str
    ) -> dict:
        """
        Build a user message in OpenAI/Ollama multimodal format.

        OpenAI vision format:
          content: [
            {"type": "image_url", "image_url": {"url": "data:<mime>;base64,<data>"}},
            {"type": "text", "text": "..."},
          ]

        PDF / non-image: Ollama does not support document blocks natively,
        so we embed a note in the text and skip the binary attachment.
        Vision-capable models (llava, llama3.2-vision, etc.) only handle images.
        """
        if file_type.startswith("image/"):
            return {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{file_type};base64,{file_data}",
                        },
                    },
                    {"type": "text", "text": message},
                ],
            }
        else:
            # For PDFs and other documents, fall back to text-only with a note.
            # If you switch to an OpenAI provider that supports the document block
            # (e.g. Claude via Bedrock), override this branch in OpenAIProvider instead.
            return {
                "role": "user",
                "content": (
                    f"[Attached file: {file_name} ({file_type}) — "
                    f"binary content omitted; please process based on the description below]\n\n"
                    f"{message}"
                ),
            }

    async def _process_query(self, query: str) -> dict:
        await self.connect_to_streamable_http_server()
        try:
            result = await self.provider.process_query(query, self.session, self.messages)
            final_answer, updated_messages, usage = result

            if not final_answer:
                final_answer = "I'm sorry, I couldn't generate a response. Please try again."
                frappe.log_error(
                    title="AIKO Empty LLM Response",
                    message=(
                        f"Provider returned an empty final answer with no tool result to "
                        f"fall back on. thread_id={self.thread_id}, "
                        f"provider={type(self.provider).__name__}, "
                        f"message_count={len(updated_messages)}"
                    ),
                )

            self.messages = updated_messages
            self._trim_history()

            return {
                "content": final_answer,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }
        finally:
            await self.cleanup()

    def invoke(self, message: str) -> dict:
        """Synchronous wrapper for plain text queries."""
        return asyncio.run(self._process_query(message))

    def invoke_with_file(
        self, message: str, file_data: str, file_type: str, file_name: str
    ) -> dict:
        """Synchronous wrapper for file/vision queries."""
        return asyncio.run(
            self._process_query_with_file(message, file_data, file_type, file_name)
        )

    def invoke_with_file_extraction(
        self, message: str, file_url: str, operation: str, file_name: str
    ) -> dict:
        """Synchronous wrapper for document (PDF/image/CSV/etc.) queries that
        go through the extract_file_content MCP tool.

        Unlike the old approach of telling the LLM "you must call
        extract_file_content first" via a prompt instruction, this calls the
        tool directly in code before the LLM is ever invoked. A model
        (especially a smaller local one) can and does ignore step-by-step
        prompt instructions under tool pressure — e.g. pattern-matching
        "items" in the user's question to an unrelated "Invoice" DocType
        lookup instead of extracting the uploaded file. Making extraction
        deterministic removes that failure mode entirely: the model is only
        ever asked to answer using text we hand it, never asked to decide
        whether/how to extract.
        """
        return asyncio.run(
            self._process_file_extraction_query(message, file_url, operation, file_name)
        )

    async def _extract_file_deterministically(self, file_url: str, operation: str) -> tuple:
        """Always call extract_file_content directly via the MCP session.

        Returns (display_content, note, plain_text) where:
          display_content  — HTML card or plain text, for presenting to the user
          note             — empty string, or a notice that OCR retry was used
          plain_text       — raw extracted text with NO HTML, for regex/LLM field extraction
        """
        try:
            result = await self.session.call_tool(
                "extract_file_content", {"file_url": file_url, "operation": operation}
            )
            raw_text = _stringify_mcp_content(result.content)
            # LOG: record exactly what the MCP tool returned so failures are visible
            frappe.log_error(
                title="AIKO extract_file_content raw_text",
                message=f"file_url={file_url} op={operation}\nraw_text={raw_text[:2000]}"
            )
            display_content, ok, plain_text = _parse_extraction_result(raw_text)
            frappe.log_error(
                title="AIKO _parse_extraction_result",
                message=f"ok={ok} plain_text[:500]={plain_text[:500] if plain_text else repr(plain_text)}"
            )
        except Exception as e:
            frappe.log_error(
                title="AIKO extract_file_content EXCEPTION",
                message=f"file_url={file_url} op={operation} error={e}\n{frappe.get_traceback()}"
            )
            err = f"[Extraction error: {e}]"
            return err, "", err

        # If a plain text extraction came back empty (e.g. a scanned PDF
        # that slipped through), automatically retry with OCR rather than
        # surfacing an empty result.
        if operation == "extract" and not ok:
            try:
                ocr_result = await self.session.call_tool(
                    "extract_file_content", {"file_url": file_url, "operation": "ocr"}
                )
                ocr_raw = _stringify_mcp_content(ocr_result.content)
                ocr_display, ocr_ok, ocr_plain = _parse_extraction_result(ocr_raw)
                frappe.log_error(
                    title="AIKO OCR retry result",
                    message=f"ocr_ok={ocr_ok} plain_text[:500]={ocr_plain[:500] if ocr_plain else repr(ocr_plain)}"
                )
                if ocr_ok:
                    note = "(Text extraction was empty; automatically retried with OCR.)\n\n"
                    return ocr_display, note, ocr_plain
            except Exception as e2:
                frappe.log_error(title="AIKO OCR retry EXCEPTION", message=str(e2))

        return display_content, "", plain_text

    # ------------------------------------------------------------------ #
    # DocType field maps: extracted label → Frappe fieldname
    # These mirror the fields defined in service_entry.json / fuel_entry.json.
    # Only writable, non-read-only, meaningful fields are listed.
    # ------------------------------------------------------------------ #
    _SERVICE_ENTRY_FIELD_MAP = {
        # vehicle
        "vehicle": "vehicle",
        "vehicle no": "vehicle",
        "vehicle number": "vehicle",
        "reg no": "vehicle",
        "registration": "vehicle",
        # dates
        "start date": "start_date",
        "start": "start_date",
        "completion date": "completion_date",
        "completion": "completion_date",
        "end date": "completion_date",
        "date": "completion_date",
        # type / priority
        "type": "repair_priority_class",
        "repair type": "repair_priority_class",
        "priority": "repair_priority_class",
        # odometer
        "odometer": "odometer",
        "km": "odometer",
        "mileage": "odometer",
        # vendor
        "vendor": "vendor",
        "workshop": "vendor",
        "garage": "vendor",
        # financials
        "labor": "labor",
        "labour": "labor",
        "parts": "parts",
        "discount type": "discount_type",
        "discount value": "discount_value",
        "tax type": "tax_type",
        "tax value": "tax_value",
    }

    _FUEL_ENTRY_FIELD_MAP = {
        # vehicle
        "vehicle": "vehicle",
        "vehicle no": "vehicle",
        "vehicle number": "vehicle",
        "reg no": "vehicle",
        "registration": "vehicle",
        # date
        "fuel date": "fuel_date",
        "date": "fuel_date",
        "refuel date": "fuel_date",
        # odometer
        "odometer": "odometer",
        "km": "odometer",
        "mileage": "odometer",
        # fuel
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
        # vendor
        "vendor": "vendor",
        "station": "vendor",
        "fuel station": "vendor",
        "petrol station": "vendor",
    }

    # DocType aliases the user might say in their message
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

    def _detect_doctype_update_intent(self, message: str):
        """Return (doctype_name, field_map, record_name_hint) if the user wants
        to create/update a Service Entry or Fuel Entry. record_name_hint is the
        existing record name if the user said 'update SE-2024-00001', else None.

        Returns None if no matching intent found.
        """
        lower = message.lower()
        action_words = ("create", "save", "insert", "add", "update", "push", "submit", "make")
        if not any(w in lower for w in action_words):
            return None

        for alias, (doctype, field_map) in self._DOCTYPE_ALIASES.items():
            if alias in lower:
                # Check if a specific record name was given (for update)
                # Pattern: SE-YYYY-##### or FE-YYYY-#####
                record_match = re.search(
                    r'\b(SE-\d{4}-\d+|FE-\d{4}-\d+)\b', message, re.IGNORECASE
                )
                record_name = record_match.group(1).upper() if record_match else None
                return doctype, field_map, record_name

        return None

    async def _update_doctype_from_extraction(
        self,
        message: str,
        extracted_text: str,
        doctype: str,
        field_map: dict,
        record_name,
        file_name: str,
    ) -> dict:
        """Deterministically update or create a Service Entry / Fuel Entry
        from the extracted file text.

        Flow:
        1. Regex pre-parser extracts key fields directly from the text — no LLM
           needed for common patterns (Regn. No, Job Card Date, Kms, Gross Amount).
        2. LLM is called with ONLY the first 2000 chars of extracted text and
           asked for a compact JSON — this avoids context-window overflow on
           small local models that return empty output on large inputs.
        3. LLM result is merged with regex result (regex wins on vehicle to avoid
           chassis number confusion; LLM fills in anything regex missed).
        4. Write to Frappe in code. No tool-call gambling.
        """
        # ------------------------------------------------------------------ #
        # STEP 1: Regex pre-parser — extract fields without the LLM.         #
        # Works on raw extracted text directly; handles the Tata/service      #
        # invoice format seen in the wild.                                    #
        # ------------------------------------------------------------------ #
        def _regex_extract(text: str, dt: str) -> dict:
            fields = {}

            # --- Vehicle Registration Number ---
            # Must match BEFORE chassis so we never accidentally use chassis.
            # Reg numbers are short: 2 letters + 2 digits + 1-2 letters + 1-4 digits
            # Accept both "Vehicle Reg. No" and plain "Regn. No" labels.
            regn_match = re.search(
                r'(?:Vehicle\s*Reg(?:n|istration)?\.?\s*No\.?\s*[:\-]?\s*|'
                r'Reg(?:n|istration)?\s*No\.?\s*[:\-]?\s*)'
                r'([A-Z]{2}\d{2}[A-Z]{1,3}\d{1,4})',
                text, re.IGNORECASE
            )
            if regn_match:
                fields["vehicle"] = regn_match.group(1).upper()

            # --- Odometer / Kms ---
            kms_match = re.search(
                r'(?:Kms?\.?\s*[:\-]?\s*|Odometer\s*[:\-]?\s*)(\d[\d,]*)',
                text, re.IGNORECASE
            )
            if kms_match:
                fields["odometer"] = kms_match.group(1).replace(",", "")

            if dt == "Service Entry":
                # --- Job Card / Completion Date ---
                date_match = re.search(
                    r'(?:Job\s*Card\s*Date|Completion\s*Date|Service\s*Date)\s*[:\-]?\s*'
                    r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
                    text, re.IGNORECASE
                )
                if date_match:
                    raw_date = date_match.group(1)
                    # Normalise DD/MM/YYYY or DD-MM-YYYY → YYYY-MM-DD 00:00:00
                    parts = re.split(r'[/\-]', raw_date)
                    if len(parts) == 3:
                        d, m, y = parts
                        if len(y) == 2:
                            y = "20" + y
                        try:
                            fields["completion_date"] = f"{y}-{int(m):02d}-{int(d):02d} 00:00:00"
                            # Also set start_date to the same value if not set separately
                            fields.setdefault("start_date", fields["completion_date"])
                        except ValueError:
                            pass

                # --- Repair type from Service Request Type ---
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

                # --- Labour amount ---
                # The invoice uses both "Final Labour Invoice Amount" and "Labour Amount"
                labour_match = re.search(
                    r'(?:Final\s*Labo(?:u)?r\s*Invoice\s*Amount|Labo(?:u)?r\s*(?:Invoice\s*)?Amount)'
                    r'\s*[:\-]?\s*([\d,]+\.?\d*)',
                    text, re.IGNORECASE
                )
                if labour_match:
                    fields["labor"] = labour_match.group(1).replace(",", "")
                else:
                    # Fallback: use Gross Amount if labour specifically not found
                    gross_match = re.search(
                        r'Gross\s*Amount\s*[:\-]?\s*([\d,]+\.?\d*)',
                        text, re.IGNORECASE
                    )
                    if gross_match:
                        fields["labor"] = gross_match.group(1).replace(",", "")

                # --- Parts amount (Final Parts Invoice Amount) ---
                parts_match = re.search(
                    r'(?:Final\s*Parts\s*Invoice\s*Amount|Parts\s*Amount)\s*[:\-]?\s*([\d,]+\.?\d*)',
                    text, re.IGNORECASE
                )
                if parts_match:
                    val = parts_match.group(1).replace(",", "")
                    try:
                        if float(val) > 0:
                            fields["parts"] = val
                        # Explicitly skip setting parts=0 — Frappe treats missing
                        # as 0, but an explicit 0 can trigger validation on some
                        # builds and is meaningless data.
                    except ValueError:
                        pass

                # --- Tax amount ---
                tax_match = re.search(
                    r'(?:Total\s*Tax|Tax\s*Amount)\s*[:\-]?\s*([\d,]+\.?\d*)',
                    text, re.IGNORECASE
                )
                if tax_match:
                    fields["tax_value"] = tax_match.group(1).replace(",", "")
                    fields["tax_type"] = "Fixed"

                # --- Vendor (dealer / workshop name) ---
                # Tata service invoices say "For SRI LAKSHMI MOTORS" near the
                # Authorised Signatory block at the bottom of the page.
                # We search from the END of the text so we pick up the signature
                # area rather than an earlier "For <something>" occurrence like
                # "For Insurance Job Card" or "For Free Service".
                # Only accept names ending in MOTORS / AUTOMOBILES / AUTOMOTIVES
                # / AUTO / AGENCIES — these are unambiguous dealer suffixes.
                vendor_match = re.search(
                    r'For\s+([A-Z][A-Z\s]{2,50}?'
                    r'(?:MOTORS|AUTOMOBILES?|AUTOMOTIVES?|AUTO|AGENCIES|DEALERSHIP))',
                    text[-3000:],           # search only the last 3000 chars (signature area)
                    re.IGNORECASE
                )
                if vendor_match:
                    fields["vendor"] = vendor_match.group(1).strip().title()
                else:
                    # Fallback: look for "Dealer Name :" or "Workshop :" label anywhere
                    dealer_match = re.search(
                        r'(?:Dealer\s*Name|Workshop\s*Name?)\s*[:\-]\s*(.+?)(?:\n|$)',
                        text, re.IGNORECASE
                    )
                    if dealer_match:
                        fields["vendor"] = dealer_match.group(1).strip().title()

            elif dt == "Fuel Entry":
                # --- Fuel date ---
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

                # --- Fuel quantity ---
                qty_match = re.search(
                    r'(?:Qty|Quantity|Litres?|Liters?)\s*[:\-]?\s*([\d]+\.?\d*)',
                    text, re.IGNORECASE
                )
                if qty_match:
                    fields["fuel_quantity"] = qty_match.group(1)

                # --- Price per litre ---
                ppl_match = re.search(
                    r'(?:Price\s*[Pp]er\s*[Ll]i(?:t(?:re|er))?|Rate)\s*[:\-]?\s*([\d]+\.?\d*)',
                    text, re.IGNORECASE
                )
                if ppl_match:
                    fields["price_per_litre"] = ppl_match.group(1)

            return fields

        regex_fields = _regex_extract(extracted_text, doctype)
        frappe.log_error(
            title="AIKO regex_extract result",
            message=f"doctype={doctype} file={file_name}\nregex_fields={regex_fields}"
        )

        # ------------------------------------------------------------------ #
        # STEP 2: LLM call — only the first 2000 chars of extracted text.    #
        # Small models handle short inputs reliably; the regex already got    #
        # the most important fields so the LLM just fills in the gaps.       #
        # ------------------------------------------------------------------ #
        field_list = "\n".join(f"  - {fname}" for fname in sorted(set(field_map.values())))
        # Send only the document header (first 3000 chars) — this is where all
        # the key fields live. The line-items table (which blows context) is at
        # the bottom and not needed for the header fields.
        # extracted_text here is ALWAYS plain text (never HTML) — see callers.
        header_text = extracted_text[:3000]

        extract_prompt = (
            f"Extract values from this service/fuel document for a Frappe '{doctype}' record.\n"
            f"Return ONLY a JSON object with these keys (omit any you can't find):\n"
            f"{field_list}\n\n"
            f"RULES (follow exactly):\n"
            f"- vehicle: REGISTRATION NUMBER only (e.g. TN45CA7234 — 2 letters, 2 digits, "
            f"1-3 letters, 1-4 digits). This is labelled 'Vehicle Regn. No' on the document. "
            f"NEVER use Chassis No (17-char VIN starting with letters like MAT...).\n"
            f"- Dates: YYYY-MM-DD 00:00:00 format. 'Job Card Date' maps to completion_date.\n"
            f"- Numbers: digits only, no units or commas.\n"
            f"- repair_priority_class: if Service Request Type is 'Paid Service' → 'Non Scheduled'; "
            f"'Warranty' → 'Scheduled'; 'Emergency' → 'Emergency'\n"
            f"- discount_type / tax_type: 'Percentage %' or 'Fixed'\n"
            f"- labor: the 'Final Labour Invoice Amount' or 'Gross Amount' (digits only)\n"
            f"- vendor: look for 'For <NAME>' near the signature area (the workshop name)\n\n"
            f"DOCUMENT:\n{header_text}\n\n"
            f"JSON only, nothing else."
        )

        system_msg = {"role": "system", "content": "You extract structured data. Return only valid JSON, no explanation."}
        llm_messages = [system_msg, {"role": "user", "content": extract_prompt}]

        usage = {"input_tokens": 0, "output_tokens": 0}
        llm_fields = {}
        try:
            # Pass session=None so NO MCP tools are available to the LLM for
            # this call. We want a pure text completion (JSON extraction only).
            # With tools enabled, OpenAI will call Frappe tools instead of
            # returning JSON, and those tools can return chassis numbers or
            # unrelated data from the database.
            result = await self.provider.process_query_with_messages(None, llm_messages)
            raw_answer, _, usage = result

            if raw_answer and raw_answer.strip():
                jtext = raw_answer.strip()
                jtext = re.sub(r'^```(?:json)?', '', jtext, flags=re.MULTILINE).strip()
                jtext = re.sub(r'```$', '', jtext, flags=re.MULTILINE).strip()
                bm = re.search(r'\{.*\}', jtext, re.DOTALL)
                if bm:
                    jtext = bm.group(0)
                try:
                    llm_fields = _json.loads(jtext)
                except Exception:
                    try:
                        llm_fields = ast.literal_eval(jtext)
                    except Exception:
                        llm_fields = {}
        except Exception as e:
            frappe.log_error(title="AIKO LLM field-extract error", message=str(e))
            llm_fields = {}

        # ------------------------------------------------------------------ #
        # STEP 3: Merge — regex wins on vehicle (chassis confusion guard);   #
        # LLM fills anything regex missed; filter to valid fieldnames only.  #
        # ------------------------------------------------------------------ #
        frappe.log_error(
            title="AIKO LLM field-extract result",
            message=f"doctype={doctype}\nllm_fields={llm_fields}\nraw_answer={raw_answer[:500] if 'raw_answer' in dir() else 'N/A'}"
        )
        valid_fieldnames = set(field_map.values())
        merged = {}
        # Start with LLM fields
        for k, v in llm_fields.items():
            if k in valid_fieldnames and v not in (None, "", "null", "N/A", "Unknown"):
                merged[k] = v
        # Regex fields overwrite — they are more trustworthy for vehicle/date/odometer/vendor.
        # Critically, vendor extracted by regex is anchored to the signature area of the doc
        # (last 3000 chars) while the LLM may grab any "For X" phrase from anywhere.
        for k, v in regex_fields.items():
            if k in valid_fieldnames and v not in (None, "", "null"):
                merged[k] = v

        # Post-merge: remove vendor if it looks wrong (contains common non-vendor words)
        if "vendor" in merged:
            bad_vendor_words = ("insurance", "job card", "free service", "paid service",
                                "warranty", "scheduled", "emergency", "n/a", "unknown")
            if any(w in merged["vendor"].lower() for w in bad_vendor_words):
                frappe.log_error(
                    title="AIKO vendor rejected",
                    message=f"Rejected bad vendor value: {merged['vendor']!r}"
                )
                del merged["vendor"]

        if not merged:
            # Both regex and LLM failed — surface a clear error with what we have
            return {
                "content": (
                    f"❌ Could not extract any fields from **{file_name}** for a {doctype}.\n\n"
                    f"Regex found: `{regex_fields}`\n"
                    f"LLM returned: `{raw_answer[:300] if 'raw_answer' in dir() else '(no response)'}`\n\n"
                    f"Try uploading a clearer scan or enter the values manually."
                ),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }

        clean_fields = merged

        # ------------------------------------------------------------------ #
        # STEP 3b: Resolve Link fields — values extracted from documents are  #
        # human-readable names (e.g. "SRI LAKSHMI MOTORS") but Frappe Link   #
        # fields need the exact document `name`. Do a case-insensitive lookup #
        # and substitute the real name before saving.                         #
        # ------------------------------------------------------------------ #
        def _resolve_vendor(raw_value: str, is_service: bool) -> str:
            """Resolve extracted vendor text to the exact Frappe Vendor document name.

            Uses raw SQL so there is no risk of frappe.get_all combining filters
            incorrectly. Tries four strategies in order:
            1. Exact match (fastest, works when casing is perfect)
            2. Strip all spaces and compare — catches "SRILAKSHMI" vs "SRI LAKSHMI"
            3. Fuzzy token match — every word in raw_value appears in the db name
            4. First available vendor with the right type flag (last resort)
            """
            if not raw_value:
                return raw_value

            vendor_type_col = "is_service_vendor" if is_service else "is_fuel_vendor"

            # 1. Exact
            exact = frappe.db.get_value("Vendor", {"name": raw_value}, "name")
            if exact:
                return exact

            # 2. Space-stripped comparison via SQL REPLACE
            stripped = raw_value.replace(" ", "").upper()
            rows = frappe.db.sql(
                f"""SELECT name FROM `tabVendor`
                    WHERE {vendor_type_col} = 1
                      AND UPPER(REPLACE(name, ' ', '')) LIKE %s
                    LIMIT 5""",
                (f"%{stripped}%",),
                as_dict=True,
            )
            if rows:
                return rows[0]["name"]

            # 3. Token match — all words of raw_value present in name
            tokens = [t for t in raw_value.upper().split() if len(t) > 2]
            if tokens:
                where_clauses = " AND ".join(
                    f"UPPER(name) LIKE %s" for _ in tokens
                )
                params = tuple(f"%{t}%" for t in tokens)
                rows2 = frappe.db.sql(
                    f"""SELECT name FROM `tabVendor`
                        WHERE {vendor_type_col} = 1
                          AND {where_clauses}
                        LIMIT 5""",
                    params,
                    as_dict=True,
                )
                if rows2:
                    return rows2[0]["name"]

            # 4. Broadest possible match — any vendor with right type flag
            rows3 = frappe.db.sql(
                f"""SELECT name FROM `tabVendor`
                    WHERE {vendor_type_col} = 1
                      AND UPPER(name) LIKE %s
                    LIMIT 1""",
                (f"%{tokens[0] if tokens else stripped[:4]}%",),
                as_dict=True,
            )
            if rows3:
                return rows3[0]["name"]

            return raw_value  # give up — Frappe will show a clear error

        def _resolve_vehicle(raw_value: str) -> str:
            """Resolve extracted registration number to Frappe Vehicle document name."""
            if not raw_value:
                return raw_value
            exact = frappe.db.get_value("Vehicle", {"name": raw_value}, "name")
            if exact:
                return exact
            # Strip spaces, compare case-insensitively
            stripped = raw_value.replace(" ", "").upper()
            rows = frappe.db.sql(
                """SELECT name FROM `tabVehicle`
                   WHERE UPPER(REPLACE(name, ' ', '')) LIKE %s
                   LIMIT 1""",
                (f"%{stripped}%",),
                as_dict=True,
            )
            if rows:
                return rows[0]["name"]
            return raw_value

        # Resolve vendor Link
        if "vendor" in clean_fields:
            resolved_vendor = _resolve_vendor(
                clean_fields["vendor"], is_service=(doctype == "Service Entry")
            )
            frappe.log_error(
                title="AIKO vendor resolution",
                message=f"raw={clean_fields['vendor']!r} resolved={resolved_vendor!r}"
            )
            clean_fields["vendor"] = resolved_vendor

        # Resolve vehicle Link
        if "vehicle" in clean_fields:
            resolved_vehicle = _resolve_vehicle(clean_fields["vehicle"])
            frappe.log_error(
                title="AIKO vehicle resolution",
                message=f"raw={clean_fields['vehicle']!r} resolved={resolved_vehicle!r}"
            )
            clean_fields["vehicle"] = resolved_vehicle

        # Drop zero / falsy numeric fields — Frappe defaults missing currency/float
        # fields to 0 anyway, so sending explicit 0 can cause Link validation errors
        # on computed read-only fields and adds no value.
        for _fld in ("parts", "discount_value", "tax_value"):
            if _fld in clean_fields:
                try:
                    if float(clean_fields[_fld]) == 0:
                        del clean_fields[_fld]
                except (ValueError, TypeError):
                    pass

        frappe.log_error(
            title="AIKO final merged fields",
            message=f"doctype={doctype}\nclean_fields={clean_fields}"
        )

        # ------------------------------------------------------------------ #
        # Resolve record_name: if the user said "update SE-2025-00001" we    #
        # already have it. Otherwise, if the user said "update" (not create) #
        # look for the most recent draft record for this vehicle so we UPDATE #
        # rather than always inserting a duplicate.                           #
        # ------------------------------------------------------------------ #
        action_word_lower = message.lower()
        is_update_intent = any(w in action_word_lower for w in ("update", "save", "push"))
        is_create_intent = any(w in action_word_lower for w in ("create", "insert", "add", "make", "new"))

        if not record_name and is_update_intent and not is_create_intent:
            # Try to find the most recent draft record for this vehicle
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
                    frappe.log_error(
                        title="AIKO auto-resolved record_name",
                        message=f"doctype={doctype} vehicle={vehicle_val} → record_name={record_name}"
                    )

        # ------------------------------------------------------------------ #
        # Pre-save Link validation: verify every Link field value actually    #
        # exists in Frappe before attempting insert/save. If a Link value     #
        # can't be confirmed, remove it from clean_fields so the doc saves   #
        # successfully and the user can fill in that field manually.          #
        # This prevents "Could not find Vendor: X" hard errors on insert.    #
        # ------------------------------------------------------------------ #
        link_fields = {
            "vendor": "Vendor",
            "vehicle": "Vehicle",
            "fuel_type": "Fuel Type",
            "unit": "Fuel Entry Unit",
            "trip": "Trip",
        }
        skipped_links = {}
        for fieldname, target_doctype in link_fields.items():
            if fieldname not in clean_fields:
                continue
            val = clean_fields[fieldname]
            exists = frappe.db.exists(target_doctype, val)
            if not exists:
                frappe.log_error(
                    title="AIKO Link validation skip",
                    message=f"fieldname={fieldname} value={val!r} not found in {target_doctype} — removing from payload"
                )
                skipped_links[fieldname] = val
                del clean_fields[fieldname]

        # Create or update the Frappe document
        try:
            if record_name:
                # UPDATE existing record
                doc = frappe.get_doc(doctype, record_name)
                for fieldname, value in clean_fields.items():
                    doc.set(fieldname, value)
                doc.flags.ignore_mandatory = True
                doc.flags.ignore_validate_update_after_submit = True
                doc.save(ignore_permissions=True)
                frappe.db.commit()
                action_done = f"updated **{record_name}**"
            else:
                # CREATE new record
                doc_data = {"doctype": doctype}
                doc_data.update(clean_fields)
                doc = frappe.get_doc(doc_data)
                doc.flags.ignore_mandatory = True
                doc.flags.ignore_validate_update_after_submit = True
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                action_done = f"created **{doc.name}**"

            # After a successful save, patch skipped Link fields directly via
            # db.set_value which bypasses Frappe's Link validation entirely.
            # This way the vendor/vehicle IS stored even if the name doesn't
            # match the exact case Frappe expects from frappe.db.exists().
            if skipped_links:
                for fieldname, val in skipped_links.items():
                    frappe.db.set_value(doctype, doc.name, fieldname, val,
                                        update_modified=False)
                frappe.db.commit()
                frappe.log_error(
                    title="AIKO patched skipped links",
                    message=f"doc={doc.name} patched={skipped_links}"
                )

        except Exception as e:
            frappe.log_error(title=f"AIKO {doctype} save error", message=frappe.get_traceback())
            return {
                "content": (
                    f"❌ Failed to save the {doctype} record: `{e}`\n\n"
                    f"Fields attempted:\n"
                    + "\n".join(f"- **{k}**: {v}" for k, v in clean_fields.items())
                ),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }

        # Build a friendly confirmation table
        field_rows = "\n".join(f"| {k} | {v} |" for k, v in clean_fields.items())
        final_answer = (
            f"✅ Successfully {action_done} in **{doctype}**.\n\n"
            f"| Field | Value |\n|---|---|\n{field_rows}\n\n"
            f"[View in Frappe: {doctype} → {doc.name}]"
        )

        return {
            "content": final_answer,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }

    # Keywords that mean "show me what's in the file" — no LLM reasoning needed.
    _DISPLAY_ONLY_PATTERNS = (
        "extract", "read", "show", "display", "what", "content", "text",
        "tell me", "give me", "summarize", "summary", "details", "list",
        "items", "fields", "data", "information", "info", "parse",
    )

    def _is_display_only_request(self, message: str) -> bool:
        """Return True when the user just wants to see the file content and has
        NOT asked us to write anything into Frappe or requested custom tabular layout formatting.
        """
        lower = message.lower()
        
        # 1. Route to Slow Path if executing a database action
        action_words = ("create", "save", "insert", "add to", "update", "push", "submit")
        if any(w in lower for w in action_words):
            return False
            
        # 2. Route to Slow Path if the user wants custom structure layout reasoning from the LLM
        formatting_words = ("table", "tabular", "grid", "breakdown", "items", "list items")
        if any(w in lower for w in formatting_words):
            return False
            
        return True  # default: treat all file uploads as display requests unless explicit action or query formatting requested

    async def _process_file_extraction_query(
        self, message: str, file_url: str, operation: str, file_name: str
    ) -> dict:
        await self.connect_to_streamable_http_server()
        try:
            # _extract_file_deterministically now returns a 3-tuple:
            #   display_content  — HTML card or plain text, shown to the user
            #   note             — empty or "retried with OCR" notice
            #   plain_text       — raw extracted text, NEVER HTML, used for field extraction
            display_content, note, plain_text = await self._extract_file_deterministically(file_url, operation)

            # ----------------------------------------------------------------
            # FAST PATH: If extraction succeeded and the user is just asking to
            # see/read/summarize the file (not create a Frappe record), bypass
            # the LLM entirely and return the extracted text directly.
            # This eliminates the entire class of failures where:
            #   - Ollama runs out of context and produces empty output
            #   - The model ignores the extraction and calls an unrelated tool
            #   - The model produces an apology instead of the content
            # ----------------------------------------------------------------
            # Use plain_text for the "ok" check — display_content may be HTML
            # which always starts with "<", never "["
            extraction_ok = not plain_text.startswith("[")

            # LOG: record extraction result for debugging
            frappe.log_error(
                title="AIKO file extraction fast-path check",
                message=(
                    f"file_name={file_name} operation={operation}\n"
                    f"extraction_ok={extraction_ok}\n"
                    f"plain_text[:300]={plain_text[:300]}"
                )
            )

            if not extraction_ok:
                # Extraction failed — surface the real error directly to the user
                # instead of passing to Ollama which will generate a confusing 
                # "no text found" message that hides the actual cause.
                final_answer = (
                    f"Sorry, I could not extract text from **{file_name}**.\n\n"
                    f"Reason: {plain_text}\n\n"
                    f"Please check the Frappe error log (titled 'AIKO extract_file_content') "
                    f"for the full details."
                )
                self.messages.append({"role": "user", "content": f"[File: {file_name}] {message}"})
                self.messages.append({"role": "assistant", "content": final_answer})
                self._trim_history()
                return {"content": final_answer, "input_tokens": 0, "output_tokens": 0}

            if self._is_display_only_request(message):
                display_header = f"Here is the extracted content of **{file_name}**:\n\n"
                if note:
                    display_header += f"_{note.strip()}_\n\n"
                final_answer = display_header + display_content

                short_user_msg = (
                    f"[File: {file_name}] {message}\n\n"
                    f"[Extracted content was provided directly for this turn.]"
                )
                self.messages.append({"role": "user", "content": short_user_msg})
                self.messages.append({"role": "assistant", "content": final_answer})
                self._trim_history()

                return {
                    "content": final_answer,
                    "input_tokens": 0,
                    "output_tokens": 0,
                }

            # ----------------------------------------------------------------
            # DOCTYPE UPDATE PATH: User wants to create/update a Service Entry
            # or Fuel Entry. Do this deterministically — extract fields via a
            # structured JSON prompt to the LLM, then write to Frappe in code.
            # This bypasses the general-purpose tool-call loop entirely so a
            # small local model can't accidentally call the wrong tool.
            # ----------------------------------------------------------------
            doctype_intent = self._detect_doctype_update_intent(message)
            if doctype_intent is not None:
                doctype, field_map, record_name = doctype_intent
                result = await self._update_doctype_from_extraction(
                    message=message,
                    extracted_text=plain_text,   # ALWAYS raw text, never HTML
                    doctype=doctype,
                    field_map=field_map,
                    record_name=record_name,
                    file_name=file_name,
                )
                final_answer = result.get("content", "")
                usage = {
                    "input_tokens": result.get("input_tokens", 0),
                    "output_tokens": result.get("output_tokens", 0),
                }

                short_user_msg = (
                    f"[File: {file_name}] {message}\n\n"
                    f"[DocType update attempted for: {doctype}]"
                )
                self.messages.append({"role": "user", "content": short_user_msg})
                self.messages.append({"role": "assistant", "content": final_answer})
                self._trim_history()

                return {
                    "content": final_answer,
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                }

            # ----------------------------------------------------------------
            # SLOW PATH: User asked for something that needs LLM reasoning
            # (e.g. "create a Purchase Invoice from this", "what is the total?").
            # Hand the extracted text to the LLM with a clean, minimal message
            # list — system prompt + THIS turn only, no history — so that prior
            # "[Extracted content was provided…]" stubs from old turns can't
            # confuse the model or bloat the context window.
            # ----------------------------------------------------------------
            truncated = _truncate(plain_text)   # plain text, not HTML, for LLM
            full_prompt = (
                f"A file named '{file_name}' was uploaded. The system has ALREADY "
                f"extracted its full content — do NOT call extract_file_content "
                f"yourself. Present every field, every line, every amount "
                f"completely. Never say the content can't be processed. If the "
                f"extracted content below already contains '**Label:** Value' "
                f"lines, reproduce them exactly as given, one per line — do NOT "
                f"rewrite them into prose or a table.\n\n"
                f"{note}"
                f"--- EXTRACTED FILE CONTENT START ---\n"
                f"{truncated}\n"
                f"--- EXTRACTED FILE CONTENT END ---\n\n"
                f"Only call a tool to create/update a Frappe record if the user's "
                f"request explicitly contains 'create', 'save', 'insert', or 'add to' "
                f"followed by a DocType name. Otherwise answer from the content above.\n\n"
                f"User request: {message}"
            )

            # Use ONLY system prompt + this turn — no history — to keep
            # context lean and avoid poisoning from old compact stubs.
            system_msg = self.messages[0]  # always the system prompt
            messages_for_llm = [system_msg, {"role": "user", "content": full_prompt}]

            result = await self.provider.process_query_with_messages(
                self.session, messages_for_llm
            )
            final_answer, _updated_messages, usage = result

            # Three-tier fallback: LLM answer → raw extraction → error message
            if not final_answer or final_answer.strip().startswith("I'm sorry"):
                if plain_text and not plain_text.startswith("[No content"):
                    final_answer = (
                        f"Here is the extracted content of **{file_name}**"
                        f"{' (' + note.strip() + ')' if note else ''}:\n\n"
                        f"{display_content}"
                    )
                else:
                    final_answer = display_content or (
                        "I'm sorry, I couldn't generate a response. Please try again."
                    )

            short_user_msg = (
                f"[File: {file_name}] {message}\n\n"
                f"[Extracted content was provided to the assistant for this turn.]"
            )
            self.messages.append({"role": "user", "content": short_user_msg})
            self.messages.append({"role": "assistant", "content": final_answer})
            self._trim_history()

            return {
                "content": final_answer,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }
        finally:
            await self.cleanup()

    async def _process_query_with_file(
        self, message: str, file_data: str, file_type: str, file_name: str
    ) -> dict:
        await self.connect_to_streamable_http_server()
        try:
            multimodal_message = self._build_multimodal_message(
                message, file_data, file_type, file_name
            )

            # Append to a copy so self.messages stays clean until we know it succeeded
            messages_with_file = self.messages + [multimodal_message]

            result = await self.provider.process_query_with_messages(
                self.session, messages_with_file
            )

            final_answer, updated_messages, usage = result

            if not final_answer:
                final_answer = "I'm sorry, I couldn't analyse the file. Please try again."

            # Store a text-only version in history (no base64 blobs)
            self.messages.append({
                "role": "user",
                "content": f"[File: {file_name}] {message}",
            })
            self.messages.append({"role": "assistant", "content": final_answer})
            self._trim_history()

            return {
                "content": final_answer,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "doctype_updated": usage.get("doctype_updated", ""),
            }
        finally:
            await self.cleanup()