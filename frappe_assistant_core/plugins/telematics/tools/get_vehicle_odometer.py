"""
Get the latest odometer reading from a vehicle's tracking device.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleOdometer(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_odometer"
		self.description = (
			"Retrieves the latest odometer reading from the tracking device. "
			"Use this for 'What is the odometer reading for vehicle X?', "
			"'How many total km on TN01AB1234?'"
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
			client    = TraccarClient()
			positions = client.get_positions(device_id=device_id)
			position  = positions[0] if positions else {}
			attrs     = position.get("attributes", {})

			odometer_m  = attrs.get("totalDistance", attrs.get("odometer", 0))
			odometer_km = round(odometer_m / 1000, 2)

			return {
				"success":      True,
				"vehicle":      vehicle,
				"odometer_km":  odometer_km,
				"odometer_m":   odometer_m,
				"device_time":  position.get("deviceTime"),
			}
		except Exception as e:
			frappe.log_error(str(e), "GetVehicleOdometer.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_odometer = GetVehicleOdometer()