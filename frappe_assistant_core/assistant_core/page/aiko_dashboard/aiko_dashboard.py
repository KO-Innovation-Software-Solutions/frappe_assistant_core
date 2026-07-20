import frappe


def get_context(context):
    # No server-side context needed - aiko_dashboard.js mounts the React
    # bundle and everything after that talks to frappe_assistant_core.aiko.api
    # via frappe.call / frappe.realtime, same as the existing aiko_chat page.
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in to access the Aiko Dashboard"), frappe.PermissionError)
