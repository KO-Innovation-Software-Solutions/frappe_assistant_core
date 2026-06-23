"""
Shared Traccar HTTP client for Fleet IoT telematics.
Reads credentials from Fleet IoT Settings doctype.
"""
import requests
import frappe
from frappe.utils import get_datetime, format_datetime, get_system_timezone
from frappe.utils.data import convert_utc_to_timezone


def to_local_time(utc_time_str, fmt="dd-MM-yyyy HH:mm:ss"):
	"""
	Convert a Traccar UTC timestamp string (e.g. '2024-06-23T08:30:00.000+0000')
	to the site's local timezone (Asia/Kolkata) as a formatted string.
	Returns None if input is falsy/unparseable.
	"""
	if not utc_time_str:
		return None
	try:
		dt_utc = get_datetime(utc_time_str)
		local_dt = convert_utc_to_timezone(dt_utc, get_system_timezone())
		return format_datetime(local_dt, fmt)
	except Exception:
		frappe.log_error(f"Time conversion failed for: {utc_time_str}", "to_local_time")
		return utc_time_str


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

		self.session.headers.update({"Accept": "application/json"})

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

	
	def create_or_update_geofence(self, name, latitude, longitude, radius=100):
		# Fetch geofences
		res = self.session.get(f"{self.base_url}/api/geofences", timeout=15)

		if res.status_code != 200:
			frappe.throw(f"Fetch geofences failed: {res.status_code} - {res.text}")

		geofences = res.json()

		# Check existing
		for geo in geofences:
			if geo.get("name") == name:
				return geo.get("id")

		# Create new
		payload = {
			"name": name,
			"area": f"CIRCLE ({latitude} {longitude}, {radius})"
		}

		res = self.session.post(
			f"{self.base_url}/api/geofences",
			json=payload,
			timeout=15
		)

		if res.status_code not in (200, 201):
			frappe.throw(f"Create geofence failed: {res.status_code} - {res.text}")

		return res.json().get("id")


	def get_all_devices(self):
		res = self.session.get(f"{self.base_url}/api/devices", timeout=15)
		if res.status_code != 200:
			frappe.throw(f"Devices fetch failed: {res.status_code}")
		return res.json()

	def get_all_positions(self):
		res = self.session.get(f"{self.base_url}/api/positions", timeout=30)
		if res.status_code != 200:
			frappe.throw(f"All positions fetch failed: {res.status_code}")
		return res.json()

	def get_all_summary(self, from_date, to_date):
		res = self.session.get(
			f"{self.base_url}/api/reports/summary",
			params={"from": from_date, "to": to_date},
			timeout=60,
		)
		if res.status_code != 200:
			return []
		return res.json()

	def reverse_geocode(self, lat, lng):
		try:
			settings = frappe.get_single("Fleet IoT Settings")
			api_key = "AIzaSyCekFmfkQ1yePDmE2otyma_ASuw-z_HGyo"
			if not api_key:
				return None
			url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}&key={api_key}"
			res = requests.get(url, timeout=10)
			data = res.json()
			if data.get("status") == "OK" and data.get("results"):
				return data["results"][0]["formatted_address"]
			return None
		except Exception:
			return None


def resolve_device_id(vehicle: str) -> int:
	vehicle_doc = frappe.get_doc("Vehicle", vehicle)

	if not vehicle_doc.telematics_id:
		frappe.throw(
			f"No telematics_id configured for vehicle: {vehicle}"
		)

	return int(vehicle_doc.telematics_id)