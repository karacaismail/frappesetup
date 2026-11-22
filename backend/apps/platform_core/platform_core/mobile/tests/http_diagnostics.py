"""Keep HTTP test diagnostics limited to public mobile error identifiers."""

PUBLIC_MOBILE_CODES = frozenset(
	{
		"IdentityNotFound",
		"account_unavailable",
		"body_too_large",
		"cleanup_forbidden",
		"command_disabled",
		"cursor_key_unavailable",
		"installation_limit",
		"installation_unavailable",
		"invalid_batch_size",
		"invalid_client_version",
		"invalid_command",
		"invalid_cursor",
		"invalid_fields",
		"invalid_json",
		"invalid_mobile_route",
		"invalid_mobile_settings",
		"invalid_operation",
		"invalid_page_size",
		"invalid_request",
		"invalid_retention_setting",
		"invalid_uuid",
		"json_required",
		"mixed_authentication",
		"mobile_busy",
		"mobile_schema_unavailable",
		"mobile_sequence_exhausted",
		"mobile_session_revoked",
		"mobile_token_required",
		"mobile_token_revoked",
		"operation_conflict",
		"pwa_request_forbidden",
		"pwa_session_required",
		"rate_limit",
		"reauthentication_required",
		"record_not_found",
		"redirect_rejected",
		"service_token_required",
		"unexpected_version",
		"unknown_command",
		"unsupported_contract_version",
		"version_conflict",
		"version_required",
	}
)


def safe_http_error_code(payload):
	code = payload.get("code") if isinstance(payload, dict) else None
	return code if isinstance(code, str) and code in PUBLIC_MOBILE_CODES else None


def http_diagnostic(status, payload):
	code = safe_http_error_code(payload)
	return f"HTTP {status} ({code})" if code else f"HTTP {status}"
