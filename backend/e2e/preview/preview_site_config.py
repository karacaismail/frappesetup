"""Frappe configuration hook for the disposable tenant process."""

import os


def tenant_service_config():
    return {"keycloak_service_client_secret": os.environ["E2E_KEYCLOAK_SERVICE_CLIENT_SECRET"]}
