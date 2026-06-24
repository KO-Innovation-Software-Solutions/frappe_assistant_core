import frappe
import os

def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/aiko_chat"
        raise frappe.Redirect

    allowed_roles = {"Assistant User", "Assistant Admin", "System Manager", "Administrator"}
    user_roles = set(frappe.get_roles(frappe.session.user))
    if not user_roles.intersection(allowed_roles):
        frappe.throw("You do not have permission to access AIKO Assistant.", frappe.PermissionError)

    context.no_cache = 1
    context.title = "AIKO Assistant"
    context.user = frappe.session.user

    # ✅ ADD THIS BLOCK
    js_path = os.path.join(
        os.path.dirname(__file__),  # www/ folder
        "aiko_chat.js"
    )
    with open(js_path, "r") as f:
        context.script = f.read()