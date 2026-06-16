"""
Calculate total idle duration and identify long idle periods for a vehicle.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleIdleTime(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_idle_time"
		self.description = (
			"Calculates total idle duration and identifies long idle periods for a vehicle. "
			"Use this for 'How long was X idling today?', 'Show idle periods for TN01AB1234'."
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle": {"type": "string", "description": "Vehicle name in Frappe"},
				"from_date": {"type": "string", "description": "Start ISO 8601 UTC"},
				"to_date": {"type": "string", "description": "End ISO 8601 UTC"},
				"min_idle_minutes": {"type": "integer", "description": "Min idle duration to include (default: 5)"},
			},
			"required": ["vehicle", "from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle         = arguments.get("vehicle")
		from_date       = arguments.get("from_date")
		to_date         = arguments.get("to_date")
		min_idle_min    = arguments.get("min_idle_minutes", 5)
		try:
			device_id = resolve_device_id(vehicle)
			client    = TraccarClient()
			raw_stops = client.get_stops(device_id, from_date, to_date)

			idle_periods       = []
			total_idle_seconds = 0

			for s in raw_stops:
				duration = s.get("duration", 0)
				if s.get("engineHours", 0) > 0 and duration >= min_idle_min * 60:
					total_idle_seconds += duration
					idle_periods.append({
						"start_time":       s.get("startTime"),
						"end_time":         s.get("endTime"),
						"duration_minutes": round(duration / 60, 1),
						"address":          s.get("address"),
						"latitude":         s.get("lat"),
						"longitude":        s.get("lon"),
					})

			return {
				"success": True, "vehicle": vehicle,
				"from_date": from_date, "to_date": to_date,
				"total_idle_minutes": round(total_idle_seconds / 60, 1),
				"idle_period_count":  len(idle_periods),
				"idle_periods":       idle_periods,
			}
		except Exception as e:
			frappe.log_error(str(e), "GetVehicleIdleTime.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_idle_time = GetVehicleIdleTime()