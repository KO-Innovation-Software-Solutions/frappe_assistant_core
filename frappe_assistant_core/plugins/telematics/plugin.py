"""
Traccar Fleet IoT Plugin for Frappe Assistant Core.
Provides telematics tools: position, trips, stops, route, events, summary, geofences.
"""

import frappe
from frappe_assistant_core.plugins.base_plugin import BasePlugin


class TraccarPlugin(BasePlugin):
	"""
	Plugin that exposes Traccar telematics data to the AI assistant.
	Reads credentials from Fleet IoT Settings.
	"""

	def get_info(self):
		return {
			"name": "telematics",
			"display_name": "Fleet IoT Telematics (Traccar)",
			"description": (
				"Provides live and historical vehicle telematics via Traccar: "
				"GPS position, trips, stops, route replay, events, summary reports, and geofences."
			),
			"version": "1.0.0",
			"author": "Fleet IoT",
			"dependencies": ["requests"],
			"requires_restart": False,
		}

	def get_tools(self):
		return [
			"create_or_update_geofence",
			"find_nearest_vehicle",
			"get_active_alerts",
			"get_daily_movement_report",
			"get_device_status",
			"get_fleet_summary",
			"get_geofence_history",
			"get_geofences",
			"get_ignition_status",
			"get_motion_status",
			"get_nearby_geofences",
			"get_offline_vehicles",
			"get_overspeed_events",
			"get_speed_analysis",
			"get_top_idle_vehicles",
			"get_top_running_vehicles",
			"get_vehicle_activity_report",
			"get_vehicle_distance",
			"get_vehicle_events",
			"get_vehicle_idle_time",
			"get_vehicle_last_update",
			"get_vehicle_live_status",
			"get_vehicle_location_history",
			"get_vehicle_odometer",
			"get_vehicle_position",
			"get_vehicle_route",
			"get_vehicle_stops",
			"get_vehicle_summary",
			"get_vehicle_timeline",
			"get_vehicle_trip_statistics",
			"get_vehicle_trips",
			"get_vehicle_utilization",
		]

	def validate_environment(self):
		try:
			settings = frappe.get_single("Fleet IoT Settings")
			if not settings.telematics_base_url:
				return False, "Fleet IoT Settings: telematics_base_url is not configured"
			if not settings.telematics_username:
				return False, "Fleet IoT Settings: telematics_username is not configured"
			return True, None
		except Exception as e:
			return False, f"Fleet IoT Settings not found: {str(e)}"