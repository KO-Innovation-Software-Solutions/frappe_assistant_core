"""
Get current GPS position of a vehicle from Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehiclePosition(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_position"
		self.description = (
			"Get the current (latest) live GPS position of a vehicle from Traccar telematics. "
			"Returns latitude, longitude, speed (km/h), course, address, ignition status, "
			"odometer, and timestamp. Use this to answer 'Where is vehicle X right now?'"
		)
		self.requires_permission = None

		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle": {
					"type": "string",
					"description": "Vehicle name as stored in Frappe (e.g. 'TN01AB1234')",
				},
			},
			"required": ["vehicle"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle = arguments.get("vehicle")

		try:
			device_id = resolve_device_id(vehicle)
			client = TraccarClient()
			positions = client.get_positions(device_id)

			if not positions:
				return {
					"success": False,
					"vehicle": vehicle,
					"message": f"No position data found for vehicle {vehicle}",
				}

			latest = positions[-1]
			attrs = latest.get("attributes", {})
			address = latest.get("address")
			frappe.logger().info(
				f"Reverse geocode: {latest.get('latitude')}, {latest.get('longitude')}"
			)
			if not address:
				address = client.reverse_geocode(
					latest.get("latitude"),
					latest.get("longitude")
				)

			return {
				"success": True,
				"vehicle": vehicle,
				"device_id": device_id,
				"latitude": latest.get("latitude"),
				"longitude": latest.get("longitude"),
				"speed_kmh": round(latest.get("speed", 0) * 1.852, 2),
				"course": latest.get("course"),
				"address": address,
				"fix_time": latest.get("fixTime"),
				"server_time": latest.get("serverTime"),
				"ignition": attrs.get("ignition"),
				"odometer_km": round(attrs["totalDistance"] / 1000, 2) if attrs.get("totalDistance") else None,
			}

		except Exception as e:
			frappe.log_error(str(e), "GetVehiclePosition.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_position = GetVehiclePosition