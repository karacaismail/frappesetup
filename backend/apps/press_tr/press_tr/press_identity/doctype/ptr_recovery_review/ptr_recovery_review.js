// AJA-420: after approval, a reviewer removes the old keys of the account owner.
// The server checks the permission, the account owner and the review state again.
frappe.ui.form.on("PTR Recovery Review", {
	refresh(frm) {
		if (frm.is_new() || !["Approved", "Removal Failed"].includes(frm.doc.status)) {
			return;
		}
		frm.add_custom_button(__("Remove Old Keys", null, "PTR Recovery Review"), () => {
			frappe.confirm(
				__(
					"Remove every passkey and security key that was set up before the approval? The user's sessions end too.",
					null,
					"PTR Recovery Review"
				),
				() => {
					frappe
						.call({
							method: "press_tr.api.account.remove_recovered_keys",
							args: { review: frm.doc.name },
							freeze: true,
						})
						.then(() => frm.reload_doc());
				}
			);
		});
	},
});
