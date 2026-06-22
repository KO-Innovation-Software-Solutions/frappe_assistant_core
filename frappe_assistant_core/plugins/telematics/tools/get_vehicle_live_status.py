"""
Get live status of a vehicle: Running, Idle, Parked, or Offline.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleLiveStatus(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_live_status"
		self.description = (
			"Returns whether a vehicle is Running, Idle, Parked, or Offline "
			"along with ignition state and connectivity status. "
			"Use this for 'Is vehicle X running?', 'What is the status of TN01AB1234?'"
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

			positions = client.get_positions(device_id=device_id)

			devices = client.get_all_devices()

			device = next(
				(d for d in devices if d.get("id") == device_id),
				{}
			)

			position = positions[-1] if positions else {}

			attrs = position.get("attributes", {})

			speed = position.get("speed", 0)
			ignition = attrs.get("ignition", False)
			motion = attrs.get("motion", False)

			device_status = device.get("status", "unknown")

			if device_status == "offline":
				status = "Offline"
			elif motion:
				status = "Running"
			elif ignition:
				status = "Idle"
			else:
				status = "Parked"

			return {
				"success":      True,
				"vehicle":      vehicle,
				"status":       status,
				"ignition":     ignition,
				"speed_kmh":    round(speed * 1.852, 2),
				"connectivity": device_status,
				"last_update":  position.get("deviceTime"),
			}
		except Exception as e:
			frappe.log_error(str(e), "GetVehicleLiveStatus.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_live_status = GetVehicleLiveStatus()