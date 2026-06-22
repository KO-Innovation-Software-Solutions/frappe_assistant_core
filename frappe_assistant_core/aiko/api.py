import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe_assistant_core.aiko.agent import AikoAgent


def _get_or_create_session(thread_id: str, user: str):
    existing_name = frappe.db.get_value("Aiko Chat Session", {"thread_id": thread_id}, "name")
    if existing_name:
        return frappe.get_doc("Aiko Chat Session", existing_name)

    session = frappe.get_doc({
        "doctype": "Aiko Chat Session",
        "thread_id": thread_id,
        "user": user,
        "title": f"Chat {thread_id[:8]}",
        "message_count": 0,
    })
    try:
        session.insert(ignore_permissions=True)
    except frappe.db.IntegrityError:
        frappe.db.rollback()
        existing_name = frappe.db.get_value("Aiko Chat Session", {"thread_id": thread_id}, "name")
        if existing_name:
            return frappe.get_doc("Aiko Chat Session", existing_name)
        raise
    return session


def _save_message(session_id: str, role: str, content: str,
                  input_tokens: int = 0, output_tokens: int = 0):
    """Insert a single chat message record."""
    total = input_tokens + output_tokens
    msg = frappe.get_doc({
        "doctype": "Aiko Chat Message",
        "session": session_id,
        "role": role,
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
    })
    msg.insert(ignore_permissions=True)
    return msg


def _update_session_meta(session, delta_messages: int = 1):
    """Bump message_count and refresh last_active."""
    frappe.db.set_value(
        "Aiko Chat Session",
        session.name,
        {
            "last_active": now_datetime(),
            "message_count": (session.message_count or 0) + delta_messages,
        },
        update_modified=False,
    )


def _save_file_to_frappe(file_name: str, file_type: str, file_data: str, user: str) -> str:
    """
    Save the uploaded base64 file into Frappe's File DocType so that
    extract_file_content MCP tool can locate it by file_url.

    Returns the file_url (e.g. '/private/files/invoice.pdf').
    """
    import base64

    raw_bytes = base64.b64decode(file_data)

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "is_private": 1,
        "content": raw_bytes,
        "owner": user,
    })
    file_doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return file_doc.file_url


@frappe.whitelist()
def chat(message: str, thread_id: str):
    """
    Main endpoint for AIKO chat.
    Saves the session and each message (user + assistant) with token usage.
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))

    user = frappe.session.user

    try:
        session = _get_or_create_session(thread_id, user)
        agent = AikoAgent(thread_id=thread_id)
        result = agent.invoke(message)

        response_text = result.get("content", "")
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)
        _save_message(session.name, role="user", content=message)
        _save_message(
            session.name,
            role="assistant",
            content=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        _update_session_meta(session, delta_messages=2)
        frappe.db.commit()

        return {
            "success": True,
            "data": response_text,
            "session_name": session.name,
        }

    except Exception as e:
        frappe.log_error(title="AIKO Chat Error", message=frappe.get_traceback())
        return {
            "success": False,
            "error": str(e),
        }


@frappe.whitelist()
def chat_with_file(message: str, thread_id: str, file_name: str, file_type: str, file_data: str):
    """
    Chat endpoint that accepts a file (image, PDF, or document) as base64.

    Strategy:
    1. Save the file into Frappe's File DocType (private).
    2. Decide the extraction operation (extract vs ocr) based on file type
       and, for PDFs, whether a real text layer is present.
    3. Call extract_file_content directly via the agent's MCP session
       (deterministically, in code) and hand the resulting text to the LLM
       along with the user's message. The LLM is never asked to decide
       whether/how to extract the file — only to answer using text it's
       already been given, and optionally act on a DocType if the user's
       message explicitly asked for that (e.g. "create", "save", "insert").

    This avoids sending raw base64 to the LLM, works with any model
    including text-only Ollama models, and removes the failure mode where
    a model ignores extraction instructions and reaches for an unrelated
    tool (e.g. a keyword like "items" triggering a lookup against a
    "DocType" that may not even exist).
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))

    user = frappe.session.user

    try:
        import base64

        # Basic size guard: 20 MB
        raw_bytes = base64.b64decode(file_data)
        if len(raw_bytes) > 20 * 1024 * 1024:
            return {"success": False, "error": "File too large. Maximum 20 MB allowed."}

        # 1. Save file to Frappe so the MCP tool can read it
        file_url = _save_file_to_frappe(file_name, file_type, file_data, user)

        # 2. Determine the best operation for the file type.
        #    Images always use OCR. PDFs are checked: if pdfplumber finds
        #    no text layer (scanned PDF), go straight to OCR so we don't
        #    waste a round-trip through extract first.
        if file_type.startswith("image/"):
            operation = "ocr"
        elif file_type == "application/pdf" or file_name.lower().endswith(".pdf"):
            # Quick scan: check if this PDF has a real text layer
            import base64 as _b64
            try:
                import pdfplumber as _pl, io as _io
                _raw = _b64.b64decode(file_data)
                with _pl.open(_io.BytesIO(_raw)) as _pdf:
                    _has_text = any(
                        p.extract_text() and p.extract_text().strip()
                        for p in _pdf.pages[:3]
                    )
                operation = "extract" if _has_text else "ocr"
            except Exception:
                operation = "extract"  # safe fallback
        else:
            operation = "extract"

        # 3. Hand off to the agent. Extraction now happens deterministically
        #    in code (see AikoAgent.invoke_with_file_extraction) — the LLM is
        #    never asked to decide whether/how to call extract_file_content,
        #    so it can't skip that step or reach for an unrelated tool based
        #    on a keyword match (e.g. "items" -> an "Invoice" DocType lookup).
        #    It only ever has to answer using the extracted text we hand it,
        #    and optionally act on a DocType if the user explicitly asked.
        session = _get_or_create_session(thread_id, user)
        agent = AikoAgent(thread_id=thread_id)
        result = agent.invoke_with_file_extraction(
            message=message,
            file_url=file_url,
            operation=operation,
            file_name=file_name,
        )

        response_text = result.get("content", "")
        input_tokens  = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)

        _save_message(session.name, role="user", content=f"[File: {file_name}] {message}")
        _save_message(
            session.name,
            role="assistant",
            content=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        _update_session_meta(session, delta_messages=2)
        frappe.db.commit()

        return {
            "success": True,
            "data": response_text,
            "session_name": session.name,
        }

    except Exception as e:
        frappe.log_error(title="AIKO File Chat Error", message=frappe.get_traceback())
        return {
            "success": False,
            "error": str(e),
        }