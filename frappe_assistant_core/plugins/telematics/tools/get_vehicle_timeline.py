"""
Generate a chronological timeline of trips, stops, events for a vehicle.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleTimeline(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_timeline"
		self.description = (
			"Generates a chronological timeline of trips, stops, and events for a vehicle. "
			"Use this for 'Show me the full timeline for X today', "
			"'What happened with TN01AB1234 yesterday?'"
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
			timeline  = []

			for t in client.get_trips(device_id, from_date, to_date):
				timeline.append({
					"type": "trip", "start_time": t.get("startTime"),
					"end_time": t.get("endTime"),
					"distance_km": round(t.get("distance", 0) / 1000, 2),
					"avg_speed_kmh": round(t.get("averageSpeed", 0) * 1.852, 2),
				})

			for s in client.get_stops(device_id, from_date, to_date):
				timeline.append({
					"type": "stop", "start_time": s.get("startTime"),
					"end_time": s.get("endTime"),
					"duration_minutes": round(s.get("duration", 0) / 60, 1),
					"address": s.get("address"),
				})

			for e in client.get_events(device_id, from_date, to_date):
				timeline.append({
					"type": "event", "event_type": e.get("type"),
					"event_time": e.get("eventTime"),
				})

			timeline.sort(key=lambda x: x.get("start_time") or x.get("event_time") or "")

			return {"success": True, "vehicle": vehicle, "event_count": len(timeline), "timeline": timeline}
		except Exception as e:
			frappe.log_error(str(e), "GetVehicleTimeline.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_timeline = GetVehicleTimeline()