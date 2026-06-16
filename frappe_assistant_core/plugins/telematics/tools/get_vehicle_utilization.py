"""
Measure vehicle utilization: running time vs available time.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleUtilization(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_utilization"
		self.description = (
			"Measures vehicle utilization based on running time versus available time. "
			"Use this for 'How utilized is vehicle X this week?', "
			"'What is the utilization rate for TN01AB1234?'"
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle": {"type": "string", "description": "Vehicle name in Frappe"},
				"from_date": {"type": "string", "description": "Start ISO 8601 UTC"},
				"to_date": {"type": "string", "description": "End ISO 8601 UTC"},
				"available_hours_per_day": {"type": "number", "description": "Working hours per day (default: 8)"},
			},
			"required": ["vehicle", "from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle             = arguments.get("vehicle")
		from_date           = arguments.get("from_date")
		to_date             = arguments.get("to_date")
		available_hours_day = arguments.get("available_hours_per_day", 8)
		try:
			device_id = resolve_device_id(vehicle)
			client    = TraccarClient()
			raw       = client.get_summary(device_id, from_date, to_date)
			summary   = raw[0] if isinstance(raw, list) and raw else (raw or {})

			engine_hours    = summary.get("engineHours", 0) / 3600
			trips           = client.get_trips(device_id, from_date, to_date)
			trip_count      = len(trips)

			from datetime import datetime
			try:
				dt_from = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
				dt_to   = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
				days    = max((dt_to - dt_from).days, 1)
			except Exception:
				days = 1

			available_hours   = days * available_hours_day
			utilization_pct   = round((engine_hours / available_hours) * 100, 1) if available_hours else 0

			return {
				"success": True, "vehicle": vehicle,
				"from_date": from_date, "to_date": to_date,
				"engine_hours":       round(engine_hours, 2),
				"available_hours":    available_hours,
				"utilization_pct":    utilization_pct,
				"trip_count":         trip_count,
				"distance_km":        round(summary.get("distance", 0) / 1000, 2),
			}
		except Exception as e:
			frappe.log_error(str(e), "GetVehicleUtilization.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_utilization = GetVehicleUtilization()