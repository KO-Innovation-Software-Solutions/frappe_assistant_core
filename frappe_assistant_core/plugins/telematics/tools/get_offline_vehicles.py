"""
List vehicles that have not reported data within a specified period.
"""

from typing import Any, Dict
from datetime import datetime, timezone, timedelta

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient


class GetOfflineVehicles(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_offline_vehicles"
		self.description = (
			"Lists vehicles that have not reported data within a specified period. "
			"Use this for 'Which vehicles are offline?', "
			"'Vehicles not reporting for more than 1 hour'."
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"offline_minutes": {"type": "integer", "description": "Minutes without update to consider offline (default: 60)"},
			},
			"required": [],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		offline_minutes = arguments.get("offline_minutes", 60)
		try:
			# Get only Frappe-registered vehicles
			frappe_vehicles = {
				v["name"].replace(" ", "").upper()
				for v in frappe.get_all("Vehicle", fields=["name"], ignore_permissions=True)
			}
			client  = TraccarClient()
			devices = client.get_all_devices()

			# Filter only Frappe vehicles
			devices = [
				d for d in devices
				if d.get("name", "").replace(" ", "").upper() in frappe_vehicles
			]

			now       = datetime.now(timezone.utc)
			threshold = now - timedelta(minutes=offline_minutes)
			offline   = []

			for d in devices:
				last_update_str = d.get("lastUpdate")
				if not last_update_str:
					offline.append({"name": d.get("name"), "last_update": None, "minutes_offline": None})
					continue
				try:
					last_update = datetime.fromisoformat(last_update_str.replace("Z", "+00:00"))
					if last_update < threshold:
						mins_offline = round((now - last_update).total_seconds() / 60, 1)
						offline.append({"name": d.get("name"), "last_update": last_update_str, "minutes_offline": mins_offline})
				except Exception:
					offline.append({"name": d.get("name"), "last_update": last_update_str, "minutes_offline": None})

			offline.sort(key=lambda x: x.get("minutes_offline") or 999999, reverse=True)

			return {
				"success":        True,
				"offline_count":  len(offline),
				"threshold_mins": offline_minutes,
				"vehicles":       offline,
			}
		except Exception as e:
			frappe.log_error(str(e), "GetOfflineVehicles.execute")
			return {"success": False, "error": str(e)}


get_offline_vehicles = GetOfflineVehicles()