"""
Get complete daily movement report for a vehicle.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetDailyMovementReport(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_daily_movement_report"
		self.description = (
			"Provides a complete daily movement report: trips, stops, distance, speed, events. "
			"Use this for 'Give me the daily report for X', 'Full movement report for TN01AB1234 today'."
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle": {"type": "string", "description": "Vehicle name in Frappe"},
				"date":    {"type": "string", "description": "Date in format YYYY-MM-DD"},
			},
			"required": ["vehicle", "date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle = arguments.get("vehicle")
		date    = arguments.get("date")
		from_date = f"{date}T00:00:00Z"
		to_date   = f"{date}T23:59:59Z"
		try:
			device_id = resolve_device_id(vehicle)
			client    = TraccarClient()

			trips  = client.get_trips(device_id, from_date, to_date)
			stops  = client.get_stops(device_id, from_date, to_date)
			events = client.get_events(device_id, from_date, to_date)
			raw    = client.get_summary(device_id, from_date, to_date)
			summary = raw[0] if isinstance(raw, list) and raw else (raw or {})

			return {
				"success":          True,
				"vehicle":          vehicle,
				"date":             date,
				"distance_km":      round(summary.get("distance", 0) / 1000, 2),
				"max_speed_kmh":    round(summary.get("maxSpeed", 0) * 1.852, 2),
				"avg_speed_kmh":    round(summary.get("averageSpeed", 0) * 1.852, 2),
				"engine_hours":     round(summary.get("engineHours", 0) / 3600, 2),
				"trip_count":       len(trips),
				"stop_count":       len(stops),
				"event_count":      len(events),
				"trips":            [{"start": t.get("startTime"), "end": t.get("endTime"), "distance_km": round(t.get("distance", 0) / 1000, 2)} for t in trips],
				"stops":            [{"start": s.get("startTime"), "end": s.get("endTime"), "duration_min": round(s.get("duration", 0) / 60, 1), "address": s.get("address")} for s in stops],
			}
		except Exception as e:
			frappe.log_error(str(e), "GetDailyMovementReport.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_daily_movement_report = GetDailyMovementReport()