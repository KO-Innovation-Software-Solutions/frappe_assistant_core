from __future__ import annotations
import asyncio
import base64
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe_assistant_core.aiko.file_chat.agent import AikoFileAgent

def _get_active_llm_info(settings=None):
    settings = settings or frappe.get_single("Assistant Core Settings")
    provider = (settings.get("llm_provider") or "anthropic").lower()
    if provider == "openai":
        model = settings.get("openai_model")
    elif provider == "ollama":
        model = settings.get("ollama_chat_model")
    else:
        model = settings.get("anthropic_model")
    return provider, model

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

def _save_message(
    session_id: str, role: str, content: str,
    input_tokens: int = 0, output_tokens: int = 0,
    llm_provider: str = None, llm_model: str = None,
):
    total = input_tokens + output_tokens
    msg = frappe.get_doc({
        "doctype": "Aiko Chat Message",
        "session": session_id,
        "role": role,
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
    })
    msg.insert(ignore_permissions=True)
    return msg

def _update_session_meta(session, delta_messages: int = 1):
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
def chat_with_file(
    message: str,
    thread_id: str,
    file_name: str,
    file_type: str,
    file_data: str,
    request_id: str = None,
):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))

    user = frappe.session.user
    request_id = request_id or frappe.generate_hash(length=10)

    try:
        frappe.enqueue(
            "frappe_assistant_core.aiko.file_chat.api.run_file_chat_job_sync",
            queue="default",
            timeout=300,
            message=message,
            thread_id=thread_id,
            file_name=file_name,
            file_type=file_type,
            file_data=file_data,
            user=user,
            request_id=request_id,
        )
    except Exception:
        frappe.log_error(title="AIKO File Chat Enqueue Error", message=frappe.get_traceback())
        return {"success": False, "error": "Could not start the request. Please try again."}

    return {
        "success": True,
        "queued": True,
        "thread_id": thread_id,
        "request_id": request_id,
    }

async def run_file_chat_job(
    message: str,
    thread_id: str,
    file_name: str,
    file_type: str,
    file_data: str,
    user: str,
    request_id: str,
):
    frappe.set_user(user)

    async def on_stage(text: str):
        await asyncio.to_thread(
            frappe.publish_realtime,
            event="aiko_stage",
            message={"thread_id": thread_id, "request_id": request_id, "stage": text},
            user=user,
        )

    try:
        await on_stage("Uploading file...")

        raw_bytes = base64.b64decode(file_data)
        if len(raw_bytes) > 20 * 1024 * 1024:
            frappe.publish_realtime(
                event="aiko_done",
                message={
                    "thread_id": thread_id,
                    "request_id": request_id,
                    "success": False,
                    "error": "File too large. Maximum 20 MB allowed.",
                },
                user=user,
            )
            return

        settings = frappe.get_single("Assistant Core Settings")
        provider, model = _get_active_llm_info(settings)
        session = _get_or_create_session(thread_id, user)

        await on_stage("Saving file...")
        file_url = await asyncio.to_thread(
            _save_file_to_frappe, file_name, file_type, file_data, user
        )

        if file_type.startswith("image/"):
            operation = "ocr"
        elif file_type == "application/pdf" or file_name.lower().endswith(".pdf"):
            try:
                import io
                import pdfplumber as _pl
                with _pl.open(io.BytesIO(raw_bytes)) as _pdf:
                    _has_text = any(
                        p.extract_text() and p.extract_text().strip()
                        for p in _pdf.pages[:3]
                    )
                operation = "extract" if _has_text else "ocr"
            except Exception:
                operation = "extract"
        else:
            operation = "extract"

        _save_message(
            session.name, role="user",
            content=f"[File: {file_name}] {message}",
            llm_provider=provider, llm_model=model,
        )
        _update_session_meta(session, delta_messages=1)
        frappe.db.commit()

        await on_stage("Extracting file content...")
        agent = AikoFileAgent(thread_id=thread_id)
        result = await agent.invoke_with_file_extraction(
            message=message,
            file_url=file_url,
            operation=operation,
            file_name=file_name,
        )

        response_text = result.get("content", "")
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)

        _save_message(
            session.name, role="assistant", content=response_text,
            input_tokens=input_tokens, output_tokens=output_tokens,
            llm_provider=provider, llm_model=model,
        )
        _update_session_meta(session, delta_messages=1)
        frappe.db.commit()

        frappe.publish_realtime(
            event="aiko_done",
            message={
                "thread_id": thread_id,
                "request_id": request_id,
                "success": True,
                "data": response_text,
                "session_name": session.name,
            },
            user=user,
        )

    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="AIKO File Chat Error", message=frappe.get_traceback())
        frappe.publish_realtime(
            event="aiko_done",
            message={
                "thread_id": thread_id,
                "request_id": request_id,
                "success": False,
                "error": "Something went wrong while processing your file.",
            },
            user=user,
        )


def run_file_chat_job_sync(
    message: str,
    thread_id: str,
    file_name: str,
    file_type: str,
    file_data: str,
    user: str,
    request_id: str,
):
    asyncio.run(run_file_chat_job(
        message, thread_id, file_name, file_type, file_data, user, request_id,
    ))