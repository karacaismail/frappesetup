"""Create or update the local review accounts in the stack's Keycloak.

Runs inside the stack network with `python -I`. Input on stdin: keycloak_url, admin_username,
admin_password, password, relaxed_length, restore_policy and the accounts of
backend/e2e/review-accounts.json.
Output on stdout: the Keycloak subject of every platform realm account. It prints no password.

The platform realm asks for 12 characters, the production rule. The shared review password is
shorter, so the script lowers the length rule of the running local Keycloak while it sets the
passwords, and afterwards writes restore_policy, also after an error. restore_policy is the rule
of platform-realm.json, never the rule read from the running Keycloak: a run killed before the
restore leaves the relaxed rule behind, and the next run must not take that rule for the realm's. The password history
rule is dropped for the same moment, so a repeated run may set the same password again.
The realm file is never changed. Only a plain-HTTP local Keycloak is accepted.
"""

import http.client
import json
import re
import sys
import urllib.parse

PLATFORM = "platform"
MASTER = "master"
LOCAL_HOST = re.compile(r"(?:localhost|127\.0\.0\.1|[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.localhost)")


def require_local(url):
    parts = urllib.parse.urlsplit(url)
    if (
        parts.scheme != "http"
        or not LOCAL_HOST.fullmatch(parts.hostname or "")
        or parts.path not in ("", "/")
        or parts.query
        or parts.username
    ):
        raise SystemExit("Only a local development Keycloak is accepted.")


def relaxed_policy(policy, length):
    """The realm rule with a shorter length and without the history rule. Other rules stay."""
    rules = [rule.strip() for rule in (policy or "").split(" and ") if rule.strip()]
    rules = [rule for rule in rules if not rule.startswith("passwordHistory(")]
    rules = [f"length({length})" if rule.startswith("length(") else rule for rule in rules]
    return " and ".join(rules)


def require_production_policy(policy):
    """The rule to restore must keep the production minimum of 12 characters."""
    found = re.search(r"(?:^| and )length\((\d+)\)(?: and |$)", policy) if isinstance(policy, str) else None
    if not found or int(found.group(1)) < 12:
        raise SystemExit("The rule to restore must ask for at least 12 characters.")


def http_caller(base_url, username, password):
    parts = urllib.parse.urlsplit(base_url)
    host, port = parts.hostname, parts.port or 80

    def request(method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(host, port, timeout=20)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.getheader("Location"), response.read()
        finally:
            connection.close()

    status, _, raw = request(
        "POST",
        f"/realms/{MASTER}/protocol/openid-connect/token",
        urllib.parse.urlencode(
            {"grant_type": "password", "client_id": "admin-cli", "username": username, "password": password}
        ),
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    if status != 200:
        raise SystemExit(f"Keycloak refused the admin sign-in (HTTP {status}).")
    token = json.loads(raw).get("access_token")
    if not isinstance(token, str) or not token:
        raise SystemExit("Keycloak returned no admin access token.")

    def call(method, path, data=None):
        body = None if data is None else json.dumps(data)
        status, location, raw = request(
            method, path, body, {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
        )
        return status, location, (json.loads(raw) if raw else None)

    return call


def expect(call, expected, what, method, path, data=None):
    status, location, body = call(method, path, data)
    if status not in expected:
        raise SystemExit(f"Keycloak did not {what} (HTTP {status}).")
    return location, body


def ensure_user(call, realm, account, password):
    """Create the user, or bring an existing one back to the reviewed state. Returns its ID."""
    base = f"/admin/realms/{realm}"
    username = account["username"]
    fields = {
        "username": username,
        "enabled": True,
        "firstName": account["first_name"],
        "lastName": account["last_name"],
        "requiredActions": [],
    }
    if "@" in username:
        fields.update({"email": username, "emailVerified": True})
    query = urllib.parse.urlencode({"exact": "true", "username": username}, quote_via=urllib.parse.quote)
    _, found = expect(call, {200}, f"search {username}", "GET", f"{base}/users?{query}")
    found = [user for user in found or [] if user.get("username") == username]
    if found:
        user_id = found[0]["id"]
        expect(call, {204}, f"update {username}", "PUT", f"{base}/users/{user_id}", fields)
        expect(
            call, {204}, f"set the password of {username}", "PUT", f"{base}/users/{user_id}/reset-password",
            {"type": "password", "value": password, "temporary": False},
        )
        return user_id
    location, _ = expect(
        call, {201}, f"create {username}", "POST", f"{base}/users",
        {**fields, "credentials": [{"type": "password", "value": password, "temporary": False}]},
    )
    if not location:
        raise SystemExit(f"Keycloak did not name the created user {username}.")
    return location.rsplit("/", 1)[-1]


def apply(payload, caller_factory=http_caller):
    require_local(payload["keycloak_url"])
    length = payload["relaxed_length"]
    if type(length) is not int or not 8 <= length < 12:
        raise SystemExit("The relaxed length must be from 8 to 11.")
    policy = payload.get("restore_policy")
    require_production_policy(policy)
    call = caller_factory(payload["keycloak_url"], payload["admin_username"], payload["admin_password"])
    password = payload["password"]
    accounts = payload["accounts"]
    realm_path = f"/admin/realms/{PLATFORM}"
    subjects = {}
    expect(call, {204}, "relax the local password rule", "PUT", realm_path,
           {"passwordPolicy": relaxed_policy(policy, length)})
    try:
        for account in accounts:
            if account["realm"] == PLATFORM:
                subjects[account["username"]] = ensure_user(call, PLATFORM, account, password)
    finally:
        expect(call, {204}, "restore the password rule", "PUT", realm_path, {"passwordPolicy": policy})
    for account in accounts:
        if account["realm"] != MASTER:
            continue
        user_id = ensure_user(call, MASTER, account, password)
        roles = []
        for name in account.get("master_roles", []):
            _, role = expect(call, {200}, f"read the {name} role", "GET", f"/admin/realms/{MASTER}/roles/{name}")
            roles.append(role)
        if roles:
            expect(call, {204}, "grant the master roles", "POST",
                   f"/admin/realms/{MASTER}/users/{user_id}/role-mappings/realm", roles)
    return {"subjects": subjects}


def main():
    print(json.dumps(apply(json.load(sys.stdin))))


if __name__ == "__main__":
    main()
