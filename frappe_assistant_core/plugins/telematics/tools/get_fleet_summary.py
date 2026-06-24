from typing import Any, Dict
import frappe

from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient


class GetFleetSummary(BaseTool):

    def __init__(self):
        super().__init__()

        self.name = "get_fleet_summary"

        self.description = (
            "Returns raw fleet summary data from Traccar."
        )

        self.inputSchema = {
            "type": "object",
            "properties": {
                "from_date": {
                    "type": "string"
                },
                "to_date": {
                    "type": "string"
                }
            },
            "required": ["from_date", "to_date"]
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:

        try:
            client = TraccarClient()

            summary = client.get_all_summary(
                arguments["from_date"],
                arguments["to_date"]
            )

            return {
                "success": True,
                "data": summary
            }

        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(),
                "GetFleetSummary"
            )

            return {
                "success": False,
                "error": str(e)
            }


get_fleet_summary = GetFleetSummary()