import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe_assistant_core.aiko.agent import AikoAgent


def _get_or_create_session(thread_id: str, user: str):
    """Return existing session doc or create a new one for this thread_id."""
    if frappe.db.exists("Aiko Chat Session", thread_id):
        session = frappe.get_doc("Aiko Chat Session", thread_id)
    else:
        session = frappe.get_doc({
            "doctype": "Aiko Chat Session",
            "thread_id": thread_id,
            "user": user,
            "title": f"Chat {thread_id[:8]}",
            "message_count": 0,
        })
        session.insert(ignore_permissions=True)
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
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))

    user = frappe.session.user

    try:
        # 1. Ensure session exists
        session = _get_or_create_session(thread_id, user)

        # 2. Save the user message (no tokens on the user side)
        _save_message(session.name, role="user", content=message)

        # 3. Run the agent
        agent = AikoAgent(thread_id=thread_id)
        result = agent.invoke(message)

        # result is either a plain string (legacy) or a dict with token info
        if isinstance(result, dict):
            response_text = result.get("content", "")
            input_tokens = result.get("input_tokens", 0)
            output_tokens = result.get("output_tokens", 0)
        else:
            response_text = result
            input_tokens = 0
            output_tokens = 0

        # 4. Save the assistant message
        _save_message(
            session.name,
            role="assistant",
            content=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        # 5. Update session metadata (user msg + assistant msg = 2)
        _update_session_meta(session, delta_messages=2)

        frappe.db.commit()

        return {
            "success": True,
            "data": response_text,
        }

    except Exception as e:
        frappe.log_error(title="AIKO Chat Error", message=str(e))
        return {
            "success": False,
            "error": str(e),
        }