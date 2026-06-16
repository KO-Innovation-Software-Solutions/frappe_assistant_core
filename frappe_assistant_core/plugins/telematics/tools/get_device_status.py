"""
Get device connectivity, battery, signal quality and health indicators from Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetDeviceStatus(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_device_status"
		self.description = (
			"Provides device connectivity status, battery information, signal quality, "
			"and device health indicators. "
			"Use this for 'Is the GPS device on X healthy?', "
			"'What is the battery level of vehicle TN01AB1234 tracker?'"
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
			devices   = client.get_devices()
			device    = next((d for d in devices if d.get("id") == device_id), {})
			position  = positions[0] if positions else {}
			attrs     = position.get("attributes", {})

			return {
				"success":        True,
				"vehicle":        vehicle,
				"connectivity":   device.get("status", "unknown"),
				"last_update":    device.get("lastUpdate"),
				"battery_level":  attrs.get("batteryLevel"),
				"power":          attrs.get("power"),
				"rssi":           attrs.get("rssi"),
				"gps_accuracy":   position.get("accuracy"),
				"satellites":     attrs.get("sat"),
				"hdop":           attrs.get("hdop"),
				"valid_fix":      position.get("valid"),
			}
		except Exception as e:
			frappe.log_error(str(e), "GetDeviceStatus.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_device_status = GetDeviceStatus()