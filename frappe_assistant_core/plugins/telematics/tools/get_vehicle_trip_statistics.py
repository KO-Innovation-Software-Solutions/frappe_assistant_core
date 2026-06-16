"""
Get trip statistics: count, avg duration, avg distance, efficiency for a vehicle.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleTripStatistics(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_trip_statistics"
		self.description = (
			"Provides trip counts, average trip duration, average distance, and trip efficiency metrics. "
			"Use this for 'Trip stats for X this week', 'Average trip distance for TN01AB1234'."
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle":   {"type": "string", "description": "Vehicle name in Frappe"},
				"from_date": {"type": "string", "description": "Start ISO 8601 UTC"},
				"to_date":   {"type": "string", "description": "End ISO 8601 UTC"},
			},
			"required": ["vehicle", "from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle, from_date, to_date = arguments.get("vehicle"), arguments.get("from_date"), arguments.get("to_date")
		try:
			device_id = resolve_device_id(vehicle)
			client    = TraccarClient()
			trips     = client.get_trips(device_id, from_date, to_date)

			if not trips:
				return {"success": True, "vehicle": vehicle, "trip_count": 0, "message": "No trips found"}

			durations  = [t.get("duration", 0) for t in trips]
			distances  = [t.get("distance", 0) for t in trips]
			speeds     = [t.get("averageSpeed", 0) * 1.852 for t in trips]

			return {
				"success":            True,
				"vehicle":            vehicle,
				"from_date":          from_date,
				"to_date":            to_date,
				"trip_count":         len(trips),
				"total_distance_km":  round(sum(distances) / 1000, 2),
				"avg_distance_km":    round(sum(distances) / len(distances) / 1000, 2),
				"avg_duration_min":   round(sum(durations) / len(durations) / 60, 1),
				"avg_speed_kmh":      round(sum(speeds) / len(speeds), 2),
				"max_speed_kmh":      round(max(t.get("maxSpeed", 0) * 1.852 for t in trips), 2),
			}
		except Exception as e:
			frappe.log_error(str(e), "GetVehicleTripStatistics.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_trip_statistics = GetVehicleTripStatistics()