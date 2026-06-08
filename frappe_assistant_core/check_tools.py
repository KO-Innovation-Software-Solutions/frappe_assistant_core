import frappe
from frappe_assistant_core.aiko.agent import DirectMCPClient

def print_tools():
    frappe.session.user = "Administrator"
    client = DirectMCPClient("Administrator")
    res = client.send_request("tools/list")
    print("\n=== RAW RESPONSE ===")
    print([t["name"] for t in res["tools"]])
    print("=======================\n")
