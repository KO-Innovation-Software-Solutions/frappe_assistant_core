"""
Get geofence entry/exit history for a vehicle from Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetGeofenceHistory(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_geofence_history"
		self.description = (
			"Retrieves vehicle geofence entry and exit history for a selected period. "
			"Use this for 'Did vehicle X enter the depot today?', "
			"'Show geofence history for TN01AB1234 this week'."
		)
		self.requires_permission = None

		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle": {
					"type": "string",
					"description": "Vehicle name as stored in Frappe (e.g. 'TN01AB1234')",
				},
				"from_date": {
					"type": "string",
					"description": "Start datetime ISO 8601 UTC e.g. '2024-06-01T00:00:00Z'",
				},
				"to_date": {
					"type": "string",
					"description": "End datetime ISO 8601 UTC e.g. '2024-06-01T23:59:59Z'",
				},
				"geofence_name": {
					"type": "string",
					"description": "Optional geofence name to filter results",
				},
			},
			"required": ["vehicle", "from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle       = arguments.get("vehicle")
		from_date     = arguments.get("from_date")
		to_date       = arguments.get("to_date")
		geofence_name = arguments.get("geofence_name")

		try:
			device_id = resolve_device_id(vehicle)
			client    = TraccarClient()
			raw       = client.get_events(
				device_id, from_date, to_date,
				types=["geofenceEnter", "geofenceExit"],
			)

			geofences = {g.get("id"): g.get("name") for g in client.get_geofences()}

			history = []
			for e in raw:
				gf_id   = e.get("geofenceId")
				gf_name = geofences.get(gf_id, f"Geofence {gf_id}")
				if geofence_name and gf_name.lower() != geofence_name.lower():
					continue
				history.append({
					"event_type":    e.get("type"),
					"event_time":    e.get("eventTime"),
					"geofence_id":   gf_id,
					"geofence_name": gf_name,
					"position_id":   e.get("positionId"),
				})

			return {
				"success":       True,
				"vehicle":       vehicle,
				"from_date":     from_date,
				"to_date":       to_date,
				"event_count":   len(history),
				"history":       history,
			}
		except Exception as e:
			frappe.log_error(str(e), "GetGeofenceHistory.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_geofence_history = GetGeofenceHistory()