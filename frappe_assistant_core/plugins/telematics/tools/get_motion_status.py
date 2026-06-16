"""
Get whether a vehicle is currently moving or stationary.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetMotionStatus(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_motion_status"
		self.description = (
			"Indicates whether the vehicle is currently moving or stationary. "
			"Use this for 'Is vehicle X moving right now?', "
			"'Is TN01AB1234 parked or in motion?'"
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
			speed     = position.get("speed", 0)
			speed_kmh = round(speed * 1.852, 2)
			motion    = position.get("attributes", {}).get("motion", speed > 1)

			return {
				"success":     True,
				"vehicle":     vehicle,
				"is_moving":   bool(motion),
				"status":      "Moving" if motion else "Stationary",
				"speed_kmh":   speed_kmh,
				"latitude":    position.get("latitude"),
				"longitude":   position.get("longitude"),
				"device_time": position.get("deviceTime"),
			}
		except Exception as e:
			frappe.log_error(str(e), "GetMotionStatus.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_motion_status = GetMotionStatus()