frappe.pages["aiko-dashboard-artifact-view"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Dashboard Artifact",
		single_column: true,
	});

	const artifactName = frappe.get_route()[1] || null;

	const mountEl = $(
		'<div id="aiko-dashboard-artifact-root" style="height: calc(100vh - 140px);"></div>'
	).appendTo(page.body);

	frappe.require([
		"/assets/frappe_assistant_core/dist/aiko_dashboard_artifact_view/index.js",
	]).then(() => {
		try {
			if (window.AikoDashboardArtifact && window.AikoDashboardArtifact.mount) {
				window.AikoDashboardArtifact.mount(mountEl[0], artifactName);
			} else {
				mountEl.html(
					'<div style="padding:2rem;color:#888;">Bundle not found — run vite build.</div>'
				);
			}
		} catch (e) {
			mountEl.html(
				'<div style="padding:2rem;color:#c00;">Error mounting dashboard artifact: ' + (e.message || e) + '</div>'
			);
		}
	}).catch(function () {
		mountEl.html(
			'<div style="padding:2rem;color:#c00;">Failed to load dashboard artifact bundle. Check that the build exists at the expected path.</div>'
		);
	});
};
