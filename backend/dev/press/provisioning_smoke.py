"""Queue and verify the offline Press provisioning smoke test."""

import sys
from collections import Counter
from ipaddress import IPv4Address
from uuid import uuid4

import frappe
from frappe.utils.password import set_encrypted_password

DOMAIN = "provisioning-smoke.invalid"
CLUSTER = "provisioning-smoke"


def enqueue(hostname, target_ip):
    server_name = f"{hostname}.{DOMAIN}"
    ip = IPv4Address(target_ip)
    if not ip.is_private or ip.is_loopback or ip.is_link_local:
        raise SystemExit("Expected the disposable target's private Compose address.")
    ip = str(ip)
    for doctype, name, fields in (
        ("Cluster", CLUSTER, {}),
        ("Root Domain", DOMAIN, {"default_cluster": CLUSTER}),
        ("TLS Certificate", DOMAIN, {"domain": DOMAIN, "wildcard": 1}),
        (
            "Server",
            server_name,
            {
                "hostname": hostname,
                "domain": DOMAIN,
                "cluster": CLUSTER,
                "provider": "Generic",
                "is_standalone": 1,
                "is_self_hosted": 1,
                "ip": ip,
                "private_ip": ip,
            },
        ),
    ):
        if not frappe.db.exists(doctype, name):
            # Avoid external provisioning hooks while creating disposable fixtures.
            frappe.get_doc(dict(doctype=doctype, name=name, **fields)).db_insert()

    server = frappe.get_doc("Server", server_name)
    if (server.ip, server.private_ip, server.is_self_hosted, server.is_standalone) != (ip, ip, 1, 1):
        raise SystemExit("The existing server differs from the disposable fixture.")
    frappe.db.set_value("Server", server_name, "agent_password", "********")
    set_encrypted_password("Server", server_name, uuid4().hex, "agent_password")
    set_encrypted_password("Cluster", CLUSTER, uuid4().hex, "monitoring_password")
    server.reload().setup_server()
    frappe.db.commit()


def verify(hostname):
    server_name = f"{hostname}.{DOMAIN}"
    plays = frappe.get_all(
        "Ansible Play",
        filters={"server": server_name},
        fields=["name", "status", "playbook", "ok", "failures", "unreachable"],
        order_by="creation desc",
        limit=1,
    )
    if not plays:
        raise SystemExit("Press did not create an Ansible Play record.")
    play = plays[0]
    tasks = frappe.get_all(
        "Ansible Task",
        filters={"play": play.name},
        fields=["role", "task", "status", "result", "exception"],
    )
    counts = Counter(task.status for task in tasks)
    server_status = frappe.db.get_value("Server", server_name, "status")
    print(f"Play {play.name}: {play.playbook}, {play.status}. Server: {server_status}.")
    print(f"Ansible recap: ok={play.ok}, failed={play.failures}, unreachable={play.unreachable}.")
    print(f"Task statuses: {dict(counts)}")
    for task in tasks:
        if task.status != "Pending":
            print(f"{task.role} / {task.task}: {task.status}; result saved={bool(task.result)}")
    apt_failures = [
        task
        for task in tasks
        if task.role == "essentials"
        and task.task.endswith("Update APT Cache")
        and task.status == "Failure"
        and task.result
        and "127.0.0.1:9" in (task.exception or "")
    ]
    outcome = (play.playbook, play.status, play.failures, play.unreachable, server_status)
    expected = ("self_hosted.yml", "Failure", 1, 0, "Broken")
    if outcome != expected or not apt_failures or not play.ok:
        raise SystemExit("Expected Press to record the offline APT failure over SSH.")


def main():
    frappe.init("press.localhost")
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        if "press_tr" not in frappe.get_installed_apps():
            raise SystemExit("Install press_tr before running the provisioning smoke test.")
        if sys.argv[1] == "enqueue":
            enqueue(sys.argv[2], sys.argv[3])
        else:
            verify(sys.argv[2])
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
