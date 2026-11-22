const form = document.getElementById("account-deletion");

form?.addEventListener("submit", async (event) => {
	event.preventDefault();
	const button = form.querySelector("button");
	if (button.disabled) {
		return;
	}
	const status = document.getElementById("account-deletion-status");
	const restart = document.getElementById("restart-account-deletion");
	button.disabled = true;
	status.textContent = "";
	restart.hidden = true;

	try {
		const response = await fetch(form.action, {
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
		if (typeof message?.url === "string" && message.submitted === undefined && message.pending === undefined) {
			const destination = new URL(message.url);
			if (destination.protocol !== "https:" && destination.protocol !== "http:") {
				throw new Error();
			}
			window.location.assign(destination.href);
			return;
		}
		if (message?.pending === true && message.url === undefined && message.submitted === undefined) {
			status.textContent = form.dataset.pending;
			restart.textContent = form.dataset.refresh;
			restart.hidden = false;
			return;
		}
		if (message?.submitted !== true || message.url !== undefined || message.pending !== undefined) {
			throw new Error();
		}
		status.textContent = form.dataset.success;
	} catch {
		status.textContent = form.dataset.error;
		restart.hidden = false;
		button.disabled = false;
	}
});
