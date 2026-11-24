import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import service
from jobs import Worker
from main import create_app
from storage import Store


class WebReadinessTests(unittest.TestCase):
    def test_ready_reads_the_existing_database_and_requires_a_running_worker(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{"AUDIT_ACCESS_MODE":"local","AUDIT_PUBLIC_ORIGIN":""}):
            store = Store(Path(temp))
            worker = Worker(store)
            client = create_app(store,worker).test_client()
            response = client.get("/api/ready")
            self.assertEqual((response.status_code,response.json.get("component")),(503,"worker"))
            worker.thread = threading.current_thread()
            self.assertEqual(client.get("/api/ready").json,{"status":"ready","mode":"local"})
            missing = Path(temp)/"missing.sqlite3"
            with patch.object(store,"path",missing):
                response = client.get("/api/ready")
                self.assertEqual((response.status_code,response.json.get("component")),(503,"database"))
                self.assertFalse(missing.exists())

    def test_restart_waits_for_the_new_process_and_the_deployed_browser_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frontend = root/"frontend"
            frontend.mkdir()
            (frontend/"index.html").write_text('<link rel="stylesheet" href="/style.css"><script src="/app.js?v=2"></script>')
            (frontend/"style.css").write_text("body{}")
            (frontend/"app.js").write_text("void 0")
            files = service.frontend_files(frontend)
            calls, hosts = [],[]
            availability = {"ready":False}
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):
                    pass

                def do_GET(self):
                    calls.append(self.path)
                    hosts.append(self.headers["Host"])
                    status = 200
                    if self.path=="/api/ready":
                        ready = availability["ready"]
                        status = 200 if ready else 503
                        data = json.dumps({"status":"ready","mode":"saas"} if ready else {"component":"worker"}).encode()
                        availability["ready"] = True
                    else:
                        data = files.get(self.path,b"")
                    self.send_response(status)
                    self.send_header("Content-Length",str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)

            with ThreadingHTTPServer(("127.0.0.1",0),Handler) as http:
                thread = threading.Thread(target=http.serve_forever,daemon=True)
                thread.start()
                self.addCleanup(thread.join,2)
                try:
                    pids = iter((101,102))
                    with patch.object(service,"ROOT",root/"server"),patch.object(service,"agent_pid",side_effect=lambda:next(pids,102)), \
                            patch.object(service,"listen_addresses",return_value=[http.server_address]) as listeners, \
                            patch.object(service,"trusted_host",return_value="audit.example"),contextlib.redirect_stdout(io.StringIO()):
                        service.wait_ready(True,previous=101,timeout=3)
                    self.assertTrue(all(c.args==(102,) for c in listeners.call_args_list))
                    self.assertEqual(calls,["/api/ready","/api/ready","/","/style.css","/app.js"])
                    self.assertEqual(set(hosts),{"audit.example"})
                    files["/app.js"]=b"stale script"
                    with self.assertRaisesRegex(ValueError,"app.js"):
                        service.probe(http.server_address,service.frontend_files(frontend),True,1)
                finally:
                    http.shutdown()

    def test_process_without_a_listening_web_port_is_unavailable(self):
        with patch.object(service,"agent_pid",return_value=72),patch.object(service,"listen_addresses",return_value=[]), \
                patch.object(service,"trusted_host",return_value=None):
            with self.assertRaisesRegex(SystemExit,"等待网页就绪超时"):
                service.wait_ready(False,timeout=.02)
