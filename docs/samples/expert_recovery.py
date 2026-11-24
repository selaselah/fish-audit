"""Exercise a real expert response, a hard worker exit and recovery in a new synthetic enterprise."""

import argparse
import hashlib
import io
import json
import logging
import multiprocessing
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

from werkzeug.serving import make_server

import generate

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/"server"))

from backup import restore, snapshot
from capacity import usage
from jobs import Worker
from main import create_app
from storage import Store
from verify import verify


def interrupted_worker(root,case_id):
    store = Store(root)
    def stop_before_publication(cid,*args):
        assert cid==case_id
        os._exit(86)
    store.save_report = stop_before_publication
    assert store.claim()==case_id
    Worker(store).run(case_id)


def inspect_browser(app,client,workspace,case_id):
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    http = make_server("127.0.0.1",0,app,threaded=True)
    thread = threading.Thread(target=http.serve_forever,daemon=True)
    thread.start()
    try:
        env = {k:v for k,v in os.environ.items() if k!="OPENAI_API_KEY"}
        env.update(SYNTHETIC_RECOVERY_ORIGIN=f"http://127.0.0.1:{http.server_port}",SYNTHETIC_RECOVERY_WORKSPACE=workspace,
                   SYNTHETIC_RECOVERY_SESSION=client.get_cookie("fish_session").value)
        subprocess.run(["node","frontend/tests/workspace.mjs","--recovering-case",case_id],cwd=PROJECT,env=env,check=True,timeout=100)
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def exercise(area,browser):
    source = area/"演练发票.pdf"
    generate.pdfmetrics.registerFont(generate.UnicodeCIDFont("STSong-Light"))
    generate.pdf(source,"采购发票",generate.fields("发票","YL-HT-RECOVER-01","11,300.00",number="YL-FP-RECOVER-01"))
    store = Store(area/"live")
    app = create_app(store,Worker(store))
    client = app.test_client()
    account = {"login":"recovery.auditor","password":secrets.token_urlsafe(24)}
    new = client.post("/api/auth/register",json={**account,"workspace":"合成演练企业","name":"演练审计员"})
    assert new.status_code==201,new.json
    workspace = new.json["selected"]
    with source.open("rb") as stream:
        upload = client.post(f"/api/w/{workspace}/cases",headers={"X-CSRF-Token":new.json["csrf"]},
                             data={"title":"合成演练 · 专家响应恢复","files":(stream,source.name)})
    assert upload.status_code==202,upload.json
    cid = upload.json["id"]
    path = f"/api/w/{workspace}/cases/{cid}"
    child = multiprocessing.get_context("spawn").Process(target=interrupted_worker,args=(store.root,cid))
    child.start()
    try:
        for _ in range(60):
            child.join(10)
            if child.exitcode is not None:
                break
        assert child.exitcode==86,f"演练进程退出状态 {child.exitcode}"
    finally:
        if child.is_alive():
            child.terminate()
            child.join()
    pending = client.get(path).json
    assert (pending["rev"],pending["progress"],pending["page_progress"]["expert"]["target_rev"])==(0,96,1)
    before = usage(store,workspace)
    with store.connect() as db:
        calls = db.execute("SELECT response_id FROM model_requests WHERE case_id=? AND operation='audit_followups'",(cid,)).fetchall()
        pending_content,pending_hash = db.execute("SELECT content,sha256 FROM expert_checkpoints WHERE case_id=?",(cid,)).fetchone()
    assert len(calls)==1 and calls[0]["response_id"]
    assert hashlib.sha256(pending_content.encode()).hexdigest()==pending_hash
    pending_trace = json.loads(pending_content)["trace"]
    if browser:
        inspect_browser(app,client,workspace,cid)
    snapshot(store.root,area/"backup")
    manifest = restore(area/"backup",area/"restore")
    with patch.dict(os.environ,{"OPENAI_API_KEY":"","AUDIT_MONTHLY_REQUESTS":str(before["requests"])}):
        restored = Store(area/"restore")
        restored.recover()
        assert restored.claim()==cid
        Worker(restored).run(cid)
    after = usage(restored,workspace)
    assert (before["requests"],before["input_tokens"],before["output_tokens"])==(after["requests"],after["input_tokens"],after["output_tokens"])
    paper = restored.report(cid,1)["report"]
    expert = paper["calls"]["expert"]
    assert expert["response_id"]==calls[0]["response_id"]
    assert all(pending_trace[key]==expert[key] for key in pending_trace if key!="instruction")
    assert paper["calls"]["instructions"][expert["prompt_sha256"]]==pending_trace["instruction"]
    login = create_app(restored,Worker(restored)).test_client()
    assert login.post("/api/auth/login",json=account).status_code==200
    detail = login.get(path).json
    assert detail["rev"]==1 and detail["status"]=="ready" and "expert" not in detail["page_progress"]
    assert any("与已保存响应匹配" in row["message"] for row in detail["events"])
    with login.get(path+"/reports/1/bundle") as bundle:
        checked = verify(io.BytesIO(bundle.data),True)
    assert checked[:2]==(cid,1)
    print(f"通过 · 恢复前后各 {after['requests']} 次已发模型请求，其中专家调用 1 次。恢复核验 {manifest['evidence_files']} 份原件与页图。")
    print(f"R1 保留原专家响应编号，{len(paper['findings'])} 项发现，{checked[2]} 个包内文件通过严格复算。")


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true",required=True,help="用真实模型运行带水印的演练发票")
    parser.add_argument("--browser",action="store_true",help="用本机 Chrome 检查中断时的工作台")
    args = parser.parse_args()
    if not os.getenv("OPENAI_API_KEY","").strip():
        parser.error("请在 server/.env 配置 OpenAI 项目密钥。")
    with tempfile.TemporaryDirectory(prefix="fish-expert-drill-") as folder, patch.dict(os.environ,{"AUDIT_ACCESS_MODE":"saas","AUDIT_PUBLIC_ORIGIN":""}):
        exercise(Path(folder),args.browser)
