import hashlib
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path


if __name__ == "__main__":
    local_env = Path(__file__).resolve().parent / ".venv"
    local_python = local_env / "bin" / "python"
    if local_python.is_file() and Path(sys.prefix).resolve() != local_env:
        os.execv(str(local_python), [str(local_python), *sys.argv])

from flask import Blueprint, Flask, g, jsonify, request, send_file
from waitress import serve
from werkzeug.exceptions import HTTPException

from config import (AUDITOR_MODEL, CaseError, DATA, FORMATS, FRONTEND, MAX_CASE_BYTES,
                    MAX_FILE_BYTES, MAX_FILES, MAX_PAGES, MODEL, PROFILE, PROFILES)
from accounts_api import configure_access
from controls import CATALOG, VERSION
from documents import digest
from evidence import export_bundle
from graph import compact
from jobs import Worker
from model import FIELDS
from review import review_text
from storage import Store, encode


def text_field(value, name, limit):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit or any(
            ord(char) < 32 and char not in "\n\t" for char in value):
        raise CaseError(f"请填写有效的{name}，最多 {limit} 字。", 400)
    return value.strip()


def upload(store, workspace, user):
    title = text_field(request.form.get("title"), "任务名称", 100)
    profile = request.form.get("profile", PROFILE)
    if profile not in PROFILES:
        raise CaseError("请选择支持的审计范围。", 400)
    files = request.files.getlist("files")
    if not 1 <= len(files) <= MAX_FILES:
        raise CaseError(f"每案可上传 1 至 {MAX_FILES} 份资料。", 400)
    key = request.headers.get("Idempotency-Key") or uuid.uuid4().hex
    if not re.fullmatch(r"[a-zA-Z0-9_-]{12,100}", key):
        raise CaseError("提交编号无效。", 400)
    if workspace != "local":
        key = f"{workspace}:{user['id']}:{key}"
    case_id = uuid.uuid4().hex
    folder = store.files / case_id
    folder.mkdir(mode=0o700)
    keep = False
    try:
        docs, total = [], 0
        for index, item in enumerate(files, 1):
            name = text_field((item.filename or "").replace("\\", "/").split("/")[-1], "文件名", 200)
            ext = Path(name).suffix.lower()
            if ext not in FORMATS:
                raise CaseError(f"不支持 {ext or '无后缀'} 文件，请使用 PDF、Word 或图片。", 415)
            doc = f"d{index:02d}"
            target = folder / doc
            target.mkdir()
            hasher = hashlib.sha256()
            size = 0
            with (target / ("original" + ext)).open("xb") as output:
                while chunk := item.stream.read(128 * 1024):
                    size += len(chunk)
                    total += len(chunk)
                    if size > MAX_FILE_BYTES or total > MAX_CASE_BYTES:
                        raise CaseError("单份资料上限 16 MiB，整案上限 48 MiB。", 413)
                    output.write(chunk)
                    hasher.update(chunk)
            if not size:
                raise CaseError("资料为空，请重新选择文件。", 400)
            docs.append({"id": doc, "name": name, "ext": ext, "sha256": hasher.hexdigest(), "size": size})
        fingerprint = digest(encode([title, docs] if profile == PROFILE else [title, docs, profile]).encode())
        existing = store.existing(key, fingerprint)
        if existing:
            return existing
        try:
            store.create(case_id, title, docs, key, fingerprint, profile, workspace, user)
        except sqlite3.IntegrityError:
            existing = store.existing(key, fingerprint)
            if existing:
                return existing
            raise
        keep = True
        return case_id
    finally:
        if not keep:
            shutil.rmtree(folder, ignore_errors=True)


def json_body():
    if request.content_length and request.content_length > 64 * 1024:
        raise CaseError("请求过大。", 413)
    data = request.get_json()
    if not isinstance(data, dict):
        raise CaseError("请求必须为 JSON 对象。", 400)
    return data


