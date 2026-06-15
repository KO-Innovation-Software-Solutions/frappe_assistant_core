"""
Get summary report for a vehicle from Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.traccar.traccar_client import TraccarClient, resolve_device_id


class GetVehicleSummary(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_summary"
		self.description = (
			"Get a summary report for a vehicle between two dates from Traccar telematics. "
			"Returns total distance (km), engine hours, average speed, and max speed. "
			"Use this for 'How far did vehicle X travel this month?' or 'Total engine hours for X today?'"
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
					"description": "Start datetime in ISO 8601 UTC format e.g. '2024-06-01T00:00:00Z'",
				},
				"to_date": {
					"type": "string",
					"description": "End datetime in ISO 8601 UTC format e.g. '2024-06-01T23:59:59Z'",
				},
			},
			"required": ["vehicle", "from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle = arguments.get("vehicle")
		from_date = arguments.get("from_date")
		to_date = arguments.get("to_date")

		try:
			device_id = resolve_device_id(vehicle)
			client = TraccarClient()
			raw = client.get_summary(device_id, from_date, to_date)

			# Traccar returns a list — one entry per device
			summary = raw[0] if isinstance(raw, list) and raw else (raw or {})

			return {
				"success":        True,
				"vehicle":        vehicle,
				"from_date":      from_date,
				"to_date":        to_date,
				"distance_km":    round(summary.get("distance", 0) / 1000, 2),
				"avg_speed_kmh":  round(summary.get("averageSpeed", 0) * 1.852, 2),
				"max_speed_kmh":  round(summary.get("maxSpeed", 0) * 1.852, 2),
				"engine_hours":   round(summary.get("engineHours", 0) / 3600000, 2),
			}

		except Exception as e:
			frappe.log_error(str(e), "GetVehicleSummary.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_summary = GetVehicleSummary