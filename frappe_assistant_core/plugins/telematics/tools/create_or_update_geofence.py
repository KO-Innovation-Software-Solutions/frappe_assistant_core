"""
Create or update a geofence in Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient


class CreateOrUpdateGeofence(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "create_or_update_geofence"
		self.description = (
			"Create a new geofence (circular zone) in Traccar, or return the existing one if a geofence "
			"with the same name already exists. "
			"Use this for 'Create a geofence at the depot', 'Add a zone called Warehouse at this location', "
			"'Set up a geofence for Chennai HQ at lat 13.08, lng 80.27 with 200m radius'."
		)
		self.requires_permission = None

		self.inputSchema = {
			"type": "object",
			"properties": {
				"name": {
					"type": "string",
					"description": "Name of the geofence (e.g. 'Chennai Depot', 'Warehouse A')",
				},
				"latitude": {
					"type": "number",
					"description": "Center latitude of the geofence circle",
				},
				"longitude": {
					"type": "number",
					"description": "Center longitude of the geofence circle",
				},
				"radius": {
					"type": "number",
					"description": "Radius in meters (default: 100)",
				},
			},
			"required": ["name", "latitude", "longitude"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		name      = arguments.get("name")
		latitude  = arguments.get("latitude")
		longitude = arguments.get("longitude")
		radius    = arguments.get("radius", 100)

		try:
			client     = TraccarClient()
			geofence_id = client.create_or_update_geofence(name, latitude, longitude, radius)

			return {
				"success":     True,
				"geofence_id": geofence_id,
				"name":        name,
				"latitude":    latitude,
				"longitude":   longitude,
				"radius":      radius,
				"message":     f"Geofence '{name}' ready with ID {geofence_id}",
			}

		except Exception as e:
			frappe.log_error(str(e), "CreateOrUpdateGeofence.execute")
			return {"success": False, "error": str(e)}


create_or_update_geofence = CreateOrUpdateGeofence