#!/usr/bin/env python3
"""Validate indexing, ingress URL scheme, persisted workflow state and stable system keys."""

import json
import subprocess
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:18080"


def request(path, *, submit=False, headers=None):
    req = Request(BASE + path, data=b"{}" if submit else None, headers=headers or {})
    with urlopen(req, timeout=10) as response:
        body = response.read()
        return response.status, response.headers, body


def poll(check, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(2)
    raise RuntimeError("Container smoke test timed out")


def main():
    poll(lambda: request("/api/healthz")[0] == 200, timeout=300)
    status, headers, raw = request("/api/_aks_smoke", submit=True, headers={
        "Host": "aimie-service.test.example.invalid",
        "X-Forwarded-Host": "aimie-service.test.example.invalid",
        "X-Forwarded-Proto": "https",
    })
    assert status == 202
    payload = json.loads(raw)
    location = urlsplit(payload["statusQueryGetUri"])
    assert location.scheme == "https", "TLS ingress must return HTTPS polling URLs"
    assert location.netloc == "aimie-service.test.example.invalid"
    assert location.path.startswith("/runtime/webhooks/durabletask/instances/")
    assert headers["Location"] == payload["statusQueryGetUri"]
    path = location.path + "?" + location.query

    def state():
        result = json.loads(request(path)[2])
        if result["runtimeStatus"] == "Failed":
            raise RuntimeError("Synthetic Durable workflow failed")
        return result

    poll(lambda: state().get("customStatus") == "waiting-for-restart")
    # Replace the container, including its writable layer, as a pod replacement would.
    # Reusing the same container could hide accidental local-only host key persistence.
    inspected = json.loads(subprocess.check_output(["docker", "inspect", "aimie-smoke"]))[0]
    replacement = ["docker", "run", "-d", "--name", "aimie-smoke", "--network", "aimie-smoke",
                   "-p", "127.0.0.1:18080:80"]
    for mount in inspected["Mounts"]:
        replacement += ["--mount", f"type=bind,source={mount['Source']},target={mount['Destination']},readonly"]
    for entry in inspected["Config"]["Env"]:
        replacement += ["--env", entry]
    replacement.append(inspected["Config"]["Image"])
    subprocess.run(["docker", "kill", "aimie-smoke"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["docker", "rm", "aimie-smoke"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(replacement, check=True, stdout=subprocess.DEVNULL)
    poll(lambda: request("/api/healthz")[0] == 200)
    result = poll(lambda: (value if (value := state())["runtimeStatus"] == "Completed" else None))
    assert result["output"] == "persisted activity result"
    # Internal callers must receive an internal HTTP URL, not the public ingress hostname.
    _, _, raw = request("/api/_aks_smoke", submit=True)
    assert json.loads(raw)["statusQueryGetUri"].startswith(BASE + "/runtime/webhooks/durabletask/")
    print("Functions indexed; ingress/internal URLs and Durable restart recovery verified")


if __name__ == "__main__":
    main()
