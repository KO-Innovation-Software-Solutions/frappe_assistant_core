"""
Get current ignition state of a vehicle from Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetIgnitionStatus(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_ignition_status"
		self.description = (
			"Returns the current ignition state of the vehicle (ON/OFF). "
			"Use this for 'Is the ignition on for vehicle X?', "
			"'Is TN01AB1234 engine running?'"
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
			ignition  = attrs.get("ignition", False)

			return {
				"success":        True,
				"vehicle":        vehicle,
				"ignition":       ignition,
				"ignition_state": "ON" if ignition else "OFF",
				"device_time":    position.get("deviceTime"),
				"speed_kmh":      round(position.get("speed", 0) * 1.852, 2),
			}
		except Exception as e:
			frappe.log_error(str(e), "GetIgnitionStatus.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_ignition_status = GetIgnitionStatus()