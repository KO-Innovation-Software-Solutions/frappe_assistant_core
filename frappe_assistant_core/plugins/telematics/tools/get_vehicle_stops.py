"""
Get stop history for a vehicle from Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleStops(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_stops"
		self.description = (
			"Get stop history for a vehicle between two dates from Traccar telematics. "
			"Returns list of stops with location (lat/lon), address, and duration in minutes. "
			"Use this for 'Where did vehicle X stop today?' or 'How long did X stop at each location?'"
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
			raw_stops = client.get_stops(device_id, from_date, to_date)

			stops = []
			for s in raw_stops:
				stops.append({
					"start_time":   s.get("startTime"),
					"end_time":     s.get("endTime"),
					"duration_min": round(s.get("duration", 0) / 60000, 1),
					"address":      s.get("address"),
					"latitude":     s.get("lat"),
					"longitude":    s.get("lon"),
				})

			return {
				"success":    True,
				"vehicle":    vehicle,
				"from_date":  from_date,
				"to_date":    to_date,
				"stop_count": len(stops),
				"stops":      stops,
			}

		except Exception as e:
			frappe.log_error(str(e), "GetVehicleStops.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_stops = GetVehicleStops