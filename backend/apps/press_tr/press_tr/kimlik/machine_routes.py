from functools import lru_cache
from importlib import import_module

# This inventory is tied to the tested Press tag. New routes must be audited.
MACHINE_METHODS = (
	"press.press.doctype.stripe_webhook_log.stripe_webhook_log.stripe_webhook_handler",
	"press.api.github.hook",
	"press.api.monitoring.targets",
	"press.api.monitoring.alert",
	"press.api.email.send_mime_mail",
	"press.api.site_backup.create_snapshot",
	"press.saas.api.auth.is_access_token_valid",
	"press.saas.api.auth.generate_access_token",
	"press.saas.api.billing.country_list",
	"press.saas.api.billing.get_information",
	"press.saas.api.billing.update_information",
	"press.saas.api.billing.validate_gst",
	"press.saas.api.billing.change_payment_mode",
	"press.saas.api.billing.get_publishable_key_and_setup_intent",
	"press.saas.api.billing.setup_intent_success",
	"press.saas.api.billing.create_payment_intent_for_micro_debit",
	"press.saas.api.billing.create_payment_intent_for_buying_credits",
	"press.saas.api.billing.create_razorpay_order",
	"press.saas.api.billing.handle_razorpay_payment_failed",
	"press.saas.api.billing.get_invoices",
	"press.saas.api.billing.upcoming_invoice",
	"press.saas.api.billing.get_unpaid_invoices",
	"press.saas.api.billing.total_unpaid_amount",
	"press.saas.api.billing.get_invoice",
	"press.saas.api.billing.download_invoice",
	"press.saas.api.billing.get_stripe_payment_url_for_invoice",
	"press.saas.api.billing.get_payment_methods",
	"press.saas.api.billing.set_as_default",
	"press.saas.api.billing.remove_payment_method",
	"press.saas.api.domain.get_domains",
	"press.saas.api.domain.check_dns",
	"press.saas.api.domain.add_domain",
	"press.saas.api.domain.remove_domain",
	"press.saas.api.domain.retry_add_domain",
	"press.saas.api.domain.set_host_name",
	"press.saas.api.domain.set_redirect",
	"press.saas.api.domain.unset_redirect",
	"press.saas.api.domain.get_inbound_ip",
	"press.saas.api.site.info",
	"press.saas.api.site.change_plan",
	"press.saas.api.site.get_plans",
	"press.saas.api.site.get_first_support_plan",
	"press.saas.api.team.info",
)

MONITORING_ALERT = "press.api.monitoring.alert"


@lru_cache(maxsize=1)
def machine_targets():
	targets = {}
	for name in MACHINE_METHODS:
		module, function = name.rsplit(".", 1)
		targets[getattr(import_module(module), function)] = name
	return targets
