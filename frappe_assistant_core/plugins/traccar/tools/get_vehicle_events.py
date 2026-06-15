"""
Get telematics events for a vehicle from Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.traccar.traccar_client import TraccarClient, resolve_device_id


class GetVehicleEvents(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_events"
		self.description = (
			"Get telematics events for a vehicle between two dates from Traccar. "
			"Supported event types: geofenceEnter, geofenceExit, deviceOverspeed, "
			"deviceStopped, deviceMoving, deviceOnline, deviceOffline, "
			"ignitionOn, ignitionOff, deviceFuelDrop, deviceFuelIncrease, alarm. "
			"If no types specified, returns all events. "
			"Use this for 'Any overspeed alerts for X today?' or 'Did vehicle X enter the depot?'"
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
					"description": "Start datetime in ISO 8601 UTC format e.g. '2024-06-01T00:00:00Z'",
				},
				"to_date": {
					"type": "string",
					"description": "End datetime in ISO 8601 UTC format e.g. '2024-06-01T23:59:59Z'",
				},
				"event_types": {
					"type": "array",
					"items": {"type": "string"},
					"description": (
						"Optional list of event types to filter. "
						"e.g. ['geofenceEnter', 'geofenceExit', 'deviceOverspeed']"
					),
				},
			},
			"required": ["vehicle", "from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle = arguments.get("vehicle")
		from_date = arguments.get("from_date")
		to_date = arguments.get("to_date")
		event_types = arguments.get("event_types")

		try:
			device_id = resolve_device_id(vehicle)
			client = TraccarClient()
			raw_events = client.get_events(device_id, from_date, to_date, types=event_types)

			events = []
			for e in raw_events:
				events.append({
					"event_id":    e.get("id"),
					"type":        e.get("type"),
					"event_time":  e.get("eventTime"),
					"position_id": e.get("positionId"),
					"geofence_id": e.get("geofenceId"),
					"attributes":  e.get("attributes", {}),
				})

			return {
				"success":     True,
				"vehicle":     vehicle,
				"from_date":   from_date,
				"to_date":     to_date,
				"event_count": len(events),
				"events":      events,
			}

		except Exception as e:
			frappe.log_error(str(e), "GetVehicleEvents.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_events = GetVehicleEvents