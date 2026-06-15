"""
Shared Traccar HTTP client for Fleet IoT telematics.
Reads credentials from Fleet IoT Settings doctype.
"""

import requests
import frappe


class TraccarClient:
	def __init__(self):
		settings = frappe.get_single("Fleet IoT Settings")

		self.username = settings.telematics_username
		self.password = settings.get_password("telematics_password")
		self.base_url = settings.telematics_base_url.rstrip("/")

		if not self.username or not self.password or not self.base_url:
			frappe.throw("Telematics credentials not configured in Fleet IoT Settings")

		self.session = requests.Session()

		login_res = self.session.post(
			f"{self.base_url}/api/session",
			data={"email": self.username, "password": self.password},
			timeout=15,
		)

		if login_res.status_code != 200:
			frappe.throw(f"Traccar login failed: {login_res.status_code} - {login_res.text}")

		self.session.headers.update({
			"Accept": "application/json",
		})

	@staticmethod
	def _int(val):
		try:
			return int(val)
		except (TypeError, ValueError):
			return val

	def get_positions(self, device_id, from_date=None, to_date=None):
		params = {"deviceId": self._int(device_id)}
		if from_date:
			params["from"] = from_date
		if to_date:
			params["to"] = to_date
		res = self.session.get(f"{self.base_url}/api/positions", params=params, timeout=30)
		if res.status_code != 200:
			frappe.throw(f"Positions fetch failed: {res.status_code} - {res.text}")
		return res.json()

	def get_trips(self, device_id, from_date, to_date):
		res = self.session.get(
			f"{self.base_url}/api/reports/trips",
			params={"deviceId": self._int(device_id), "from": from_date, "to": to_date},
			timeout=30,
		)
		if res.status_code != 200:
			frappe.log_error(f"Trips fetch failed: {res.status_code} - {res.text[:300]}", "TraccarClient.get_trips")
			return []
		return res.json()

	def get_stops(self, device_id, from_date, to_date):
		res = self.session.get(
			f"{self.base_url}/api/reports/stops",
			params={"deviceId": self._int(device_id), "from": from_date, "to": to_date},
			timeout=30,
		)
		if res.status_code != 200:
			frappe.log_error(f"Stops fetch failed: {res.status_code} - {res.text[:300]}", "TraccarClient.get_stops")
			return []
		return res.json()

	def get_route(self, device_id, from_date, to_date):
		try:
			res = self.session.get(
				f"{self.base_url}/api/reports/route",
				params={"deviceId": self._int(device_id), "from": from_date, "to": to_date},
				timeout=120,
			)
			if res.status_code != 200:
				frappe.log_error(f"Route fetch failed: {res.status_code} - {res.text[:500]}", "TraccarClient.get_route")
				return []
			data = res.json()
			if isinstance(data, list) and len(data) > 2000:
				step = len(data) // 2000
				data = data[::step]
			return data
		except Exception as e:
			frappe.log_error(f"Route fetch exception: {str(e)}", "TraccarClient.get_route")
			return []

	def get_events(self, device_id, from_date, to_date, types=None):
		params = [
			("deviceId", self._int(device_id)),
			("from", from_date),
			("to", to_date),
		]
		if types:
			if isinstance(types, list):
				for t in types:
					params.append(("type", t))
			else:
				params.append(("type", types))
		res = self.session.get(f"{self.base_url}/api/reports/events", params=params, timeout=30)
		if res.status_code != 200:
			frappe.log_error(f"Events fetch failed: {res.status_code} - {res.text[:500]}", "TraccarClient.get_events")
			return []
		return res.json()

	def get_summary(self, device_id, from_date, to_date):
		res = self.session.get(
			f"{self.base_url}/api/reports/summary",
			params={"deviceId": self._int(device_id), "from": from_date, "to": to_date},
			timeout=30,
		)
		if res.status_code != 200:
			frappe.throw(f"Summary fetch failed: {res.status_code} - {res.text}")
		return res.json()

	def get_geofences(self, device_id=None):
		all_geofences = []
		res = self.session.get(f"{self.base_url}/api/geofences", timeout=15)
		if res.status_code != 200:
			frappe.throw(f"Geofences fetch failed: {res.status_code} - {res.text}")
		all_geofences = res.json()

		if device_id:
			try:
				res2 = self.session.get(
					f"{self.base_url}/api/geofences",
					params={"deviceId": self._int(device_id)},
					timeout=15,
				)
				if res2.status_code == 200:
					existing_ids = {g["id"] for g in all_geofences}
					for g in res2.json():
						if g["id"] not in existing_ids:
							all_geofences.append(g)
			except Exception:
				pass

		return all_geofences


def resolve_device_id(vehicle: str) -> int:
    client = TraccarClient()
    vehicle_clean = vehicle.replace(" ", "").upper()
    res = client.session.get(f"{client.base_url}/api/devices", timeout=15)
    if res.status_code == 200:
        for d in res.json():
            if (d.get("name", "").replace(" ", "").upper() == vehicle_clean or
                d.get("uniqueId", "").replace(" ", "").upper() == vehicle_clean):
                return int(d["id"])
    frappe.throw(f"Could not resolve Traccar device ID for vehicle: {vehicle}")