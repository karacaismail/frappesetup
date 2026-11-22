const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
	path.join(__dirname, "../press_tr/www/account-deletion.js"),
	"utf8",
);

function browserFixture() {
	const button = { disabled: false };
	const status = { textContent: "" };
	const restart = { hidden: true };
	let submit;
	let nextResponse;
	let calls = 0;
	const destinations = [];
	const requestUrls = [];
	const form = {
		addEventListener: (_event, handler) => { submit = handler; },
		action: "https://press.example.test/api/method/fixture.deletion",
		dataset: { confirm: "true", error: "Failure", success: "Success" },
		elements: { csrf_token: { value: "fixture" } },
		querySelector: () => button,
	};
	const elements = {
		"account-deletion": form,
		"account-deletion-status": status,
		"restart-account-deletion": restart,
	};
	vm.runInNewContext(script, {
		document: { getElementById: (id) => elements[id] },
		window: { location: { assign: (url) => destinations.push(url) } },
		URL,
		fetch: (url) => {
			calls += 1;
			requestUrls.push(url);
			return new Promise((resolve) => { nextResponse = resolve; });
		},
	});

	const event = { preventDefault() {} };
	return {
		button, status, restart, destinations, requestUrls,
		submit: () => submit(event),
		respond: (response) => nextResponse(response),
		calls: () => calls,
	};
}

test("only one deletion runs while the first response is pending", async () => {
	const { button, status, restart, submit, respond, calls } = browserFixture();
	const pending = submit();
	const duplicate = submit();
	assert.equal(calls(), 1);
	assert.equal(button.disabled, true);
	respond({ ok: false });
	await Promise.all([pending, duplicate]);
	assert.equal(restart.hidden, false);
	assert.equal(button.disabled, false);
	assert.equal(status.textContent, "Failure");

	const retry = submit();
	respond({ ok: true, json: async () => ({ message: { submitted: true } }) });
	await retry;
	assert.equal(calls(), 2);
	assert.equal(button.disabled, true);
	assert.equal(status.textContent, "Success");
});

test("uses the deletion action from the rendered form", async () => {
	const { submit, respond, requestUrls } = browserFixture();
	const pending = submit();
	respond({ ok: false });
	await pending;
	assert.deepEqual(requestUrls, ["https://press.example.test/api/method/fixture.deletion"]);
});

test("rejects unrecognized messages and untrusted destination types", async () => {
	for (const message of [
		{},
		{ submitted: "true" },
		{ url: 42 },
		{ url: "javascript:void(0)" },
		{ url: "/relative-path" },
		{ url: "https://keycloak.example.test/login", submitted: true },
	]) {
		const { button, status, restart, destinations, submit, respond } = browserFixture();
		const pending = submit();
		respond({ ok: true, json: async () => ({ message }) });
		await pending;
		assert.deepEqual(destinations, []);
		assert.equal(status.textContent, "Failure");
		assert.equal(restart.hidden, false);
		assert.equal(button.disabled, false);
	}
});

test("follows an absolute Keycloak HTTP or HTTPS destination", async () => {
	for (const url of ["https://keycloak.example.test/login", "http://keycloak.localhost/login"]) {
		const { destinations, submit, respond } = browserFixture();
		const pending = submit();
		respond({ ok: true, json: async () => ({ message: { url } }) });
		await pending;
		assert.deepEqual(destinations, [url]);
	}
});

test("the script accepts a page without a deletion form", () => {
	vm.runInNewContext(script, { document: { getElementById: () => null } });
});
