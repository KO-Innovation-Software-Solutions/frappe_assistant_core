"""
Get GPS position history for a vehicle for playback and analysis.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleLocationHistory(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_location_history"
		self.description = (
			"Retrieves GPS position history for a vehicle for playback and analysis. "
			"Use this for 'Show location history for X today', "
			"'GPS trail for TN01AB1234 between 9am and 5pm'."
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle":   {"type": "string", "description": "Vehicle name in Frappe"},
				"from_date": {"type": "string", "description": "Start ISO 8601 UTC"},
				"to_date":   {"type": "string", "description": "End ISO 8601 UTC"},
			},
			"required": ["vehicle", "from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle, from_date, to_date = arguments.get("vehicle"), arguments.get("from_date"), arguments.get("to_date")
		try:
			device_id = resolve_device_id(vehicle)
			client    = TraccarClient()
			raw       = client.get_route(device_id, from_date, to_date)

			positions = [{
				"latitude":    p.get("latitude"),
				"longitude":   p.get("longitude"),
				"speed_kmh":   round(p.get("speed", 0) * 1.852, 2),
				"device_time": p.get("deviceTime"),
				"valid":       p.get("valid"),
			} for p in raw]

			return {
				"success":        True,
				"vehicle":        vehicle,
				"from_date":      from_date,
				"to_date":        to_date,
				"position_count": len(positions),
				"positions":      positions,
			}
		except Exception as e:
			frappe.log_error(str(e), "GetVehicleLocationHistory.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_location_history = GetVehicleLocationHistory()