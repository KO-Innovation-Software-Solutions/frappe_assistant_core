"""
Get GPS route/path polyline for a vehicle from Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleRoute(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_route"
		self.description = (
			"Get the GPS route/path (polyline) of a vehicle between two dates from Traccar. "
			"Returns a list of position points with latitude, longitude, speed, course, and time. "
			"Useful for route replay or drawing a vehicle's path on a map. "
			"Use this for 'Show me the route vehicle X took today'."
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
			raw_route = client.get_route(device_id, from_date, to_date)

			route_points = []
			for p in raw_route:
				route_points.append({
					"latitude":  p.get("latitude"),
					"longitude": p.get("longitude"),
					"speed_kmh": round(p.get("speed", 0) * 1.852, 2),
					"course":    p.get("course"),
					"fix_time":  p.get("fixTime"),
				})

			return {
				"success":     True,
				"vehicle":     vehicle,
				"from_date":   from_date,
				"to_date":     to_date,
				"point_count": len(route_points),
				"route":       route_points,
			}

		except Exception as e:
			frappe.log_error(str(e), "GetVehicleRoute.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_route = GetVehicleRoute