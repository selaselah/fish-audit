"""Manage this checkout's macOS user LaunchAgent."""

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LABEL = "local.fish-audit.server"
DOMAIN = f"gui/{os.getuid()}"
TARGET = f"{DOMAIN}/{LABEL}"
PLIST = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")


def launch(*arguments, check=True, quiet=False):
    return subprocess.run(["launchctl", *arguments], check=check,
                          stdout=subprocess.DEVNULL if quiet else None,
                          stderr=subprocess.DEVNULL if quiet else None)


def install():
    python = ROOT / ".venv" / "bin" / "python"
    if not python.is_file():
        raise SystemExit("请先在 server/.venv 安装 Python 环境。")
    if PLIST.is_file():
        existing = plistlib.loads(PLIST.read_bytes())
        if existing.get("WorkingDirectory") != str(ROOT):
            raise SystemExit("同名服务来自其他目录。")
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True, mode=0o700)
    env = {"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin", "PYTHONUNBUFFERED": "1"}
    office = os.getenv("SOFFICE_BIN") or shutil.which("soffice")
    if office:
        env["SOFFICE_BIN"] = office
    spec = {"Label": LABEL, "ProgramArguments": [str(python), str(ROOT / "main.py")],
            "WorkingDirectory": str(ROOT), "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 5,
            "EnvironmentVariables": env, "StandardOutPath": str(runtime / "service.log"),
            "StandardErrorPath": str(runtime / "service-error.log"), "Umask": 0o077}
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    tmp = PLIST.with_suffix(".tmp")
    tmp.write_bytes(plistlib.dumps(spec))
    tmp.chmod(0o600)
    tmp.replace(PLIST)
    for name in ("service.log", "service-error.log"):
        logfile = runtime / name
        logfile.touch(mode=0o600, exist_ok=True)
        logfile.chmod(0o600)
    if launch("print", TARGET, check=False, quiet=True).returncode == 0:
        launch("bootout", TARGET)
    for attempt in range(15):
        if launch("bootstrap", DOMAIN, str(PLIST), check=False, quiet=True).returncode == 0:
            break
        if attempt == 14:
            launch("bootstrap", DOMAIN, str(PLIST))
        time.sleep(0.3)
    print("已安装当前用户的 Fish Audit 本机服务。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["install", "status", "restart", "stop"])
    command = parser.parse_args().command
    if sys.platform != "darwin":
        raise SystemExit("该脚本适用于 macOS 用户登录会话。")
    if command == "install":
        install()
    elif command == "restart":
        launch("kickstart", "-k", TARGET)
    elif command == "stop":
        launch("bootout", TARGET)
    else:
        launch("print", TARGET)
