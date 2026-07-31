// assistant_core/doctype/aiko_dashboard_artifact/aiko_dashboard_artifact_list.js
//
// Overrides the default list-row click behavior: instead of opening the
// standard Frappe form for a Aiko Dashboard Artifact, route to the
// custom artifact viewer page (aiko-dashboard-artifact-view/<name>).

frappe.listview_settings["Aiko Dashboard Artifact"] = {
	get_indicator: () => null,
	onload(listview) {
		listview.$result.on("click", ".list-row-col.ellipsis a", function (e) {
			const name = $(this).closest(".list-row-container").attr("data-name");
			if (name) {
				e.preventDefault();
				frappe.set_route("aiko-dashboard-artifact-view", name);
			}
		});
	},
};