"""
Get the latest communication timestamp from a vehicle's GPS device.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleLastUpdate(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_last_update"
		self.description = (
			"Returns the latest communication timestamp received from the GPS device. "
			"Use this for 'When did vehicle X last report?', "
			"'Is the GPS device on TN01AB1234 communicating?'"
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
			devices   = client.get_devices()
			device    = next((d for d in devices if d.get("id") == device_id), None)

			if not device:
				return {"success": False, "vehicle": vehicle, "error": "Device not found"}

			positions = client.get_positions(device_id=device_id)
			position  = positions[0] if positions else {}

			return {
				"success":          True,
				"vehicle":          vehicle,
				"last_update":      device.get("lastUpdate"),
				"device_time":      position.get("deviceTime"),
				"fix_time":         position.get("fixTime"),
				"server_time":      position.get("serverTime"),
				"device_status":    device.get("status"),
			}
		except Exception as e:
			frappe.log_error(str(e), "GetVehicleLastUpdate.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_last_update = GetVehicleLastUpdate()