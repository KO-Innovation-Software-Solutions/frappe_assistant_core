"""
Get fleet-wide statistics: running, idle, parked, offline vehicle counts.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient


class GetFleetSummary(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_fleet_summary"
		self.description = (
			"Provides fleet-wide statistics including running, idle, parked, and offline vehicles. "
			"Use this for 'Give me fleet status', 'How many vehicles are running now?', "
			"'Fleet overview for today'."
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"group_id": {"type": "integer", "description": "Optional group ID to filter fleet"},
			},
			"required": [],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		group_id = arguments.get("group_id")
		try:
			client    = TraccarClient()
			devices   = client.get_devices(group_id=group_id)
			positions = {p.get("deviceId"): p for p in client.get_positions()}

			stats   = {"Running": 0, "Idle": 0, "Parked": 0, "Offline": 0}
			details = []

			for d in devices:
				dev_id  = d.get("id")
				status  = d.get("status", "unknown")
				pos     = positions.get(dev_id, {})
				speed   = pos.get("speed", 0)
				ignition = pos.get("attributes", {}).get("ignition", False)

				if status == "offline":
					label = "Offline"
				elif ignition and speed > 1:
					label = "Running"
				elif ignition:
					label = "Idle"
				else:
					label = "Parked"

				stats[label] += 1
				details.append({"name": d.get("name"), "status": label})

			return {
				"success": True,
				"total":   len(devices),
				"running": stats["Running"],
				"idle":    stats["Idle"],
				"parked":  stats["Parked"],
				"offline": stats["Offline"],
				"vehicles": details,
			}
		except Exception as e:
			frappe.log_error(str(e), "GetFleetSummary.execute")
			return {"success": False, "error": str(e)}


get_fleet_summary = GetFleetSummary()