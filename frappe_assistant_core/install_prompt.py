import frappe

def create_prompt():
    if not frappe.db.exists("Prompt Template", {"prompt_id": "aiko_system_prompt"}):
        doc = frappe.get_doc({
            "doctype": "Prompt Template",
            "prompt_id": "aiko_system_prompt",
            "title": "AIKO System Prompt",
            "description": "Base identity and instructions for the AIKO LangGraph Agent.",
            "status": "Published",
            "visibility": "Public",
            "is_system": 1,
            "category": "system-admin",
            "rendering_engine": "Jinja2",
            "template_content": "You are AIKO, an AI assistant for Kofleetz. CRITICAL INSTRUCTION: You MUST ONLY use the provided tools to fetch real data and answer user requests. NEVER use your internal knowledge to answer questions, explain concepts, or write code snippets. If the user asks for data (e.g., 'List of vehicle'), you MUST use the search_documents or get_document tool to fetch real data from the Kofleetz database. If you do not have a tool to fulfill the request, clearly inform the user that you lack the capability. Always summarize the actual data you receive from tools clearly to the user.\n\n=== ADDITIONAL INSTRUCTIONS ===\n{{ additional_instructions }}",
        })
        doc.append("arguments", {
            "argument_name": "additional_instructions",
            "display_label": "Additional Instructions",
            "argument_type": "string",
            "is_required": 0,
            "default_value": "",
            "description": "Any additional system instructions for the agent."
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print("Prompt successfully inserted!")
    else:
        print("Prompt already exists!")
