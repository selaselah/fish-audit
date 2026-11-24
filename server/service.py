"""Manage this checkout's macOS user LaunchAgent."""

import argparse
import http.client
import ipaddress
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
LABEL = "local.fish-audit.server"
DOMAIN = f"gui/{os.getuid()}"
TARGET = f"{DOMAIN}/{LABEL}"
PLIST = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")


def launch(*arguments, check=True, quiet=False):
    return subprocess.run(["launchctl", *arguments], check=check,
                          stdout=subprocess.DEVNULL if quiet else None,
                          stderr=subprocess.DEVNULL if quiet else None)


class FrontendAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        value = attrs.get("src") if tag=="script" else None
        if tag=="link" and "stylesheet" in attrs.get("rel","").split():
            value = attrs.get("href")
        if value:
            target = urlsplit(value)
            if not target.netloc and not target.scheme and ".." not in target.path.split("/"):
                self.paths.append("/"+target.path.lstrip("/"))


def frontend_files(folder):
    index = (folder/"index.html").read_bytes()
    parser = FrontendAssets()
    parser.feed(index.decode())
    return {"/":index, **{path:(folder/path.lstrip("/")).read_bytes() for path in parser.paths}}


def agent_pid():
    result = subprocess.run(["launchctl","print",TARGET],capture_output=True,text=True,timeout=2)
    match = re.search(r"^\s*pid = (\d+)\s*$",result.stdout,re.M) if result.returncode==0 else None
    return int(match[1]) if match else None


def listen_addresses(pid):
    result = subprocess.run(["/usr/sbin/lsof","-nP","-a","-p",str(pid),"-iTCP","-sTCP:LISTEN","-Fnt"],
                            capture_output=True,text=True,timeout=2)
    addresses = []
    wildcard = "127.0.0.1"
    for line in result.stdout.splitlines():
        if line.startswith("t"):
            wildcard = "::1" if line=="tIPv6" else "127.0.0.1"
        if not line.startswith("n"):
            continue
        host,separator,port = line[1:].rpartition(":")
        if separator and port.isdecimal():
            addr = ipaddress.ip_address(wildcard if host=="*" else host.strip("[]"))
            if addr.is_unspecified:
                addr = ipaddress.ip_address("::1" if addr.version==6 else "127.0.0.1")
            addresses.append((str(addr),int(port)))
    return addresses


def trusted_host():
    # Connect to the process's local socket, with the same Host the reverse proxy uses.
    spec = plistlib.loads(PLIST.read_bytes()) if PLIST.is_file() else {}
    origin = spec.get("EnvironmentVariables",{}).get("AUDIT_PUBLIC_ORIGIN")
    if origin is not None:
        return urlsplit(origin).hostname
    inherited = subprocess.run(["launchctl","getenv","AUDIT_PUBLIC_ORIGIN"],capture_output=True,text=True,timeout=2)
    origin = inherited.stdout.strip()
    if not origin and (ROOT/".env").is_file():
        python = ROOT/".venv"/"bin"/"python"
        probe_host = ("from dotenv import dotenv_values; from urllib.parse import urlsplit; import sys; "
                      "print(urlsplit(dotenv_values(sys.argv[1],interpolate=False).get('AUDIT_PUBLIC_ORIGIN') or '').hostname or '')")
        value = subprocess.run([str(python),"-I","-c",probe_host,str(ROOT/".env")],capture_output=True,text=True,check=True,timeout=3)
        return value.stdout.strip() or None
    return urlsplit(origin or "").hostname


def probe(address, files, enterprise, timeout, host=None):
    client = http.client.HTTPConnection(*address,timeout=timeout)
    def read(path,limit):
        headers = {"Accept-Encoding":"identity"}
        if host:
            headers["Host"] = "["+host+"]" if ":" in host else host
        client.request("GET",path,headers=headers)
        response = client.getresponse()
        data = response.read(limit+1)
        if response.status!=200:
            if path=="/api/ready" and response.status==503:
                reason = json.loads(data).get("component")
                issues = {"worker":"后台工作进程未运行","database":"任务数据库无法读取","database_write":"后台任务正在等待数据库写入"}
                if reason in issues:
                    raise ValueError(issues[reason])
            raise ValueError(f"{path} 返回 HTTP {response.status}")
        return data
    try:
        ready = json.loads(read("/api/ready",4096))
        if (not isinstance(ready,dict) or ready.get("status")!="ready" or ready.get("mode") not in {"local","saas"}
                or (enterprise and ready["mode"]!="saas")):
            raise ValueError("工作进程、数据库或实例模式尚未就绪")
        for path,expected in files.items():
            if read(path,len(expected))!=expected:
                raise ValueError("页面或前端文件与当前部署不一致 "+path)
    finally:
        client.close()


