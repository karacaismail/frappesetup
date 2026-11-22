import os
import subprocess


def start_worker():
    local_password = os.environ["FIXTURE_PASSWORD"]
    args = ["fixture", "--password", local_password]
    # ruleid: subprocess-secret-argument
    subprocess.run(args, check=True)
    # ruleid: subprocess-secret-argument
    subprocess.Popen(["fixture", f"--token={os.getenv('FIXTURE_TOKEN')}"])
    # ruleid: subprocess-secret-argument
    subprocess.check_output(["fixture", "--password", local_password])
    # ok: subprocess-secret-argument
    subprocess.run(["fixture", "--read-config"], env={"FIXTURE_PASSWORD": local_password}, check=True)
    # ok: subprocess-secret-argument
    subprocess.run(["fixture", "--password-stdin"], input=local_password, text=True, check=True)
    # ok: subprocess-secret-argument
    subprocess.run(["git", "status", "--short"], check=True)


def extend_arguments(token):
    args = ["fixture", "--token"]
    args.append(token)
    # ruleid: subprocess-secret-argument
    subprocess.run(args, check=True)
