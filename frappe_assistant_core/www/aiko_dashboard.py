import frappe

def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/aiko_dashboard"
        raise frappe.Redirect

    allowed_roles = {"Assistant User", "Assistant Admin", "System Manager", "Administrator"}
    user_roles = set(frappe.get_roles(frappe.session.user))
    if not user_roles.intersection(allowed_roles):
        frappe.throw("You do not have permission to access AIKO Dashboard.", frappe.PermissionError)

    context.no_cache = 1
    context.title = "AIKO Dashboard"
    context.user = frappe.session.user
