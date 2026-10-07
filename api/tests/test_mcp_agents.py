import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
from tests.test_auth import PASSWORD, Client

from app.main import app


def _admin() -> Client:
    client = Client()
    created = client.post(
        "/api/v1/setup",
        {
            "token": "bootstrap-token-value",
            "email": "admin@example.com",
            "password": PASSWORD,
            "display_name": "Orpheus",
        },
    )
    if created.status_code != 200:
        signed = client.post(
            "/api/v1/auth/password/login",
            {"email": "admin@example.com", "password": PASSWORD},
        )
        assert signed.status_code == 200, signed.text
    return client


def test_agent_script_and_mcp_client() -> None:
    admin = _admin()
    hunt = admin.post(
        "/api/v1/hunts",
        {
            "name": "NYC · Couple",
            "slug": "nyc-agents",
            "kind": "rental",
            "schema": "nyc-rental-v1",
            "criteria": {"price_ceiling": 3000, "ri_price_ceiling": 4000, "price_ceiling_2br": 3200},
        },
    )
    assert hunt.status_code == 201, hunt.text
    issued = admin.post(f"/api/v1/hunts/{hunt.json()['id']}/pairing-codes", {})
    assert issued.status_code == 201, issued.text
    code = issued.json()["code"]
    assert code.startswith("DWL-")

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=0.3):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise AssertionError("api did not start")

    script = Path(__file__).resolve().parents[2] / "scripts" / "agent_example.py"
    env = os.environ.copy()
    env["DWELLINGS_BASE_URL"] = f"http://127.0.0.1:{port}"
    env["DWELLINGS_PAIR_CODE"] = code
    completed = subprocess.run(
        [sys.executable, str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    server.should_exit = True
    thread.join(timeout=5)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "still present" in completed.stdout
    assert "mcp posted" in completed.stdout


def test_members_can_list_agents() -> None:
    admin = _admin()
    hunt = admin.post(
        "/api/v1/hunts",
        {
            "name": "NYC · Agents",
            "slug": "nyc-agent-list",
            "kind": "rental",
            "schema": "nyc-rental-v1",
            "criteria": {"price_ceiling": 3000},
        },
    )
    assert hunt.status_code == 201, hunt.text
    hunt_id = hunt.json()["id"]
    empty = admin.get(f"/api/v1/hunts/{hunt_id}/agents")
    assert empty.status_code == 200, empty.text
    assert empty.json()["agents"] == []

    issued = admin.post(f"/api/v1/hunts/{hunt_id}/pairing-codes", {})
    assert issued.status_code == 201, issued.text
    paired = Client().post(
        "/api/v1/agents/pair",
        {"code": issued.json()["code"], "name": "hunt-nyc"},
    )
    assert paired.status_code == 201, paired.text
    assert "token" in paired.json()

    listed = admin.get(f"/api/v1/hunts/{hunt_id}/agents")
    assert listed.status_code == 200, listed.text
    agents = listed.json()["agents"]
    assert len(agents) == 1
    assert agents[0]["name"] == "hunt-nyc"
    assert agents[0]["posts"] == 0
    assert "token" not in agents[0]

    invited = admin.post(
        "/api/v1/auth/invites",
        {"role": "owner", "email": "outsider-agents@example.com"},
    )
    assert invited.status_code == 201, invited.text
    outsider = Client()
    accepted = outsider.post(
        "/api/v1/auth/invite/accept",
        {
            "token": invited.json()["token"],
            "email": "outsider-agents@example.com",
            "password": PASSWORD,
            "display_name": "Outsider",
        },
    )
    assert accepted.status_code == 200, accepted.text
    missing = outsider.get(f"/api/v1/hunts/{hunt_id}/agents")
    assert missing.status_code == 404, missing.text
