"""Observe the progress page during a real SQLite write lock in a temporary local instance."""

import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from werkzeug.serving import WSGIRequestHandler, make_server

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/"server"))
from jobs import Worker
from main import create_app
from storage import Store
from verify import verify


class Quiet(WSGIRequestHandler):
    def log_request(self,*args):
        pass


def exercise(root):
    store = Store(root/"data")
    received,deliver = threading.Event(),threading.Event()
    reads,opinions = [],[]
    def extract(path):
        reads.append(path)
        out = {"quality":"readable","facts":[]}
        return out,{"model":"controlled-page","output":out}
    def expert(graph,findings):
        opinions.append(len(findings))
        received.set()
        if not deliver.wait(10):
            raise RuntimeError("等待演练数据库写锁超时")
        return [],{"model":"controlled-expert","output":{"followups":[]}}
    worker = Worker(store,extract,expert)
    app = create_app(store,worker)
    picture = Image.new("RGB",(360,100),"white")
    ImageDraw.Draw(picture).text((16,35),"SYNTHETIC TRAINING ONLY",fill="black")
    file=io.BytesIO()
    picture.save(file,format="JPEG")
    file.seek(0)
    client=app.test_client()
    response=client.post("/api/cases",data={"title":"合成演练 · 写锁释放后继续","files":(file,"水印演练.jpg")})
    assert response.status_code==202
    cid=response.json["id"]
    def process():
        worker.thread=threading.current_thread()
        with store.background_writes():
            worker.run(store.claim())
    http=make_server("127.0.0.1",0,app,threaded=True,request_handler=Quiet)
    server_thread=threading.Thread(target=http.serve_forever,daemon=True)
    server_thread.start()
    observed=root/"observed"
    env={**os.environ,"SYNTHETIC_WRITER_ORIGIN":f"http://127.0.0.1:{http.server_port}","SYNTHETIC_WRITER_OBSERVED":str(observed)}
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(process)
            assert received.wait(5)
            with subprocess.Popen(["node","frontend/tests/workspace.mjs","--waiting-case",cid],cwd=PROJECT,env=env) as browser:
                with sqlite3.connect(store.path) as hold:
                    hold.execute("BEGIN IMMEDIATE")
                    deliver.set()
                    deadline=time.monotonic()+35
                    while not observed.exists() and browser.poll() is None and time.monotonic()<deadline:
                        time.sleep(.1)
                    assert observed.is_file()
                future.result(5)
                assert browser.wait(timeout=35)==0
        with client.get(f"/api/cases/{cid}/reports/1/bundle") as result:
            assert verify(io.BytesIO(result.data),True)[:2]==(cid,1)
        assert len(reads)==len(opinions)==1
        print("1 次受控页面解析、1 次受控专家响应，生成 1 份可离线复算的底稿。")
    finally:
        deliver.set()
        http.shutdown()
        server_thread.join()
        http.server_close()


if __name__=="__main__":
    with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{"AUDIT_ACCESS_MODE":"local",
            "AUDIT_PUBLIC_ORIGIN":"","OPENAI_API_KEY":"synthetic-local-only"}):
        exercise(Path(temp))
