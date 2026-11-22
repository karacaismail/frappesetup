"""Hooks for a disposable mobile sync test site."""

app_name = "mobile_test_app"
app_title = "Mobile Test App"
app_publisher = "Platform"
app_description = "Isolated fixtures for mobile sync HTTP tests"
app_email = "noreply@example.test"
app_license = "MIT"
required_apps = ["platform_core"]
auth_hooks = ["mobile_test_app.fixture.authenticate"]
after_install = ["mobile_test_app.fixture.setup"]
override_whitelisted_methods = {
    "platform_core.api.mobile.v1_push": "mobile_test_app.fixture.fixture_push",
    "platform_core.api.mobile.v1_pull": "mobile_test_app.fixture.fixture_pull",
}
