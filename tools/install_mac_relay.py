#!/usr/bin/env python3
"""Install login-time gateway and reconnecting SSH tunnel for a private WireGuard relay."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="Public IP or hostname of the relay")
    parser.add_argument("--key", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    home = Path.home()
    agents = home / "Library/LaunchAgents"
    logs = home / "Library/Logs/agent-phone"
    agents.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    common = {
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 15,
        "ProcessType": "Background",
    }
    jobs = {
        "local.agent-phone.gateway": {
            "ProgramArguments": ["/usr/bin/python3", str(root / "server.py")],
            "WorkingDirectory": str(root),
            "EnvironmentVariables": {
                "AGENT_PHONE_HOST": "127.0.0.1",
                "AGENT_PHONE_PORT": "5173",
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
                "PYTHONUNBUFFERED": "1",
            },
        },
        "local.agent-phone.tunnel": {
            "ProgramArguments": [
                "/usr/bin/ssh", "-F", "/dev/null", "-NT",
                "-i", str(args.key.expanduser().resolve()),
                "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=yes",
                "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=15",
                "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
                "-R", "10.77.73.1:5173:127.0.0.1:5173",
                "agent-phone-tunnel@" + args.host,
            ],
        },
    }
    domain = f"gui/{os.getuid()}"
    for label, settings in jobs.items():
        path = agents / (label + ".plist")
        job = {**common, **settings, "Label": label,
               "StandardOutPath": str(logs / (label + ".out.log")),
               "StandardErrorPath": str(logs / (label + ".err.log"))}
        with path.open("wb") as stream:
            plistlib.dump(job, stream)
        path.chmod(0o600)
        subprocess.run(["launchctl", "bootout", domain + "/" + label],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
        print("Installed:", label)


if __name__ == "__main__":
    main()
