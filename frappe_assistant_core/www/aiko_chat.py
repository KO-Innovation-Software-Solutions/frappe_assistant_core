import frappe

def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/aiko_chat"
        raise frappe.Redirect

    allowed_roles = {"Assistant User", "Assistant Admin", "System Manager", "Administrator"}
    user_roles = set(frappe.get_roles(frappe.session.user))
    if not user_roles.intersection(allowed_roles):
        frappe.throw("You do not have permission to access AIKO Assistant.", frappe.PermissionError)

    from frappe_assistant_core.utils.token_limits import is_assistant_enabled

    if not is_assistant_enabled(frappe.session.user):
        frappe.throw("AIKO access is not enabled for this account. Please contact your administrator.", frappe.PermissionError)

    context.no_cache = 1
    context.title = "AIKO Assistant"
    context.user = frappe.session.user