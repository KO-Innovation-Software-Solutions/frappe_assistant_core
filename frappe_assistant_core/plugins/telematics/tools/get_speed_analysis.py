"""
Get speed analysis for a vehicle: avg, max, min speed and trends.
"""

from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetSpeedAnalysis(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_speed_analysis"
		self.description = (
			"Provides average speed, maximum speed, minimum speed, and speed trend analysis "
			"for a vehicle over a date range. "
			"Use this for 'What was the average speed of X today?', 'Speed analysis for TN01AB1234'."
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle": {"type": "string", "description": "Vehicle name in Frappe"},
				"from_date": {"type": "string", "description": "Start ISO 8601 UTC e.g. '2024-06-01T00:00:00Z'"},
				"to_date": {"type": "string", "description": "End ISO 8601 UTC e.g. '2024-06-01T23:59:59Z'"},
			},
			"required": ["vehicle", "from_date", "to_date"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle, from_date, to_date = arguments.get("vehicle"), arguments.get("from_date"), arguments.get("to_date")
		try:
			device_id = resolve_device_id(vehicle)
			client = TraccarClient()
			raw = client.get_summary(device_id, from_date, to_date)
			summary = raw[0] if isinstance(raw, list) and raw else (raw or {})

			avg_speed = round(summary.get("averageSpeed", 0) * 1.852, 2)
			max_speed = round(summary.get("maxSpeed", 0) * 1.852, 2)

			return {
				"success": True, "vehicle": vehicle,
				"from_date": from_date, "to_date": to_date,
				"avg_speed_kmh": avg_speed,
				"max_speed_kmh": max_speed,
				"distance_km": round(summary.get("distance", 0) / 1000, 2),
			}
		except Exception as e:
			frappe.log_error(str(e), "GetSpeedAnalysis.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_speed_analysis = GetSpeedAnalysis()