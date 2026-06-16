"""
Find geofences near the current vehicle location.
"""

import math
from typing import Any, Dict

import frappe
from frappe_assistant_core.core.base_tool import BaseTool
from frappe_assistant_core.plugins.telematics.traccar_client import TraccarClient, resolve_device_id


class GetNearbyGeofences(BaseTool):
	def __init__(self):
		super().__init__()
		self.name = "get_nearby_geofences"
		self.description = (
			"Finds geofences near the current vehicle location. "
			"Use this for 'What geofences are near vehicle X?', "
			"'Is TN01AB1234 close to any zones?'"
		)
		self.requires_permission = None
		self.inputSchema = {
			"type": "object",
			"properties": {
				"vehicle":        {"type": "string", "description": "Vehicle name in Frappe"},
				"radius_km":      {"type": "number", "description": "Search radius in km (default: 5)"},
			},
			"required": ["vehicle"],
		}

	def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
		vehicle   = arguments.get("vehicle")
		radius_km = arguments.get("radius_km", 5)

		def parse_circle_center(area):
			try:
				# CIRCLE (lat lon, radius)
				inner = area.replace("CIRCLE", "").strip().strip("()")
				coords, _ = inner.split(",")
				lat, lon = map(float, coords.strip().split())
				return lat, lon
			except Exception:
				return None, None

		def haversine(lat1, lon1, lat2, lon2):
			R = 6371
			dlat = math.radians(lat2 - lat1)
			dlon = math.radians(lon2 - lon1)
			a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
			return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

		try:
			device_id = resolve_device_id(vehicle)
			client    = TraccarClient()
			positions = client.get_positions(device_id=device_id)
			pos       = positions[0] if positions else {}
			v_lat, v_lon = pos.get("latitude"), pos.get("longitude")

			if not v_lat or not v_lon:
				return {"success": False, "vehicle": vehicle, "error": "No position available"}

			geofences = client.get_geofences()
			nearby    = []
			for g in geofences:
				g_lat, g_lon = parse_circle_center(g.get("area", ""))
				if g_lat is None:
					continue
				dist = haversine(v_lat, v_lon, g_lat, g_lon)
				if dist <= radius_km:
					nearby.append({"name": g.get("name"), "distance_km": round(dist, 2), "area": g.get("area")})

			nearby.sort(key=lambda x: x["distance_km"])
			return {"success": True, "vehicle": vehicle, "radius_km": radius_km, "nearby_geofences": nearby}
		except Exception as e:
			frappe.log_error(str(e), "GetNearbyGeofences.execute")
			return {"success": False, "vehicle": vehicle, "error": str(e)}


get_nearby_geofences = GetNearbyGeofences()