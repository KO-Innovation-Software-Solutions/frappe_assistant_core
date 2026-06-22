"""
Get active alerts and critical events requiring attention from Traccar.
"""

from typing import Any, Dict
from datetime import datetime, timezone, timedelta

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient


class GetActiveAlerts(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_active_alerts"
		self.description = (
			"Returns active alerts and critical events requiring attention across the fleet. "
			"Includes overspeed, alarms, geofence violations, and device issues. "
			"Use this for 'Any active alerts?', 'Show critical fleet events right now'."
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"lookback_minutes": {"type": "integer", "description": "How far back to check for alerts in minutes (default: 60)"},
				"event_types": {
					"type": "array", "items": {"type": "string"},
					"description": "Filter by event types e.g. ['deviceOverspeed', 'alarm']",
				},
			},
			"required": [],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		lookback  = arguments.get("lookback_minutes", 60)
		types     = arguments.get("event_types")
		try:
			client    = TraccarClient()
			devices   = client.get_all_devices()
			now       = datetime.now(timezone.utc)
			from_date = (now - timedelta(minutes=lookback)).strftime("%Y-%m-%dT%H:%M:%SZ")
			to_date   = now.strftime("%Y-%m-%dT%H:%M:%SZ")
			dev_names = {d.get("id"): d.get("name") for d in devices}

			critical_types = types or [
				"deviceOverspeed", "alarm", "geofenceEnter", "geofenceExit",
				"deviceOffline", "deviceFuelDrop",
			]

			alerts = []
			for d in devices:
				events = client.get_events(d.get("id"), from_date, to_date, types=critical_types)
				for e in events:
					alerts.append({
						"vehicle":     dev_names.get(e.get("deviceId"), "Unknown"),
						"event_type":  e.get("type"),
						"event_time":  e.get("eventTime"),
						"position_id": e.get("positionId"),
						"attributes":  e.get("attributes", {}),
					})

			alerts.sort(key=lambda x: x.get("event_time") or "", reverse=True)

			return {
				"success":      True,
				"from_date":    from_date,
				"to_date":      to_date,
				"alert_count":  len(alerts),
				"alerts":       alerts,
			}
		except Exception as e:
			frappe.log_error(str(e), "GetActiveAlerts.execute")
			return {"success": False, "error": str(e)}


get_active_alerts = GetActiveAlerts()