def wait_ready(enterprise, previous=None, timeout=30):
    frontend = ROOT.parent/"frontend"
    try:
        files = frontend_files(frontend)
    except (OSError,UnicodeError) as error:
        raise SystemExit("无法读取本次部署的网页文件："+str(error)) from error
    deadline = time.monotonic()+timeout
    problem = "等待服务进程监听端口"
    host = trusted_host()
    while time.monotonic()<deadline:
        try:
            pid = agent_pid()
            if pid and pid!=previous:
                for address in listen_addresses(pid):
                    try:
                        probe(address,files,enterprise,min(2,max(.1,deadline-time.monotonic())),host)
                    except (OSError,ValueError,http.client.HTTPException) as error:
                        problem = str(error)
                        continue
                    if agent_pid()==pid:
                        host,port = address
                        url = f"http://[{host}]:{port}/" if ":" in host else f"http://{host}:{port}/"
                        print(f"网页、后台工作进程及数据库已就绪 {url}  PID {pid}")
                        return
        except (OSError,ValueError,http.client.HTTPException,subprocess.TimeoutExpired) as error:
            problem = str(error)
        time.sleep(min(.25,max(0,deadline-time.monotonic())))
    log = ROOT/".runtime"/("enterprise" if enterprise else "")/"service-error.log"
    raise SystemExit(f"等待网页就绪超时。{problem}。服务日志 {log}")


def install(enterprise=False):
    python = ROOT / ".venv" / "bin" / "python"
    if not python.is_file():
        raise SystemExit("请先在 server/.venv 安装 Python 环境。")
    if PLIST.is_file():
        existing = plistlib.loads(PLIST.read_bytes())
        if existing.get("WorkingDirectory") != str(ROOT):
            raise SystemExit("同名服务来自其他目录。")
    runtime = ROOT / ".runtime" / ("enterprise" if enterprise else "")
    runtime.mkdir(exist_ok=True, parents=True, mode=0o700)
    env = {"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin", "PYTHONUNBUFFERED": "1"}
    if enterprise:
        env.update(AUDIT_ACCESS_MODE="saas", AUDIT_BIND="127.0.0.1", AUDIT_PUBLIC_ORIGIN="http://127.0.0.1:8010",
                   AUDIT_DATA_DIR=str(ROOT / "data-enterprise"), PORT="8010")
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
    previous = agent_pid()
    if launch("print", TARGET, check=False, quiet=True).returncode == 0:
        launch("bootout", TARGET)
    for attempt in range(15):
        if launch("bootstrap", DOMAIN, str(PLIST), check=False, quiet=True).returncode == 0:
            break
        if attempt == 14:
            launch("bootstrap", DOMAIN, str(PLIST))
        time.sleep(0.3)
    wait_ready(enterprise,previous)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["install", "status", "restart", "stop"])
    parser.add_argument("--enterprise", action="store_true", help="管理 8010 端口的独立企业实例")
    args = parser.parse_args()
    command = args.command
    if args.enterprise:
        LABEL = "local.fish-audit.enterprise"
        TARGET = f"{DOMAIN}/{LABEL}"
        PLIST = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")
    if sys.platform != "darwin":
        raise SystemExit("该脚本适用于 macOS 用户登录会话。")
    if command == "install":
        install(args.enterprise)
    elif command == "restart":
        previous = agent_pid()
        launch("kickstart", "-k", TARGET)
        wait_ready(args.enterprise,previous)
    elif command == "stop":
        launch("bootout", TARGET)
    else:
        launch("print", TARGET)
        wait_ready(args.enterprise)
