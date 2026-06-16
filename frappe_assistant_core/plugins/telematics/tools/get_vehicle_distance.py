"""
Calculate total distance traveled by a vehicle within a date range.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleDistance(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_distance"
		self.description = (
			"Calculates total distance traveled by a vehicle within a specified date range. "
			"Use this for 'How far did vehicle X travel today?', "
			"'Total km for TN01AB1234 this month?'"
		)
		self.requires_permission = None

		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle": {
					"type": "string",
					"description": "Vehicle name as stored in Frappe (e.g. 'TN01AB1234')",
				},
				"from_date": {
					"type": "string",
					"description": "Start datetime ISO 8601 UTC e.g. '2024-06-01T00:00:00Z'",
				},
				"to_date": {
					"type": "string",
					"description": "End datetime ISO 8601 UTC e.g. '2024-06-01T23:59:59Z'",
				},
			},
			"required": ["vehicle", "from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle   = arguments.get("vehicle")
		from_date = arguments.get("from_date")
		to_date   = arguments.get("to_date")
		try:
			device_id = resolve_device_id(vehicle)
			client    = TraccarClient()
			raw       = client.get_summary(device_id, from_date, to_date)
			summary   = raw[0] if isinstance(raw, list) and raw else (raw or {})

			distance_m  = summary.get("distance", 0)
			distance_km = round(distance_m / 1000, 2)

			return {
				"success":     True,
				"vehicle":     vehicle,
				"from_date":   from_date,
				"to_date":     to_date,
				"distance_km": distance_km,
				"distance_m":  distance_m,
			}
		except Exception as e:
			frappe.log_error(str(e), "GetVehicleDistance.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_distance = GetVehicleDistance()