"""
List vehicles with highest running hours or distance traveled.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient


class GetTopRunningVehicles(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_top_running_vehicles"
		self.description = (
			"Lists vehicles with the highest running hours or distance traveled in a period. "
			"Use this for 'Which vehicles ran the most today?', "
			"'Top 5 vehicles by distance this week'."
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"from_date": {"type": "string", "description": "Start ISO 8601 UTC"},
				"to_date":   {"type": "string", "description": "End ISO 8601 UTC"},
				"limit":     {"type": "integer", "description": "Number of top vehicles (default: 5)"},
				"sort_by":   {"type": "string", "description": "'distance' or 'hours' (default: distance)", "enum": ["distance", "hours"]},
			},
			"required": ["from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		from_date = arguments.get("from_date")
		to_date   = arguments.get("to_date")
		limit     = arguments.get("limit", 5)
		sort_by   = arguments.get("sort_by", "distance")
		try:
			client  = TraccarClient()
			devices = client.get_all_devices()
			results = []

			for d in devices:
				dev_id = d.get("id")
				raw    = client.get_summary(dev_id, from_date, to_date)
				s      = raw[0] if isinstance(raw, list) and raw else (raw or {})
				if not s:
					continue
				results.append({
					"vehicle":      d.get("name"),
					"distance_km":  round(s.get("distance", 0) / 1000, 2),
					"engine_hours": round(s.get("engineHours", 0) / 3600, 2),
				})

			key = "distance_km" if sort_by == "distance" else "engine_hours"
			results.sort(key=lambda x: x[key], reverse=True)

			return {
				"success":   True,
				"from_date": from_date, "to_date": to_date,
				"sort_by":   sort_by,
				"vehicles":  results[:limit],
			}
		except Exception as e:
			frappe.log_error(str(e), "GetTopRunningVehicles.execute")
			return {"success": False, "error": str(e)}


get_top_running_vehicles = GetTopRunningVehicles()