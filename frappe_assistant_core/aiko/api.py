import asyncio
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe_assistant_core.aiko.agent import AikoAgent

def _cancel_key(request_id: str) -> str:
    return f"aiko_cancel_{request_id}"

def _mark_cancelled(request_id: str):
    """Set a short-lived cache flag so the background worker knows to stop."""
    frappe.cache().set_value(_cancel_key(request_id), 1, expires_in_sec=300)

def _is_cancelled(request_id: str) -> bool:
    """Check if the given request has been cancelled."""
    return bool(frappe.cache().get_value(_cancel_key(request_id)))

def _clear_cancel(request_id: str):
    frappe.cache().delete_value(_cancel_key(request_id))

@frappe.whitelist(methods=["POST"])
def cancel_chat(request_id: str):
    """Called by the frontend stop button. Sets a cache flag the worker polls."""
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))
    if not request_id:
        frappe.throw(_("request_id is required"))
    _mark_cancelled(request_id)
    return {"success": True}

def _get_active_llm_info(settings=None):
    """Return (provider, model) currently configured in Assistant Core Settings -> AIKO LLM tab."""
    settings = settings or frappe.get_single("Assistant Core Settings")
    provider = (settings.get("llm_provider") or "anthropic").lower()

    if provider == "openai":
        model = settings.get("openai_model")
    elif provider == "ollama":
        model = settings.get("ollama_chat_model")
    else:  # anthropic (default)
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


def _save_message(session_id: str, role: str, content: str,input_tokens: int = 0, output_tokens: int = 0,llm_provider: str = None, llm_model: str = None):
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

@frappe.whitelist(methods=["POST"])
def save_stopped_message(thread_id: str, request_id: str = None):
    """Save a 'Response stopped' placeholder so it persists after refresh."""
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))
    user = frappe.session.user
    session = _get_or_create_session(thread_id, user)
    _save_message(session.name, role="assistant", content="_Response stopped._")
    _update_session_meta(session, delta_messages=1)
    frappe.db.commit()
    return {"success": True}

@frappe.whitelist()
def chat(message: str, thread_id: str, request_id: str = None):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))

    user = frappe.session.user
    request_id = request_id or frappe.generate_hash(length=10)

    try:
        frappe.enqueue(
            "frappe_assistant_core.aiko.api.run_chat_job_sync",
            queue="default",
            timeout=300,
            message=message,
            thread_id=thread_id,
            user=user,
            request_id=request_id,
        )
    except Exception:
        frappe.log_error(title="AIKO Chat Enqueue Error", message=frappe.get_traceback())
        return {"success": False, "error": "Could not start the request. Please try again."}

    return {
        "success": True,
        "queued": True,
        "thread_id": thread_id,
        "request_id": request_id,
    }
