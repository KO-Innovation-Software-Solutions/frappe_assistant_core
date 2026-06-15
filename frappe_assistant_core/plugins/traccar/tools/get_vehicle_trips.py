"""
Get trip history for a vehicle from Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.traccar.traccar_client import TraccarClient, resolve_device_id


class GetVehicleTrips(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_trips"
		self.description = (
			"Get trip history for a vehicle between two dates from Traccar telematics. "
			"Returns list of trips with start/end times, distance (km), duration (minutes), "
			"average speed, max speed, and start/end addresses. "
			"Use this for 'How many trips did vehicle X make today?' or 'Show me trips for X this week'."
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
			raw_trips = client.get_trips(device_id, from_date, to_date)

			trips = []
			for t in raw_trips:
				trips.append({
					"start_time":    t.get("startTime"),
					"end_time":      t.get("endTime"),
					"distance_km":   round(t.get("distance", 0) / 1000, 2),
					"duration_min":  round(t.get("duration", 0) / 60000, 1),
					"avg_speed_kmh": round(t.get("averageSpeed", 0) * 1.852, 2),
					"max_speed_kmh": round(t.get("maxSpeed", 0) * 1.852, 2),
					"start_address": t.get("startAddress"),
					"end_address":   t.get("endAddress"),
					"start_lat":     t.get("startLat"),
					"start_lon":     t.get("startLon"),
					"end_lat":       t.get("endLat"),
					"end_lon":       t.get("endLon"),
				})

			return {
				"success":    True,
				"vehicle":    vehicle,
				"from_date":  from_date,
				"to_date":    to_date,
				"trip_count": len(trips),
				"trips":      trips,
			}

		except Exception as e:
			frappe.log_error(str(e), "GetVehicleTrips.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_trips = GetVehicleTrips