import frappe


def get_context(context):
    # No server-side context needed - aiko_dashboard_artifact_view.js mounts
    # the React bundle and everything after that talks to
    # frappe_assistant_core.aiko.api via frappe.call, same pattern as
    # aiko_dashboard.py.
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in to access this Dashboard Artifact"), frappe.PermissionError)