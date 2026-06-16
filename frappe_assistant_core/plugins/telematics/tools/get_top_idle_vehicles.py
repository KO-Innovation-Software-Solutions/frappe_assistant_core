"""
List vehicles with highest idle durations.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient


class GetTopIdleVehicles(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_top_idle_vehicles"
		self.description = (
			"Lists vehicles with the highest idle durations in a given period. "
			"Use this for 'Which vehicles idled the most today?', "
			"'Top 5 idling vehicles this week'."
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"from_date": {"type": "string", "description": "Start ISO 8601 UTC"},
				"to_date":   {"type": "string", "description": "End ISO 8601 UTC"},
				"limit":     {"type": "integer", "description": "Number of top vehicles (default: 5)"},
			},
			"required": ["from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		from_date = arguments.get("from_date")
		to_date   = arguments.get("to_date")
		limit     = arguments.get("limit", 5)
		try:
			client  = TraccarClient()
			devices = client.get_devices()
			results = []

			for d in devices:
				dev_id    = d.get("id")
				raw_stops = client.get_stops(dev_id, from_date, to_date)
				total_idle = sum(
					s.get("duration", 0)
					for s in raw_stops
					if s.get("engineHours", 0) > 0
				)
				if total_idle > 0:
					results.append({
						"vehicle":           d.get("name"),
						"total_idle_minutes": round(total_idle / 60, 1),
					})

			results.sort(key=lambda x: x["total_idle_minutes"], reverse=True)

			return {
				"success":   True,
				"from_date": from_date, "to_date": to_date,
				"vehicles":  results[:limit],
			}
		except Exception as e:
			frappe.log_error(str(e), "GetTopIdleVehicles.execute")
			return {"success": False, "error": str(e)}


get_top_idle_vehicles = GetTopIdleVehicles()