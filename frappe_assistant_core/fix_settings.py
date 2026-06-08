import frappe

def fix_settings():
    settings = frappe.get_doc("Assistant Core Settings")
    settings.ollama_chat_api_url = "http://ollama.kofleetz.in:3900"
    settings.ollama_chat_model = "qwen2.5-coder:7b"
    settings.save(ignore_permissions=True)
    frappe.db.commit()
    print("Settings updated successfully.")
