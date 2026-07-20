// assistant_core/page/aiko_dashboard/aiko_dashboard.js
//
// Thin Frappe page loader. Mounts the built React bundle
// (public/dist/aiko_dashboard/index.js) into this page's body.
// All actual UI/logic lives in public/js/aiko_dashboard_src/.

frappe.pages["aiko-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Aiko Dashboard",
		single_column: true,
	});

	const mountEl = $('<div id="aiko-dashboard-root"></div>').appendTo(page.body);

	frappe.require([
		"/assets/frappe_assistant_core/dist/aiko_dashboard/index.js",
	]).then(() => {
		if (window.AikoDashboard && window.AikoDashboard.mount) {
			window.AikoDashboard.mount(mountEl[0]);
		} else {
			mountEl.html(
				'<div style="padding:2rem;color:#888;">' +
				"Aiko Dashboard bundle not found — run the frontend build " +
				"(vite build in public/js/aiko_dashboard_src) first." +
				"</div>"
			);
		}
	});
};

frappe.pages["aiko-dashboard"].on_page_show = function (wrapper) {
	// no-op for now — React app owns its own state once mounted.
	// If you later add "reset dashboard" behavior on page re-entry,
	// hook it here via window.AikoDashboard.reset?.() (add that method
	// to main.jsx if needed).
};