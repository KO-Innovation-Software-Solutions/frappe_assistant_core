import frappe
from frappe import _
from frappe_assistant_core.aiko.agent import AikoAgent

@frappe.whitelist()
def chat(message: str, thread_id: str):
    """
    Main endpoint for AIKO chat.
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))
        
    try:
        agent = AikoAgent(thread_id=thread_id)
        response_text = agent.invoke(message)
        
        return {
            "success": True,
            "data": response_text
        }
    except Exception as e:
        import traceback
        frappe.log_error(title="AIKO Chat Error", message=traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }
