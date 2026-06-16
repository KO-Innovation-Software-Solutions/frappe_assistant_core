"""
Summarize vehicle activity: trips, stops, events, and utilization.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetVehicleActivityReport(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_vehicle_activity_report"
		self.description = (
			"Summarizes vehicle activity including trips, stops, events, and utilization for a period. "
			"Use this for 'Activity report for X this week', 'Summarize TN01AB1234 activity'."
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

			trips   = client.get_trips(device_id, from_date, to_date)
			stops   = client.get_stops(device_id, from_date, to_date)
			events  = client.get_events(device_id, from_date, to_date)
			raw     = client.get_summary(device_id, from_date, to_date)
			summary = raw[0] if isinstance(raw, list) and raw else (raw or {})

			total_stop_min   = sum(s.get("duration", 0) for s in stops) / 60
			total_trip_dist  = sum(t.get("distance", 0) for t in trips) / 1000
			event_types      = {}
			for e in events:
				t = e.get("type", "unknown")
				event_types[t] = event_types.get(t, 0) + 1

			return {
				"success":          True,
				"vehicle":          vehicle,
				"from_date":        from_date,
				"to_date":          to_date,
				"trip_count":       len(trips),
				"stop_count":       len(stops),
				"total_distance_km": round(total_trip_dist, 2),
				"total_stop_minutes": round(total_stop_min, 1),
				"engine_hours":     round(summary.get("engineHours", 0) / 3600, 2),
				"max_speed_kmh":    round(summary.get("maxSpeed", 0) * 1.852, 2),
				"event_summary":    event_types,
			}
		except Exception as e:
			frappe.log_error(str(e), "GetVehicleActivityReport.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_vehicle_activity_report = GetVehicleActivityReport()