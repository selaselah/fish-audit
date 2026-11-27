"""Personal product walkthrough notes, separate from signed audit workpapers."""

import json
import re

from config import CaseError
from storage import encode, stamp


SCREENS = {"home", "desk", "case", "rules", "library", "team", "account"}
HOME_PARAMS = {"scene", "slip", "copy", "edition", "batch", "record", "pdf", "carrier", "term", "agreement"}
CASE_PARAMS = {"view", "stage", "instrument", "receipt", "ticket", "call", "agreement", "acceptance", "finding", "fact"}


def check_context(value):
    if not isinstance(value, dict) or not isinstance(value.get("screen"), str) or value["screen"] not in SCREENS:
        raise CaseError("走查页面无效。", 400)
    screen = value["screen"]
    patterns = {"anchor": r"[a-zA-Z][a-zA-Z0-9_-]{0,95}", "dialog": r"[a-z][a-z0-9-]{0,40}"}
    if screen == "home":
        patterns["section"] = r"main|sample|payments|workflow|start"
    if screen == "desk":
        patterns["intake"] = r"contract|purchase|travel|payment"
    if screen == "case":
        patterns.update(case_id=r"[a-f0-9]{32}", tab=r"report|evidence|graph|activity", doc=r"d[0-9]{2,8}")
        if "case_id" not in value:
            raise CaseError("走查底稿编号缺失。", 400)
    result = {"screen": screen}
    for key, item in value.items():
        if key == "screen":
            continue
        if (key == "target" or (screen == "home" and key == "example")) and isinstance(item, str) and 0 < len(item) <= 96 and item.isprintable():
            result[key] = item
        elif key in patterns and isinstance(item, str) and re.fullmatch(patterns[key], item):
            result[key] = item
        elif screen == "case" and key in {"rev", "page", "line"} and type(item) is int and 1 <= item <= 99999999:
            result[key] = item
        elif key == "params" and screen in {"case", "home"} and isinstance(item, dict):
            allowed = CASE_PARAMS if screen == "case" else HOME_PARAMS
            if any(k not in allowed or not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_/-]{0,79}", v) for k, v in item.items()):
                raise CaseError("走查定位参数无效。", 400)
            result[key] = item
        else:
            raise CaseError("走查位置无效。", 400)
    if ("doc" in result) != ("page" in result) or ("line" in result and "page" not in result):
        raise CaseError("走查原页位置不完整。", 400)
    return result


def note_row(row):
    return {"id": row["id"], "created": row["created"], "text": row["note"], "context": json.loads(row["context"])}


def list_notes(store, workspace, author):
    with store.connect() as db:
        rows = db.execute("SELECT * FROM walkthrough_notes WHERE workspace=? AND author=? ORDER BY created DESC,id DESC", (workspace, author))
        return [note_row(row) for row in rows]


def save_note(store, workspace, author, role, data):
    ident, text = data.get("id"), data.get("text")
    if not isinstance(ident, str) or not re.fullmatch(r"[a-f0-9]{32}", ident):
        raise CaseError("走查记录编号无效。", 400)
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000 or any(ord(ch) < 32 and ch not in "\r\n\t" for ch in text):
        raise CaseError("请填写 1 到 2000 字的修改意见。", 400)
    text = text.strip()
    context = check_context(data.get("context"))
    if "case_id" in context:
        store.require_case(context["case_id"], workspace, author if role == "employee" else None)
        if "rev" in context and role == "employee":
            raise CaseError("查看底稿版本需要审计权限。", 403)
    args = (workspace, author, ident)
    packed = encode(context)
    with store.connect(write=True) as db:
        existing = db.execute("SELECT * FROM walkthrough_notes WHERE workspace=? AND author=? AND id=?", args).fetchone()
        if existing:
            if existing["note"] != text or existing["context"] != packed:
                raise CaseError("此编号已有另一条走查意见。", 409)
            return note_row(existing), 200
        if "rev" in context and not db.execute("SELECT 1 FROM reports WHERE case_id=? AND rev=?",
                                               (context["case_id"], context["rev"])).fetchone():
            raise CaseError("未找到记录时的底稿版本。", 404)
        if "doc" in context and not db.execute("SELECT 1 FROM pages WHERE case_id=? AND doc=? AND number=?",
                                               (context["case_id"], context["doc"], context["page"])).fetchone():
            raise CaseError("未找到记录时的资料原页。", 404)
        created = stamp()
        db.execute("INSERT INTO walkthrough_notes(workspace,author,id,created,note,context) VALUES(?,?,?,?,?,?)",
                   (*args, created, text, packed))
    return {"id": ident, "created": created, "text": text, "context": context}, 201
