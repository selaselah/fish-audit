"""Accounts, workspace memberships and revocable sessions for the hosted service."""

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid

from werkzeug.security import check_password_hash, generate_password_hash

from config import CaseError


ROLES = {"admin", "auditor", "employee"}
SESSION_SECONDS = 7 * 86400
INVITE_SECONDS = 72 * 3600
COOKIE = "fish_session"
PASSWORD_METHOD = "scrypt:32768:8:3"


def digest_token(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_for(token):
    return hmac.new(token.encode(), b"workspace-csrf-v1", hashlib.sha256).hexdigest()


def label(value, name, limit=80):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit or any(ord(c) < 32 for c in value):
        raise CaseError(f"请填写有效的{name}，最多 {limit} 字。", 400)
    return value.strip()


def login_name(value):
    name = label(value, "登录名").lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._@+-]{2,79}", name):
        raise CaseError("登录名须为 3 至 80 个字符，可使用英文字母、数字及 . _ @ + - 。", 400)
    return name


def new_id():
    return uuid.uuid4().hex


def team_event(db, workspace, actor, action, target=""):
    db.execute("INSERT INTO team_events(workspace,actor,action,target,at) VALUES(?,?,?,?,?)",
               (workspace, actor, action, target, int(time.time())))


class Directory:
    def __init__(self, store):
        self.store = store
        self.dummy_hash = generate_password_hash(secrets.token_urlsafe(32), method=PASSWORD_METHOD)
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS accounts(
                    id TEXT PRIMARY KEY, login TEXT NOT NULL UNIQUE, name TEXT NOT NULL, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workspaces(
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS members(
                    workspace TEXT NOT NULL REFERENCES workspaces(id), account TEXT NOT NULL REFERENCES accounts(id),
                    role TEXT NOT NULL CHECK(role IN ('admin','auditor','employee')), PRIMARY KEY(workspace,account));
                CREATE INDEX IF NOT EXISTS members_account ON members(account);
                CREATE TABLE IF NOT EXISTS sessions(
                    hash TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id), expires INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS sessions_expires ON sessions(expires);
                CREATE TABLE IF NOT EXISTS invitations(
                    id TEXT PRIMARY KEY, workspace TEXT NOT NULL REFERENCES workspaces(id), role TEXT NOT NULL,
                    hash TEXT UNIQUE NOT NULL, created INTEGER NOT NULL, expires INTEGER NOT NULL,
                    issued_by TEXT NOT NULL REFERENCES accounts(id), claimed_by TEXT, cancelled INTEGER);
                CREATE INDEX IF NOT EXISTS invites_space ON invitations(workspace,created);
                CREATE TABLE IF NOT EXISTS team_events(
                    seq INTEGER PRIMARY KEY, workspace TEXT NOT NULL REFERENCES workspaces(id),
                    actor TEXT NOT NULL REFERENCES accounts(id), action TEXT NOT NULL, target TEXT NOT NULL, at INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS team_events_space ON team_events(workspace,seq);
                CREATE TABLE IF NOT EXISTS auth_limits(bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, until INTEGER NOT NULL);
            """)

    def limit(self, action, key, max_attempts, seconds=900):
        now = int(time.time())
        bucket = digest_token(action + ":" + key)
        with self.store.connect(True) as db:
            db.execute("DELETE FROM auth_limits WHERE until<=?", (now,))
            row = db.execute("SELECT attempts FROM auth_limits WHERE bucket=?", (bucket,)).fetchone()
            if row and row["attempts"] >= max_attempts:
                raise CaseError("操作较频繁，请稍后重试。", 429)
            db.execute("""INSERT INTO auth_limits VALUES(?,1,?) ON CONFLICT(bucket)
                       DO UPDATE SET attempts=attempts+1""", (bucket, now + seconds))

    @staticmethod
    def _session(db, account):
        now = int(time.time())
        db.execute("DELETE FROM sessions WHERE expires<=?", (now,))
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest_token(token), account, now+SESSION_SECONDS))
        return token

    @staticmethod
    def _workspace(db, account, name):
        wid = new_id()
        db.execute("INSERT INTO workspaces VALUES(?,?,?)", (wid, name, int(time.time())))
        db.execute("INSERT INTO members VALUES(?,?,'admin')", (wid, account))
        team_event(db, wid, account, "workspace_created", name)
        return wid

    @staticmethod
    def _accept(db, account, code):
        if not isinstance(code, str) or not 20 <= len(code) <= 128:
            raise CaseError("邀请无效、已使用或已过期。", 410)
        invite = db.execute("""SELECT id,workspace,role FROM invitations WHERE hash=? AND expires>?
                            AND cancelled IS NULL AND claimed_by IS NULL""", (digest_token(code), int(time.time()))).fetchone()
        if not invite:
            raise CaseError("邀请无效、已使用或已过期。", 410)
        if db.execute("SELECT 1 FROM members WHERE workspace=? AND account=?", (invite["workspace"], account)).fetchone():
            raise CaseError("你已经是该企业的成员。", 409)
        db.execute("INSERT INTO members VALUES(?,?,?)", (invite["workspace"], account, invite["role"]))
        db.execute("UPDATE invitations SET claimed_by=? WHERE id=?", (account, invite["id"]))
        team_event(db, invite["workspace"], account, "invite_accepted", invite["role"])
        return invite["workspace"]

    def register(self, data):
        login = login_name(data.get("login"))
        name = label(data.get("name"), "显示姓名", 50)
        password = data.get("password")
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise CaseError("密码长度须为 12 至 128 个字符。", 400)
        invite = data.get("invite")
        workspace_name = None if invite else label(data.get("workspace"), "企业名称")
        password_hash = generate_password_hash(password, method=PASSWORD_METHOD)
        account = new_id()
        with self.store.connect(True) as db:
            try:
                db.execute("INSERT INTO accounts VALUES(?,?,?,?)", (account, login, name, password_hash))
            except sqlite3.IntegrityError as error:
                raise CaseError("登录名已被使用，可以直接登录。", 409) from error
            workspace = self._accept(db, account, invite) if invite else self._workspace(db, account, workspace_name)
            return self._session(db, account), workspace

    def login(self, data):
        login = login_name(data.get("login"))
        password = data.get("password")
        if not isinstance(password, str) or not 1 <= len(password) <= 128:
            raise CaseError("登录名或密码有误。", 401)
        with self.store.connect() as db:
            user = db.execute("SELECT id,password_hash FROM accounts WHERE login=?", (login,)).fetchone()
        if not check_password_hash(user["password_hash"] if user else self.dummy_hash, password) or not user:
            raise CaseError("登录名或密码有误。", 401)
        with self.store.connect(True) as db:
            return self._session(db, user["id"])

    def user(self, token):
        if not token or len(token) > 128:
            return None
        with self.store.connect() as db:
            row = db.execute("""SELECT a.id,a.name,a.login FROM accounts a JOIN sessions s ON a.id=s.account
                             WHERE s.hash=? AND s.expires>?""", (digest_token(token), int(time.time()))).fetchone()
            return dict(row) if row else None

    def spaces(self, account):
        with self.store.connect() as db:
            rows = db.execute("""SELECT w.id,w.name,m.role FROM workspaces w JOIN members m ON m.workspace=w.id
                              WHERE m.account=? ORDER BY w.created,w.name,w.id""", (account,))
            return [dict(row) for row in rows]

    def member(self, account, workspace):
        with self.store.connect() as db:
            row = db.execute("SELECT role FROM members WHERE workspace=? AND account=?", (workspace,account)).fetchone()
        if not row:
            raise CaseError("未找到该企业工作区。", 404)
        return row["role"]

    def logout(self, token):
        with self.store.connect(True) as db:
            db.execute("DELETE FROM sessions WHERE hash=?", (digest_token(token),))

    def create_workspace(self, account, name):
        with self.store.connect(True) as db:
            return self._workspace(db, account, label(name, "企业名称"))

    def accept(self, account, code):
        with self.store.connect(True) as db:
            return self._accept(db, account, code)

    @staticmethod
    def _admin(db, workspace, actor):
        row = db.execute("SELECT role FROM members WHERE workspace=? AND account=?", (workspace,actor)).fetchone()
        if not row or row["role"] != "admin":
            raise CaseError("此操作需要企业管理员权限。", 403)

    def team(self, workspace, actor):
        with self.store.connect() as db:
            db.execute("BEGIN")
            self._admin(db, workspace, actor)
            members = db.execute("""SELECT a.id,a.name,a.login,m.role FROM accounts a JOIN members m ON m.account=a.id
                                 WHERE m.workspace=? ORDER BY a.name,a.login""", (workspace,)).fetchall()
            invites = db.execute("""SELECT id,role,expires FROM invitations WHERE workspace=? AND expires>?
                                AND claimed_by IS NULL AND cancelled IS NULL ORDER BY created DESC""",
                                 (workspace,int(time.time()))).fetchall()
            events = db.execute("""SELECT e.at,e.action,e.target,a.name AS actor FROM team_events e JOIN accounts a ON a.id=e.actor
                                WHERE e.workspace=? ORDER BY e.seq DESC LIMIT 50""", (workspace,)).fetchall()
            return {"members":[dict(row) for row in members], "invites":[dict(row) for row in invites],
                    "events":[dict(row) for row in events]}

    def invite(self, workspace, actor, role):
        if role not in ("auditor", "employee"):
            raise CaseError("请选择审计人员或员工。", 400)
        now = int(time.time())
        code = secrets.token_urlsafe(28)
        invite_id = new_id()
        with self.store.connect(True) as db:
            self._admin(db, workspace, actor)
            db.execute("""INSERT INTO invitations(id,workspace,role,hash,created,expires,issued_by)
                       VALUES(?,?,?,?,?,?,?)""", (invite_id,workspace,role,digest_token(code),now,now+INVITE_SECONDS,actor))
            team_event(db, workspace, actor, "invite_created", role)
        return {"id":invite_id,"token":code,"expires":now+INVITE_SECONDS,"role":role}

    def cancel(self, workspace, actor, invite):
        with self.store.connect(True) as db:
            self._admin(db, workspace, actor)
            update = db.execute("""UPDATE invitations SET cancelled=? WHERE workspace=? AND id=?
                                AND cancelled IS NULL AND claimed_by IS NULL""", (int(time.time()),workspace,invite))
            if update.rowcount != 1:
                raise CaseError("未找到待使用的邀请。", 404)
            team_event(db, workspace, actor, "invite_cancelled", invite)

    def change_member(self, workspace, actor, target, role):
        if role not in ("admin","auditor","employee","remove"):
            raise CaseError("无效的成员角色。", 400)
        with self.store.connect(True) as db:
            self._admin(db, workspace, actor)
            row = db.execute("""SELECT m.role,a.login FROM members m JOIN accounts a ON a.id=m.account
                             WHERE m.workspace=? AND m.account=?""",(workspace,target)).fetchone()
            if not row:
                raise CaseError("未找到该企业成员。", 404)
            if row["role"] == "admin" and role != "admin" and db.execute(
                    "SELECT count(*) FROM members WHERE workspace=? AND role='admin'", (workspace,)).fetchone()[0] == 1:
                raise CaseError("企业须保留至少一名管理员。", 409)
            if role == "remove":
                db.execute("DELETE FROM members WHERE workspace=? AND account=?", (workspace,target))
            else:
                db.execute("UPDATE members SET role=? WHERE workspace=? AND account=?", (role,workspace,target))
            team_event(db, workspace, actor, "member_changed", row["login"]+" · "+role)
