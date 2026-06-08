import frappe
from frappe import _
from frappe_assistant_core.aiko.agent import AikoAgent

@frappe.whitelist()
def chat(message: str, thread_id: str):
    """
    Main endpoint for the AIKO chat UI.
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))

    # Check assistant permissions using existing logic
    try:
        from frappe_assistant_core.utils.permissions import check_assistant_permission
        if not check_assistant_permission(frappe.session.user):
            frappe.throw(_("Assistant access is disabled for your user."))
    except ImportError:
        # Fallback if permission logic is moved
        pass
    
    try:
        agent = AikoAgent(thread_id=thread_id)
        response_text = agent.invoke(message)
        
        return {
            "success": True,
            "data": response_text
        }
    except Exception as e:
        frappe.log_error(title="AIKO Chat Error", message=str(e))
        return {
            "success": False,
            "error": str(e)
        }