async def run_chat_job(message: str, thread_id: str, user: str, request_id: str):
    """
    Runs on the background worker. Executes the AIKO agent, publishing
    stage updates as it goes, then publishes the final answer.
    """
    frappe.set_user(user)

    async def on_stage(text):
        await asyncio.to_thread(
            frappe.publish_realtime,
            event="aiko_stage",
            message={"thread_id": thread_id, "request_id": request_id, "stage": text},
            user=user,
        )

    try:
        await on_stage("Reading your message…")
        settings = frappe.get_single("Assistant Core Settings")
        provider, model = _get_active_llm_info(settings)
        session = _get_or_create_session(thread_id, user)

        _save_message(
            session.name,
            role="user",
            content=message,
            llm_provider=provider,
            llm_model=model,
        )
        _update_session_meta(session, delta_messages=1)
        frappe.db.commit()
        # ─────────────────────────────────────────────────────────────────

        agent = AikoAgent(thread_id=thread_id)
        result = await agent.invoke(message, on_stage=on_stage, is_cancelled=lambda: _is_cancelled(request_id))
        if _is_cancelled(request_id):
            _clear_cancel(request_id)
            frappe.logger().info(f"AIKO request {request_id} was cancelled — skipping assistant save.")
            return

        response_text = result.get("content", "")
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)

        _save_message(
            session.name,
            role="assistant",
            content=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            llm_provider=provider,
            llm_model=model,
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
        frappe.log_error(title="AIKO Chat Error", message=frappe.get_traceback())
        frappe.publish_realtime(
            event="aiko_done",
            message={
                "thread_id": thread_id,
                "request_id": request_id,
                "success": False,
                "error": "Something went wrong while processing your message.",
            },
            user=user,
        )

def _get_or_create_dashboard_session(thread_id: str, user: str):
    existing_name = frappe.db.get_value("Aiko Dashboard Session", {"thread_id": thread_id}, "name")
    if existing_name:
        return frappe.get_doc("Aiko Dashboard Session", existing_name)

    session = frappe.get_doc({
        "doctype": "Aiko Dashboard Session",
        "thread_id": thread_id,
        "user": user,
        "title": f"Dashboard {thread_id[:8]}",
        "message_count": 0,
    })
    try:
        session.insert(ignore_permissions=True)
    except frappe.exceptions.DuplicateEntryError:
        frappe.db.rollback()
        existing_name = frappe.db.get_value("Aiko Dashboard Session", {"thread_id": thread_id}, "name")
        if existing_name:
            return frappe.get_doc("Aiko Dashboard Session", existing_name)
        raise
    return session


def _save_dashboard_message(session_id, role, content, ui=None, input_tokens=0, output_tokens=0, llm_provider=None, llm_model=None):
    total = input_tokens + output_tokens
    msg = frappe.get_doc({
        "doctype": "Aiko Dashboard Message",
        "session": session_id,
        "role": role,
        "content": content,
        "ui": ui,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
    })
    msg.insert(ignore_permissions=True)
    return msg


def _update_dashboard_session_meta(session, delta_messages: int = 1):
    frappe.db.set_value(
        "Aiko Dashboard Session",
        session.name,
        {
            "last_active": now_datetime(),
            "message_count": (session.message_count or 0) + delta_messages,
        },
        update_modified=False,
    )


async def run_dashboard_job(message: str, thread_id: str, user: str, request_id: str):
    frappe.set_user(user)

    async def on_stage(text):
        await asyncio.to_thread(
            frappe.publish_realtime,
            event="aiko_dashboard_stage",
            message={"thread_id": thread_id, "request_id": request_id, "stage": text},
            user=user,
        )

    try:
        await on_stage("Reading your message…")
        settings = frappe.get_single("Assistant Core Settings")
        provider, model = _get_active_llm_info(settings)
        session = _get_or_create_dashboard_session(thread_id, user)

        _save_dashboard_message(
            session.name, role="user", content=message,
            llm_provider=provider, llm_model=model,
        )
        _update_dashboard_session_meta(session, delta_messages=1)
        frappe.db.commit()

        agent = AikoAgent(thread_id=thread_id, surface="dashboard")
        result = await agent.invoke(
            message, on_stage=on_stage,
            is_cancelled=lambda: _is_cancelled(request_id),
            want_ui=True,
        )
        if _is_cancelled(request_id):
            _clear_cancel(request_id)
            frappe.logger().info(f"AIKO dashboard request {request_id} was cancelled — skipping save.")
            return

        response_text = result.get("content", "")
        ui = result.get("ui")
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)

        _save_dashboard_message(
            session.name, role="assistant", content=response_text, ui=ui,
            input_tokens=input_tokens, output_tokens=output_tokens,
            llm_provider=provider, llm_model=model,
        )
        _update_dashboard_session_meta(session, delta_messages=1)
        frappe.db.commit()

        frappe.publish_realtime(
            event="aiko_dashboard_done",
            message={
                "thread_id": thread_id,
                "request_id": request_id,
                "success": True,
                "data": response_text,
                "ui": ui,
                "session_name": session.name,
            },
            user=user,
        )

    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="AIKO Dashboard Error", message=frappe.get_traceback())
        frappe.publish_realtime(
            event="aiko_dashboard_done",
            message={
                "thread_id": thread_id,
                "request_id": request_id,
                "success": False,
                "error": "Something went wrong while processing your message.",
            },
            user=user,
        )


def run_dashboard_job_sync(message: str, thread_id: str, user: str, request_id: str):
    asyncio.run(run_dashboard_job(message, thread_id, user, request_id))

@frappe.whitelist()
def list_dashboard_sessions(limit: int = 50):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))
    sessions = frappe.db.sql(
        """
        SELECT
            s.name, s.thread_id, s.title, s.last_active, s.message_count, s.creation,
            (SELECT m.content FROM `tabAiko Dashboard Message` m
             WHERE m.session = s.name AND m.role = 'user' ORDER BY m.creation DESC LIMIT 1) AS last_message,
            (SELECT m2.content FROM `tabAiko Dashboard Message` m2
             WHERE m2.session = s.name AND m2.role = 'user' ORDER BY m2.creation ASC LIMIT 1) AS first_message
        FROM `tabAiko Dashboard Session` s
        WHERE s.user = %s
        ORDER BY COALESCE(s.last_active, s.creation) DESC
        LIMIT %s
        """,
        (frappe.session.user, limit),
        as_dict=True,
    )
    for s in sessions:
        last_msg = (s.pop("last_message", None) or "").strip()
        first_msg = (s.pop("first_message", None) or "").strip()
        s["preview"] = last_msg or first_msg or ""
    return sessions


@frappe.whitelist()
def get_dashboard_session_messages(thread_id: str):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))
    session_name = frappe.db.get_value(
        "Aiko Dashboard Session",
        {"thread_id": thread_id, "user": frappe.session.user},
        "name",
    )
    if not session_name:
        return {"thread_id": thread_id, "messages": []}

    messages = frappe.db.get_list(
        "Aiko Dashboard Message",
        filters={"session": session_name},
        fields=["role", "content", "ui", "creation"],
        order_by="creation asc",
    )
    return {"thread_id": thread_id, "messages": messages}

@frappe.whitelist()
def dashboard_chat(message: str, thread_id: str, request_id: str = None):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))
    request_id = request_id or frappe.generate_hash(length=10)
    try:
        frappe.enqueue(
            "frappe_assistant_core.aiko.api.run_dashboard_job_sync",
            queue="default",
            timeout=300,
            message=message,
            thread_id=thread_id,
            user=frappe.session.user,
            request_id=request_id,
        )
    except Exception:
        frappe.log_error(title="AIKO Dashboard Enqueue Error", message=frappe.get_traceback())
        return {"success": False, "error": "Could not start the request. Please try again."}
    return {"success": True, "queued": True, "thread_id": thread_id, "request_id": request_id}

def run_chat_job_sync(message: str, thread_id: str, user: str, request_id: str):
    """Sync entry point for Frappe's background worker."""
    asyncio.run(run_chat_job(message, thread_id, user, request_id))