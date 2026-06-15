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


@frappe.whitelist()
def chat(message: str, thread_id: str):
    """
    Main endpoint for AIKO chat.
    Saves the session and each message (user + assistant) with token usage.
    Returns session_name so the frontend can track the session.
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