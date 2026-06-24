"""
Find the nearest vehicle to a given location from Traccar.
"""

import math
from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient


class FindNearestVehicle(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "find_nearest_vehicle"
		self.description = (
			"Identifies the closest vehicle to a given latitude/longitude location. "
			"Use this for 'Which vehicle is nearest to the airport?', "
			"'Find the closest truck to lat 13.08, lon 80.27'."
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"latitude":  {"type": "number", "description": "Target latitude"},
				"longitude": {"type": "number", "description": "Target longitude"},
				"limit":     {"type": "integer", "description": "Number of nearest vehicles to return (default: 3)"},
			},
			"required": ["latitude", "longitude"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		lat   = arguments.get("latitude")
		lon   = arguments.get("longitude")
		limit = arguments.get("limit", 3)

		def haversine(lat1, lon1, lat2, lon2):
			R = 6371
			dlat = math.radians(lat2 - lat1)
			dlon = math.radians(lon2 - lon1)
			a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
			return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

		try:
			client    = TraccarClient()
			positions = client.get_all_positions()
			devices   = {d.get("id"): d.get("name") for d in client.get_all_devices()}

			ranked = []
			for p in positions:
				p_lat = p.get("latitude")
				p_lon = p.get("longitude")
				if p_lat is None or p_lon is None:
					continue
				dist = haversine(lat, lon, p_lat, p_lon)
				ranked.append({
					"vehicle":    devices.get(p.get("deviceId"), f"Device {p.get('deviceId')}"),
					"distance_km": round(dist, 2),
					"latitude":   p_lat,
					"longitude":  p_lon,
					"speed_kmh":  round(p.get("speed", 0) * 1.852, 2),
					"device_time": p.get("deviceTime"),
				})

			ranked.sort(key=lambda x: x["distance_km"])

			return {
				"success":          True,
				"target_latitude":  lat,
				"target_longitude": lon,
				"nearest_vehicles": ranked[:limit],
			}
		except Exception as e:
			frappe.log_error(str(e), "FindNearestVehicle.execute")
			return {"success": False, "error": str(e)}


find_nearest_vehicle = FindNearestVehicle()