def create_app(store, worker):
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=MAX_CASE_BYTES + 256*1024, MAX_FORM_PARTS=MAX_FILES+4,
                      TRUSTED_HOSTS=["127.0.0.1", "localhost", "[::1]"])
    app.json.ensure_ascii = False

    directory = configure_access(app, store, json_body)
    business = Blueprint("business", __name__)

    @business.url_value_preprocessor
    def select_workspace(endpoint, values):
        g.workspace = values.pop("wid", None) if values else None

    @business.before_request
    def authorize_business():
        action = request.endpoint.rsplit(".", 1)[-1]
        if g.workspace is None:
            if app.config["AUDIT_MODE"] != "local":
                raise CaseError("请从企业工作区访问任务。", 404)
            g.workspace, g.role, g.actor = "local", "admin", None
        else:
            if not g.user:
                raise CaseError("请先登录企业工作区。", 401)
            g.role = directory.member(g.user["id"], g.workspace)
            g.actor = g.user
        case_id = (request.view_args or {}).get("case_id")
        if case_id:
            owner = g.actor["id"] if g.role == "employee" else None
            store.require_case(case_id, g.workspace, owner)
        if g.role == "employee" and action not in {"cases","submit","detail","original","page_image"}:
            raise CaseError("此操作需要审计人员或管理员权限。", 403)

    def signer(data):
        return g.actor["name"] if g.actor else text_field(data.get("reviewer"), "审计人员姓名", 50)

    @app.after_request
    def headers(response):
        response.headers.update({"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
                                 "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                                 "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    @app.errorhandler(CaseError)
    def known_error(error):
        return jsonify(error=str(error)), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {400: "请求格式无效。", 404: "资源不存在。", 413: "上传超出限制。",
                    415: "请求格式不支持。", 405: "请求方法不支持。"}
        return jsonify(error=messages.get(error.code, "请求失败。")), error.code

    @app.get("/")
    def index():
        return send_file(FRONTEND / "index.html")

    @app.get("/<filename>")
    def asset(filename):
        if filename not in {"app.js", "team.js", "style.css"}:
            raise CaseError("资源不存在。", 404)
        return send_file(FRONTEND / filename)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", mode="ollama" if os.getenv("OLLAMA_MODEL") else "demo",
                       audit={"provider": "openai", "configured": bool(os.getenv("OPENAI_API_KEY", "").strip()), "model": MODEL,
                              "auditor_model": AUDITOR_MODEL, "profile": PROFILE, "profiles": PROFILES, "max_pages": MAX_PAGES})

    @app.post("/api/reviews")
    def legacy():
        if app.config["AUDIT_MODE"] != "local":
            raise CaseError("资源不存在。", 404)
        text = text_field(json_body().get("text"), "待审核文本", 5000)
        try:
            return jsonify(review_text(text, os.getenv("OLLAMA_MODEL"), os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")))
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            raise CaseError("模型暂不可用或返回格式无效，请人工复核。", 502)

    @app.get("/api/controls")
    def controls():
        return jsonify(**VERSION, profiles=PROFILES, fields=FIELDS, rules=[{"id": key, "name": value[0], "basis": value[1]}
                                        for key, value in CATALOG.items()])

    @business.get("/cases")
    def cases():
        return jsonify(cases=store.summary(g.workspace, g.actor["id"] if g.role == "employee" else None))

    @business.post("/cases")
    def submit():
        if request.mimetype != "multipart/form-data":
            raise CaseError("请以 multipart/form-data 上传资料。", 415)
        if not os.getenv("OPENAI_API_KEY"):
            raise CaseError("请配置 server/.env 中的 OPENAI_API_KEY 并重启服务。", 503)
        case_id = upload(store, g.workspace, g.actor)
        worker.wakeup.set()
        return jsonify(id=case_id), 202

    @business.get("/cases/<case_id>")
    def detail(case_id):
        data = store.detail(case_id)
        if g.role == "employee":
            data["revisions"] = []
        data["can_review"] = g.role != "employee"
        return jsonify(data)

    @business.get("/cases/<case_id>/reports/<int:rev>")
    def report(case_id, rev):
        return jsonify(store.report(case_id, rev))

    @business.get("/cases/<case_id>/reports/<int:rev>/methods/<name>")
    def method_source(case_id, rev, name):
        policy = store.report(case_id, rev)["report"]["policy"]
        checksum = policy.get("code_sha256", {}).get(name)
        if not checksum or not policy.get("archived_methods"):
            raise CaseError("该底稿没有归档此程序源码。", 404)
        source = store.method_source(checksum)
        if digest(source) != checksum:
            raise CaseError("程序源码与底稿摘要不一致。", 409)
        return app.response_class(source, mimetype="text/plain")

    @business.get("/cases/<case_id>/reports/<int:rev>/bundle")
    def export(case_id, rev):
        stream = tempfile.SpooledTemporaryFile(max_size=4 * 1024**2)
        try:
            export_bundle(store, case_id, rev, stream)
            return send_file(stream, as_attachment=True, mimetype="application/zip",
                             download_name=f"fish-audit-{case_id[:10]}-R{rev}.zip")
        except Exception:
            stream.close()
            raise

    @business.get("/cases/<case_id>/documents/<doc>/original")
    def original(case_id, doc):
        match = next((item for item in store.documents(case_id) if item["id"] == doc), None)
        if not match:
            raise CaseError("资料不存在。", 404)
        return send_file(store.files / case_id / doc / ("original" + match["ext"]), as_attachment=True,
                         download_name=match["name"], mimetype="application/octet-stream")

    @business.get("/cases/<case_id>/documents/<doc>/pages/<int:number>")
    def page_image(case_id, doc, number):
        with store.connect() as db:
            exists = db.execute("SELECT 1 FROM pages WHERE case_id=? AND doc=? AND number=?", (case_id, doc, number)).fetchone()
        if not exists:
            raise CaseError("页图不存在。", 404)
        return send_file(store.files / case_id / doc / f"{number}.jpg", mimetype="image/jpeg")

    @business.post("/cases/<case_id>/retry")
    def retry(case_id):
        store.retry(case_id, g.actor and g.actor["id"])
        worker.wakeup.set()
        return jsonify(id=case_id), 202

    @business.post("/cases/<case_id>/rerun")
    def rerun(case_id):
        revision = json_body().get("rev")
        if type(revision) != int or revision <= 0:
            raise CaseError("请选择有效底稿版本。", 400)
        store.rerun(case_id, revision, g.actor and g.actor["id"])
        worker.wakeup.set()
        return jsonify(id=case_id), 202

    @business.post("/cases/<case_id>/attest")
    @business.post("/cases/<case_id>/signoff")
    def review(case_id):
        data = json_body()
        revision = data.get("rev")
        if type(revision) is not int or revision < 1:
            raise CaseError("请选择有效底稿版本。", 400)
        reviewer = signer(data)
        note = text_field(data.get("note"), "核验意见", 2000)
        facts = None
        if request.path.endswith("/attest"):
            choices = ("confirm", "dispute")
            facts = data.get("facts")
            if not isinstance(facts, list) or not 1 <= len(facts) <= 140 or any(type(ref) is not str for ref in facts):
                raise CaseError("请选择本页要核对的证据。", 400)
        else:
            choices = ("approve", "return", "escalate")
        decision = data.get("decision")
        if decision not in choices:
            raise CaseError("无效的核验决定。", 400)
        store.review(case_id, revision, reviewer, note, decision, facts, g.actor and g.actor["id"])
        worker.wakeup.set()
        return jsonify(id=case_id), 202 if facts is not None else 200

    @business.post("/cases/<case_id>/amend")
    def amend(case_id):
        data = json_body()
        doc, page, revision = data.get("doc"), data.get("page"), data.get("rev")
        if not isinstance(doc, str) or type(page) is not int or type(revision) is not int:
            raise CaseError("请选择文件、页码和底稿版本。", 400)
        field, region, target = data.get("field"), data.get("region"), data.get("target")
        if not isinstance(field, str) or field not in FIELDS or region not in ("top", "middle", "bottom"):
            raise CaseError("字段类型或页内位置无效。", 400)
        if target is not None and not isinstance(target, str):
            raise CaseError("无效的证据编号。", 400)
        quote = text_field(data.get("quote"), "原文引文", 1500)
        value = text_field(data.get("value"), "原文取值", 500)
        if compact(value) not in compact(quote):
            raise CaseError("取值须完整出现在所引原文中。")
        reviewer = signer(data)
        note = text_field(data.get("note"), "核验意见", 2000)
        fact_id = store.amend(case_id, revision, reviewer, note, target, doc, page, field, value, quote, region, g.actor and g.actor["id"])
        worker.wakeup.set()
        return jsonify(id=case_id, fact=fact_id), 202

    app.register_blueprint(business, url_prefix="/api", name="local_cases")
    app.register_blueprint(business, url_prefix="/api/w/<wid>", name="team_cases")
    return app


if __name__ == "__main__":
    os.umask(0o077)
    store = Store(DATA)
    worker = Worker(store)
    worker.start()
    port = int(os.getenv("PORT", "8000"))
    print(f"Fish Audit http://127.0.0.1:{port}", flush=True)
    app = create_app(store, worker)
    host = os.getenv("AUDIT_BIND", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1") and (app.config["AUDIT_MODE"] != "saas" or not app.config["AUDIT_ORIGIN"]):
        raise SystemExit("对外监听需要 SaaS 模式与 AUDIT_PUBLIC_ORIGIN。")
    serve(app, host=host, port=port, threads=8,
          max_request_body_size=MAX_CASE_BYTES + 256*1024, channel_timeout=120)
