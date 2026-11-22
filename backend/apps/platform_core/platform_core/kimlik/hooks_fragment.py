# platform-core-kimlik: lines to add to hooks.py. The orchestrator adds them when merging.
on_social_login = "platform_core.kimlik.sign_in.on_social_login"
on_session_creation = ["platform_core.kimlik.sign_in.on_session_creation"]
before_login = ["platform_core.kimlik.login_policy.before_login"]
before_request = ["platform_core.kimlik.login_policy.before_request"]
auth_hooks = ["platform_core.kimlik.service_token.validate"]
