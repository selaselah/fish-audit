import hmac
import os
from urllib.parse import urlsplit

from flask import g, jsonify, request

from config import CaseError
from identity import COOKIE, SESSION_SECONDS, Directory, csrf_for, login_name


def configure_access(app, store, json_body):
    mode = os.getenv("AUDIT_ACCESS_MODE", "local")
    if mode not in ("local", "saas"):
        raise ValueError("AUDIT_ACCESS_MODE 仅支持 local 或 saas")
    origin = os.getenv("AUDIT_PUBLIC_ORIGIN", "").strip().rstrip("/")
    local_hosts = ["127.0.0.1", "localhost", "[::1]"]
    if origin:
        target = urlsplit(origin)
        if (mode != "saas" or not target.hostname or target.username or target.password or target.path
                or target.query or target.fragment or target.scheme not in ("http","https")
                or (target.scheme != "https" and target.hostname not in ("localhost","127.0.0.1","::1"))):
            raise ValueError("托管域名需要 SaaS 模式和有效的 HTTPS 来源，本机调试可使用 HTTP")
        app.config["TRUSTED_HOSTS"] = [target.hostname if target.hostname != "::1" else "[::1]"]
    else:
        app.config["TRUSTED_HOSTS"] = local_hosts
    directory = Directory(store)
    app.config.update(AUDIT_MODE=mode, AUDIT_ORIGIN=origin)
    app.extensions["directory"] = directory

    @app.before_request
    def establish_identity():
        if not request.path.startswith("/api/"):
            return
        token = request.cookies.get(COOKIE, "")
        g.user = directory.user(token)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            source = request.headers.get("Origin")
            if ((source is not None and source != (origin or request.host_url.rstrip("/")))
                    or request.headers.get("Sec-Fetch-Site") == "cross-site"):
                raise CaseError("请从本服务的工作台提交。", 403)
            account_route = request.path.startswith(("/api/auth/","/api/workspaces","/api/w/"))
            if account_route and g.user and not hmac.compare_digest(
                    request.headers.get("X-CSRF-Token","").encode(), csrf_for(token).encode()):
                raise CaseError("会话校验已更新，请刷新后重试。", 403)

    def signed_in():
        if not g.user:
            raise CaseError("请先登录企业工作区。", 401)
        return g.user["id"]

    def session_info(user, token):
        return {"mode":mode, "user":user, "workspaces":directory.spaces(user["id"]) if user else [],
                "csrf":csrf_for(token) if user else None}

    def start_session(token, selected=None):
        old = request.cookies.get(COOKIE)
        if old:
            directory.logout(old)
        response = jsonify(**session_info(directory.user(token), token), selected=selected)
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="Lax",
                            secure=origin.startswith("https://") or request.is_secure, path="/")
        return response

    @app.get("/api/session")
    def session_state():
        return jsonify(session_info(g.user, request.cookies.get(COOKIE,"")))

    @app.post("/api/auth/register")
    def register():
        directory.limit("register", request.remote_addr or "local", 12, 3600)
        token, selected = directory.register(json_body())
        return start_session(token, selected), 201

    @app.post("/api/auth/login")
    def login():
        data = json_body()
        directory.limit("login-client", request.remote_addr or "local", 100)
        directory.limit("login-name", login_name(data.get("login")), 20)
        return start_session(directory.login(data))

    @app.post("/api/auth/logout")
    def logout():
        token = request.cookies.get(COOKIE)
        if token:
            directory.logout(token)
        response = jsonify(ok=True)
        response.delete_cookie(COOKIE, path="/", httponly=True, samesite="Lax",
                               secure=origin.startswith("https://") or request.is_secure)
        return response

    @app.post("/api/workspaces")
    def create_workspace():
        account = signed_in()
        directory.limit("new-workspace", account, 10, 86400)
        selected = directory.create_workspace(account, json_body().get("name"))
        return jsonify(selected=selected, workspaces=directory.spaces(account)), 201

    @app.post("/api/workspaces/join")
    def join_workspace():
        account = signed_in()
        directory.limit("join", account, 30)
        selected = directory.accept(account, json_body().get("invite"))
        return jsonify(selected=selected, workspaces=directory.spaces(account))

    @app.get("/api/workspaces/<wid>/team")
    def team(wid):
        return jsonify(directory.team(wid, signed_in()))

    @app.post("/api/workspaces/<wid>/invites")
    def invite(wid):
        return jsonify(directory.invite(wid, signed_in(), json_body().get("role"))), 201

    @app.post("/api/workspaces/<wid>/invites/<invite_id>/cancel")
    def cancel_invite(wid, invite_id):
        directory.cancel(wid, signed_in(), invite_id)
        return jsonify(ok=True)

    @app.post("/api/workspaces/<wid>/members/<target>")
    def change_member(wid, target):
        directory.change_member(wid, signed_in(), target, json_body().get("role"))
        return jsonify(ok=True)

    return directory
