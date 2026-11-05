frappe.pages["add-branch"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Add Branch"),
		single_column: true,
	});

	const form = new frappe.ui.FieldGroup({
		parent: page.body,
		fields: [
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				reqd: 1,
				default: frappe.defaults.get_user_default("Company"),
			},
			{
				fieldname: "branch_name",
				label: __("Branch Name"),
				fieldtype: "Data",
				reqd: 1,
			},
			{ fieldname: "result", fieldtype: "HTML" },
		],
	});
	form.make();

	page.set_primary_action(__("Create Branch"), () => {
		const values = form.get_values();
		if (!values) return;
		frappe.call({
			method: "mizan_retail.branches.create_branch",
			args: { company: values.company, branch_name: values.branch_name },
			freeze: true,
			freeze_message: __("Creating branch..."),
			callback: (r) => {
				if (!r.message) return;
				const { warehouse, pos_profile } = r.message;
				form.get_field("result").$wrapper.html(
					`<div class="alert alert-success branch-created">
						${__("Branch created")}:
						<a href="/app/warehouse/${encodeURIComponent(warehouse)}">${frappe.utils.escape_html(warehouse)}</a>,
						<a href="/app/pos-profile/${encodeURIComponent(pos_profile)}">${frappe.utils.escape_html(pos_profile)}</a>
					</div>`
				);
				form.set_value("branch_name", "");
				frappe.show_alert({ message: __("Branch created"), indicator: "green" });
			},
		});
	});
};
