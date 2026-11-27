import hashlib
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
from contextlib import ExitStack, closing
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode, urlsplit


if __name__ == "__main__":
    local_env = Path(__file__).resolve().parent / ".venv"
    local_python = local_env / "bin" / "python"
    if local_python.is_file() and Path(sys.prefix).resolve() != local_env:
        os.execv(str(local_python), [str(local_python), *sys.argv])

from flask import Blueprint, Flask, g, jsonify, redirect, request, send_file, send_from_directory
from PIL import Image
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
from invoice_history import InvoiceHistoryChanged, LegacyMaskedInvoice
from field_sources import PaymentSourceError
from payment_index import LegacyPartialTransfer
from model import FIELDS
from review import review_text
from rule_replay import RulesUnavailable, replay_from_git
from storage import Store, encode, stamp
from workbench import inbox, search_evidence


def text_field(value, name, limit):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit or any(
            ord(char) < 32 and char not in "\n\t" for char in value):
        raise CaseError(f"请填写有效的{name}，最多 {limit} 字。", 400)
    return value.strip()


def verified_stream(path, expected):
    stream = tempfile.SpooledTemporaryFile(max_size=2*1024**2)
    try:
        hasher = hashlib.sha256()
        try:
            with path.open("rb") as source:
                while chunk := source.read(128*1024):
                    hasher.update(chunk)
                    stream.write(chunk)
        except FileNotFoundError as exc:
            raise CaseError("存证文件缺失，请核对本机资料或备份。", 409) from exc
        if hasher.hexdigest() != expected:
            raise CaseError("存证文件与记录的摘要不符，无法提供此原件或页图。", 409)
        stream.seek(0)
        return stream
    except BaseException:
        stream.close()
        raise


def verified_download(path, expected, name, mimetype, *, attachment):
    stream = verified_stream(path, expected)
    try:
        size = stream.seek(0, os.SEEK_END)
        stream.seek(0)
        response = send_file(stream, download_name=name, mimetype=mimetype, as_attachment=attachment,
                             conditional=False, etag=expected)
        response.content_length = size
        return response.make_conditional(request, accept_ranges=True, complete_length=size)
    except BaseException:
        stream.close()
        raise


def save_original(folder, doc, name, stream, remaining):
    name = text_field((name or "").replace("\\", "/").split("/")[-1], "文件名", 200)
    ext = Path(name).suffix.lower()
    if ext not in FORMATS:
        raise CaseError(f"不支持 {ext or '无后缀'} 文件，请使用 PDF、Word 或图片。", 415)
    target = folder / doc
    target.mkdir()
    hasher, size = hashlib.sha256(), 0
    with (target / ("original" + ext)).open("xb") as output:
        while chunk := stream.read(128 * 1024):
            size += len(chunk)
            if size > MAX_FILE_BYTES or size > remaining:
                raise CaseError("单份资料上限 16 MiB，整案上限 48 MiB。", 413)
            output.write(chunk)
            hasher.update(chunk)
    if not size:
        raise CaseError("资料为空，请重新选择文件。", 400)
    return {"id": doc, "name": name, "ext": ext, "sha256": hasher.hexdigest(), "size": size}


