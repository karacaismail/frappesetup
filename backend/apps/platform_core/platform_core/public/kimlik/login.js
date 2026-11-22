// Tenant sign-in page of platform_core. Served as an asset, so the page needs no inline script (W-8).
// Messages come from escaped data attributes that the server translates.
(function () {
	"use strict";

	// Visible keyboard focus starts off and is switched on only by Tab or Shift+Tab (AGENT.md focus rule).
	var root = document.documentElement;
	document.addEventListener("keydown", function (event) {
		if (event.key === "Tab") { root.setAttribute("data-kbd", ""); }
	}, true);
	["pointerdown", "touchstart"].forEach(function (name) {
		document.addEventListener(name, function () { root.removeAttribute("data-kbd"); }, true);
	});

	function setUpPasswordForm() {
		var form = document.querySelector("form[data-login-endpoint]");
		if (!form) { return; }
		var error = document.getElementById("login-error");
		var button = form.querySelector("button[type=submit]");
		var pending = false;

		form.addEventListener("submit", function (event) {
			event.preventDefault();
			// E-9: one request at a time. A second click while the first runs sends nothing.
			if (pending) { return; }
			pending = true;
			button.disabled = true;
			error.hidden = true;
			fetch(form.dataset.loginEndpoint, {
				method: "POST",
				headers: { "Accept": "application/json", "X-Requested-With": "XMLHttpRequest" },
				body: new URLSearchParams(new FormData(form)),
				credentials: "same-origin"
			}).then(function (response) {
				if (response.ok) { window.location.assign(form.dataset.afterLogin); return; }
				error.textContent = form.dataset.failedMessage;
				error.hidden = false;
			}).catch(function () {
				error.textContent = form.dataset.offlineMessage;
				error.hidden = false;
			}).finally(function () {
				pending = false;
				button.disabled = false;
			});
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", setUpPasswordForm);
	} else {
		setUpPasswordForm();
	}
})();
