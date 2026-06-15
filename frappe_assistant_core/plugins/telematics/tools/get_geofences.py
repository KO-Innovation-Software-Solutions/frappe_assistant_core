"""
Get all geofences from Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetGeofences(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_geofences"
		self.description = (
			"Get all geofences (zones) configured in Traccar. "
			"Optionally filter for a specific vehicle to get its assigned geofences. "
			"Returns geofence IDs, names, and area definitions. "
			"Use this for 'List all geofences' or 'What zones is vehicle X assigned to?'"
		)
		self.requires_permission = None

		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle": {
					"type": "string",
					"description": "Optional vehicle name to filter device-specific geofences",
				},
			},
			"required": [],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle = arguments.get("vehicle")
		device_id = None

		try:
			if vehicle:
				try:
					device_id = resolve_device_id(vehicle)
				except Exception:
					pass  # Still return all geofences if vehicle not resolved

			client = TraccarClient()
			raw = client.get_geofences(device_id=device_id)

			geofences = [
				{
					"geofence_id": g["id"],
					"name":        g.get("name", ""),
					"area":        g.get("area", ""),
					"attributes":  g.get("attributes", {}),
				}
				for g in raw
			]

			return {
				"success":        True,
				"geofence_count": len(geofences),
				"geofences":      geofences,
			}

		except Exception as e:
			frappe.log_error(str(e), "GetGeofences.execute")
			return {"success": False, "error": str(e)}


get_geofences = GetGeofences