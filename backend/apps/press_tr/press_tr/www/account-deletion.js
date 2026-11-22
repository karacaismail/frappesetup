const form = document.getElementById("account-deletion");

form.addEventListener("submit", async (event) => {
	event.preventDefault();
	const button = form.querySelector("button");
	const status = document.getElementById("account-deletion-status");
	const restart = document.getElementById("restart-account-deletion");
	button.disabled = true;
	status.textContent = "";
	restart.hidden = true;

	try {
		const response = await fetch("/api/method/press_tr.api.account.request_deletion", {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": form.elements.csrf_token.value,
			},
			body: JSON.stringify({ confirm: form.dataset.confirm === "true" }),
		});
		if (!response.ok) {
			throw new Error();
		}

		const { message } = await response.json();
		if (message.url) {
			window.location.assign(message.url);
			return;
		}
		status.textContent = form.dataset.success;
	} catch {
		status.textContent = form.dataset.error;
		restart.hidden = false;
		button.disabled = false;
	}
});
