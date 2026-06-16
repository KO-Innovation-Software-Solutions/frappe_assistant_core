"""
Get all overspeed violation events for a vehicle from Traccar.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetOverspeedEvents(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_overspeed_events"
		self.description = (
			"Returns all overspeed violations including location, speed recorded, and timestamps. "
			"Use this for 'Show overspeed violations for X today', "
			"'How many times did TN01AB1234 overspeed this week?'"
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle": {"type": "string", "description": "Vehicle name in Frappe"},
				"from_date": {"type": "string", "description": "Start ISO 8601 UTC"},
				"to_date": {"type": "string", "description": "End ISO 8601 UTC"},
			},
			"required": ["vehicle", "from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle, from_date, to_date = arguments.get("vehicle"), arguments.get("from_date"), arguments.get("to_date")
		try:
			device_id = resolve_device_id(vehicle)
			client = TraccarClient()
			raw = client.get_events(device_id, from_date, to_date, types=["deviceOverspeed"])

			events = []
			for e in raw:
				attrs = e.get("attributes", {})
				events.append({
					"event_id":   e.get("id"),
					"event_time": e.get("eventTime"),
					"speed_kmh":  round(attrs.get("speed", 0) * 1.852, 2),
					"position_id": e.get("positionId"),
					"attributes": attrs,
				})

			return {
				"success": True, "vehicle": vehicle,
				"from_date": from_date, "to_date": to_date,
				"violation_count": len(events),
				"events": events,
			}
		except Exception as e:
			frappe.log_error(str(e), "GetOverspeedEvents.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_overspeed_events = GetOverspeedEvents()