def upload(store, workspace, user, parent=None):
    title = text_field(request.form.get("title"), "任务名称", 100)
    profile = request.form.get("profile", PROFILE)
    inherited, supplement = [], None
    if parent:
        revision = request.form.get("rev", "")
        if not re.fullmatch(r"[1-9][0-9]{0,8}", revision):
            raise CaseError("请选择有效的退回底稿版本。", 400)
        profile, previous = store.supplement_input(parent, int(revision), workspace, user and user["id"])
        if request.form.get("profile", profile) != profile:
            raise CaseError("补件须沿用前案的审计范围。", 400)
        keep_ids = request.form.getlist("retain")
        inherited = [doc for doc in previous if doc["id"] in keep_ids]
        if len(inherited) != len(keep_ids):
            raise CaseError("沿用清单中存在重复或不属于前案的原件编号。", 400)
        note = request.form.get("note", "").strip()
        supplement = {"parent": parent, "rev": int(revision), "retained": [],
                      "note": text_field(note, "补件说明", 2000) if note else ""}
    if profile not in PROFILES:
        raise CaseError("请选择支持的审计范围。", 400)
    files = request.files.getlist("files")
    if not 1 <= len(files) + len(inherited) <= MAX_FILES:
        raise CaseError(f"每案可提交 1 至 {MAX_FILES} 份资料（含沿用原件）。", 400)
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
        docs, remaining = [], MAX_CASE_BYTES
        with ExitStack() as streams:
            inputs = []
            for doc in inherited:
                path = store.files / parent / doc["id"] / ("original" + doc["ext"])
                try:
                    inputs.append((doc["name"], streams.enter_context(path.open("rb")), doc))
                except FileNotFoundError as exc:
                    raise CaseError("所选前案原件缺失，请检查归档资料。", 409) from exc
            inputs.extend((item.filename, item.stream, None) for item in files)
            for index, (name, stream, previous) in enumerate(inputs, 1):
                doc = save_original(folder, f"d{index:02d}", name, stream, remaining)
                if previous:
                    if any(doc[k] != previous[k] for k in ("size", "sha256")):
                        raise CaseError("前案原件与签收时保存的摘要不符。", 409)
                    supplement["retained"].append({"parent_doc": previous["id"], "doc": doc["id"]})
                docs.append(doc)
                remaining -= doc["size"]
        identity = [title, docs] if profile == PROFILE else [title, docs, profile]
        if supplement:
            identity.append(supplement)
        fingerprint = digest(encode(identity).encode())
        accepted = store.create(case_id, title, docs, key, fingerprint, profile, workspace, user, supplement)
        keep = accepted == case_id
        return accepted
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
        if g.role == "employee" and action not in {"cases","ledger","submit","detail","original","page_image"}:
            raise CaseError("此操作需要审计人员或管理员权限。", 403)

    def signer(data):
        return g.actor["name"] if g.actor else text_field(data.get("reviewer"), "审计人员姓名", 50)

    def verify_revision_source(case_id, node_id, checksum):
        revisions = request.args.getlist("rev")
        if not revisions:
            return
        if g.role == "employee":
            raise CaseError("查看底稿版本需要审计人员或管理员权限。", 403)
        if len(revisions) != 1 or not re.fullmatch(r"[1-9][0-9]{0,8}", revisions[0]):
            raise CaseError("底稿版本无效。", 400)
        graph = store.report(case_id, int(revisions[0]))["report"]["graph"]
        node = next((n for n in graph["nodes"] if n["id"] == node_id and n["type"] in {"document","page"}), None)
        if not node:
            raise CaseError("该底稿版本中没有此原件或页图。", 404)
        if node["sha256"] != checksum:
            raise CaseError("资料记录与所选底稿中的来源摘要不符。", 409)

    @app.after_request
    def headers(response):
        response.headers.update({"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
                                 "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                                 "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    @app.errorhandler(CaseError)
    def known_error(error):
        if isinstance(error,PaymentSourceError):
            return jsonify(error=str(error),payment_source=error.source),error.status
        if isinstance(error,InvoiceHistoryChanged):
            return jsonify(error=str(error),invoice_history={"count":len(error.differences),"changes":error.differences[:8]}),error.status
        if isinstance(error,(LegacyMaskedInvoice,LegacyPartialTransfer)):
            return jsonify(error=str(error),incomplete_numbers={"case_id":error.case_id,"rev":error.revision,
                           "count":len(error.fields),"facts":error.fields[:8]}),error.status
        return jsonify(error=str(error)), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {400: "请求格式无效。", 404: "资源不存在。", 413: "上传超出限制。",
                    415: "请求格式不支持。", 405: "请求方法不支持。"}
        return jsonify(error=messages.get(error.code, "请求失败。")), error.code

    @app.get("/")
    def product_home():
        return send_file(FRONTEND / "landing.html")

    @app.get("/app")
    def workspace():
        return send_file(FRONTEND / "index.html")

    @app.get("/workpaper/<case_id>")
    @app.get("/w/<wid>/workpaper/<case_id>")
    def workpaper(case_id, wid=None):
        if (not re.fullmatch(r"[a-f0-9]{32}", case_id) or (wid and not re.fullmatch(r"[a-f0-9]{32}", wid))
                or (wid is None and app.config["AUDIT_MODE"] != "local")):
            raise CaseError("未找到该底稿入口。",404)
        args = {}
        if "rev" in request.args:
            version = request.args["rev"]
            if not re.fullmatch(r"[1-9][0-9]{0,8}",version):
                raise CaseError("底稿版本无效。",400)
            args["rev"] = version
        if "fact" in request.args:
            ref = request.args["fact"]
            if not re.fullmatch(r"d[0-9]{2}/p[1-9][0-9]*/(?:[ft][1-9][0-9]*|h[a-f0-9]{12})",ref) or "rev" not in args:
                raise CaseError("请选择有效的版本和证据编号。",400)
            args["fact"] = ref
        if "finding" in request.args:
            ref = request.args["finding"]
            if not re.fullmatch(r"[A-Z][0-9]{2}-[1-9][0-9]*", ref) or "rev" not in args or "fact" in args:
                raise CaseError("请选择有效的底稿版本和程序发现。", 400)
            args["finding"] = ref
        if "view" in request.args:
            view = request.args["view"]
            if view not in ("replay", "execution", "warranty-register", "addendum-signing", "reinspection", "inspection", "entities", "trial", "contract-pages", "signatures", "calendar", "suppliers", "acceptance-comments", "contract-comments", "payment-acceptance", "signer-timing", "payment-proof", "contract-checks", "acceptance-checks", "payment-checks") or set(args)!={"rev"}:
                raise CaseError("请选择有效的底稿视图及版本。",400)
            args["view"] = view
        if args.get("view") == "addendum-signing" and any(len(request.args.getlist(k)) != 1 for k in ("rev","view")):
            raise CaseError("请选择一版底稿的补充协议签署凭证。",400)
        if "agreement" in request.args:
            unit = request.args["agreement"]
            if (args.get("view") != "addendum-signing" or len(request.args.getlist("agreement")) != 1
                    or not re.fullmatch(r"(?:d[0-9]{2}|unit/d[0-9]{2}/p[1-9][0-9]{0,7})",unit)):
                raise CaseError("请选择本版补充协议原件或合册页。",400)
            args["agreement"] = unit
        if "acceptance" in request.args:
            unit = request.args["acceptance"]
            if (args.get("view") != "acceptance-checks" or any(len(request.args.getlist(k)) != 1 for k in ("rev","view","acceptance"))
                    or not re.fullmatch(r"(?:d[0-9]{2}|unit/d[0-9]{2}/p[1-9][0-9]{0,7})",unit)):
                raise CaseError("请选择本版验收签认原件或合册页。",400)
            args["acceptance"] = unit
        if "call" in request.args:
            calls = request.args.getlist("call")
            if (args.get("view") != "execution" or any(len(request.args.getlist(k)) != 1 for k in ("rev","view","call"))
                    or not re.fullmatch(r"expert|d[0-9]{2,8}/p[1-9][0-9]{0,7}/(?:initial|check)", calls[0])):
                raise CaseError("请选择固定底稿中的模型调用。", 400)
            args["call"] = calls[0]
        if "ticket" in request.args:
            tickets = request.args.getlist("ticket")
            if (args.get("view") != "warranty-register" or any(len(request.args.getlist(k)) != 1 for k in ("rev", "view", "ticket"))
                    or not re.fullmatch(r"d[0-9]{2,8}", tickets[0])):
                raise CaseError("请选择固定底稿中的质保工单。", 400)
            args["ticket"] = tickets[0]
        if "stage" in request.args:
            stages = request.args.getlist("stage")
            if args.get("view") != "payment-checks" or len(stages) != 1 or not re.fullmatch(r"H0[45]-[1-9][0-9]{0,7}", stages[0]):
                raise CaseError("请选择本版的付款条件或实付时点检查。", 400)
            args["stage"] = stages[0]
        if "receipt" in request.args:
            receipt = request.args["receipt"]
            if args.get("view") not in ("payment-acceptance","signer-timing","payment-proof") or not re.fullmatch(r"H05-[1-9][0-9]{0,7}", receipt):
                raise CaseError("请选择本版的回单核对记录。",400)
            args["receipt"] = receipt
        route = ("w/"+wid+"/" if wid else "")+"case/"+case_id
        return redirect("/app#"+route+("?" + urlencode(args) if args else ""))

    @app.get("/assets/<filename>")
    def public_asset(filename):
        # Keep the published R7 URL while serving the archived JPEG page.
        mime = "image/jpeg" if filename == "showcase-acceptance-page.png" else None
        return send_from_directory(FRONTEND / "assets", filename, mimetype=mime)

    @app.get("/showcase/<filename>")
    def showcase_document(filename):
        if filename in {"signing-text.docx", "acceptance-review.docx", "contract-payment-review.docx",
                        "addendum-original-printed.docx", "addendum-original-commented.docx",
                        "acceptance-original-clean.docx", "acceptance-original-hot.docx", "acceptance-original-retest.docx"}:
            return send_file(FRONTEND / "showcase" / filename, as_attachment=True,
                             mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        if filename not in {"contract.pdf", "acceptance.pdf", "transfer.pdf", "signing-contract.pdf",
                            "inspection-contract.pdf", "inspection-acceptance.pdf", "payment-folios.pdf", "calendar-contract.pdf",
                            "signature-typeset.pdf", "signature-current.pdf", "signature-earlier.pdf",
                            "supplier-contract.pdf", "supplier-acceptance.pdf", "acceptance-review-contract.pdf", "acceptance-review-transfer.pdf",
                            "contract-payment-transfer.pdf","named-inspection-contract.pdf","named-inspection-acceptance.pdf",
                            "batch-bank-1.pdf","batch-bank-2.pdf","batch-acceptance-1.pdf","batch-acceptance-2.pdf","batch-payment-contract.pdf",
                            "batch-version-contract.pdf","batch-version-addendum.pdf","batch-version-first.pdf","batch-version-second.pdf",
                            "guarantee-period-contract.pdf","guarantee-period-guarantee.pdf","guarantee-period-receipt.pdf","guarantee-period-bank.pdf",
                            "warranty-register-contract.pdf","warranty-register-certificate.pdf","warranty-register-open.pdf",
                            "warranty-register-closed.pdf","warranty-register-bank.pdf",
                            "addendum-signing-current.pdf","addendum-signing-earlier.pdf",
                            "addendum-invoice-agreement.pdf","addendum-invoice-bank.pdf",
                            "joint-signing-contract.pdf","joint-signing-acceptance.pdf","joint-signing-transfer.pdf",
                            "acceptance-roster-contract.pdf","acceptance-roster-receipt.pdf",
                            "signer-clock-contract.pdf","signer-clock-acceptance.pdf","signer-clock-transfer.pdf","payment-execution-notice.pdf"}:
            raise CaseError("没有这份演练原件。", 404)
        return send_file(FRONTEND / "showcase" / filename, mimetype="application/pdf")

    @app.get("/<filename>")
    def asset(filename):
        if filename not in {"app.js", "team.js", "desk.js", "evidence-compare.js", "provenance.js", "supplements.js", "checkpoints.js", "peer-review.js",
                            "style.css", "brand.css", "landing.css", "landing.js"}:
            raise CaseError("资源不存在。", 404)
        return send_file(FRONTEND / filename)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", mode="ollama" if os.getenv("OLLAMA_MODEL") else "demo",
                       audit={"provider": "openai", "configured": bool(os.getenv("OPENAI_API_KEY", "").strip()), "model": MODEL,
                              "auditor_model": AUDITOR_MODEL, "profile": PROFILE, "profiles": PROFILES, "max_pages": MAX_PAGES})

    @app.get("/api/ready")
    def ready():
        if worker.thread is None or not worker.thread.is_alive():
            return jsonify(status="unavailable",component="worker"),503
        if store.waiting_for_write.is_set():
            return jsonify(status="unavailable",component="database_write"),503
        try:
            with closing(sqlite3.connect(store.path.resolve().as_uri()+"?mode=ro",uri=True,timeout=1)) as db:
                db.execute("SELECT id,rev FROM cases LIMIT 0")
        except sqlite3.Error:
            return jsonify(status="unavailable",component="database"),503
        return jsonify(status="ready",mode=app.config["AUDIT_MODE"])

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

    @business.get("/inbox")
    def ledger():
        return jsonify(inbox(store, g.workspace, g.actor["id"] if g.role == "employee" else None, request.args))

    @business.get("/evidence")
    def library():
        return jsonify(search_evidence(store, g.workspace, request.args))

    @business.post("/cases")
    @business.post("/cases/<case_id>/supplements")
    def submit(case_id=None):
        if request.mimetype != "multipart/form-data":
            raise CaseError("请以 multipart/form-data 上传资料。", 415)
        if not os.getenv("OPENAI_API_KEY"):
            raise CaseError("请配置 server/.env 中的 OPENAI_API_KEY 并重启服务。", 503)
        case_id = upload(store, g.workspace, g.actor, case_id)
        worker.wakeup.set()
        return jsonify(id=case_id), 202

    @business.get("/cases/<case_id>")
    def detail(case_id):
        data = store.detail(case_id, g.actor["id"] if g.role == "employee" else None, with_progress=True)
        if g.role == "employee":
            data["revisions"] = []
            data.pop("referrals", None)
        data["can_review"] = g.role != "employee"
        return jsonify(data)

    @business.get("/cases/<case_id>/reports/<int:rev>")
    def report(case_id, rev):
        return jsonify(store.report(case_id, rev))

    @business.post("/cases/<case_id>/reports/<int:rev>/replay")
    def replay(case_id, rev):
        if request.args or ((request.is_json or request.content_length) and json_body()):
            raise CaseError("复算使用所选底稿及服务端发布的规则版本。",400)
        version = store.report(case_id,rev)
        paper = version["report"]
        try:
            checked = replay_from_git(paper)
        except RulesUnavailable as error:
            checked = {"state":"unavailable","message":str(error)}
        return jsonify(**checked,format="fish-audit-rule-replay/v1",case_id=case_id,rev=rev,report_sha256=version["sha256"],checked_at=stamp(),
                       rule_version=paper["policy"]["version"])

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
        verify_revision_source(case_id, doc, match["sha256"])
        return verified_download(store.files / case_id / doc / ("original" + match["ext"]), match["sha256"],
                                 match["name"], "application/octet-stream", attachment=True)

    @business.get("/cases/<case_id>/documents/<doc>/pages/<int:number>/thumbnail", defaults={"thumbnail": True})
    @business.get("/cases/<case_id>/documents/<doc>/pages/<int:number>")
    def page_image(case_id, doc, number, thumbnail=False):
        with store.connect() as db:
            row = db.execute("SELECT sha256 FROM pages WHERE case_id=? AND doc=? AND number=?", (case_id, doc, number)).fetchone()
        if not row:
            raise CaseError("页图不存在。", 404)
        verify_revision_source(case_id, f"{doc}/p{number}", row["sha256"])
        path = store.files / case_id / doc / f"{number}.jpg"
        if thumbnail:
            with verified_stream(path, row["sha256"]) as stream:
                try:
                    with Image.open(stream, formats=["JPEG"]) as page:
                        page.draft("RGB", (180, 224))
                        page.thumbnail((180, 224), Image.Resampling.LANCZOS)
                        with BytesIO() as small:
                            page.convert("RGB").save(small, "JPEG", quality=78)
                            return app.response_class(small.getvalue(), mimetype="image/jpeg")
                except OSError as exc:
                    raise CaseError("存证页图无法解码，请核对原件。", 409) from exc
        return verified_download(path, row["sha256"], f"{number}.jpg", "image/jpeg", attachment=False)

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
        store.review(case_id, revision, reviewer, note, decision, facts, g.actor and g.actor["id"],
                     visibility=data.get("reference_visibility"))
        worker.wakeup.set()
        return jsonify(id=case_id), 202 if facts is not None else 200

    @business.post("/cases/<case_id>/peer-review")
    def peer_review(case_id):
        data = json_body()
        rev, report_hash, signoff_hash = (data.get(k) for k in ("rev","report_hash","signoff_hash"))
        if type(rev) is not int or not 1 <= rev <= 999_999_999 or not all(isinstance(v,str) and re.fullmatch(r"[a-f0-9]{64}",v) for v in (report_hash,signoff_hash)):
            raise CaseError("请选择已提交复核的原版底稿。", 400)
        note = text_field(data.get("note"), "复核意见", 2000)
        revision = store.resolve_referral(case_id, rev, report_hash, signoff_hash, signer(data), note,
                                          data.get("decision"), data.get("findings"), g.actor and g.actor["id"])
        return jsonify(id=case_id, rev=revision)

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
    port = int(os.getenv("PORT", "8000"))
    print(f"Fish Audit http://127.0.0.1:{port}", flush=True)
    app = create_app(store, worker)
    host = os.getenv("AUDIT_BIND", "127.0.0.1")
    origin = urlsplit(app.config["AUDIT_ORIGIN"])
    loopback = ("127.0.0.1","localhost","::1")
    if host not in loopback and (app.config["AUDIT_MODE"] != "saas" or origin.scheme != "https" or origin.hostname in loopback):
        raise SystemExit("对外监听需要 SaaS 模式与企业 HTTPS 来源。")
    worker.start()
    serve(app, host=host, port=port, threads=8,
          max_request_body_size=MAX_CASE_BYTES + 256*1024, channel_timeout=120)
