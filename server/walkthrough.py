"""Personal product walkthrough notes, separate from signed audit workpapers."""

import json
import re

from config import CaseError
from storage import encode, stamp


SCREENS = {"home", "desk", "case", "rules", "library", "team", "account"}
HOME_PARAMS = {"scene", "slip", "copy", "edition", "batch", "record", "pdf", "carrier", "term", "agreement"}
CASE_PARAMS = {"view", "stage", "instrument", "receipt", "ticket", "call", "agreement", "acceptance", "finding", "fact", "prior", "entry", "filing", "part"}
QUALITY_PIN = re.compile(r"quality-(H0[45]-[1-9][0-9]{0,7})(?:-(clause|acceptance_criteria|inspection_basis|measured_result|"
                         r"acceptance_scope|acceptance_result|accepted_on|payment_designation|transfer_status|paid_on|terms|order))?")
RETEST_PIN = re.compile(r"retest-(H05-[1-9][0-9]{0,7})(?:-(clause|citation|payment_designation|transfer_status|paid_on|terms|order|"
                        r"(?:original|final)_(?:acceptance_number|accepted_on|acceptance_result|acceptance_scope|defect_number)|"
                        r"(?:repair|final)_(?:original_acceptance|repair_number)|repair_(?:repaired_on|defect_number)|final_defect_closure))?")
USE_PIN = re.compile(r"inspection-use-(H05-[1-9][0-9]{0,7})(?:-(d[0-9]{2,8})-p([1-9][0-9]{0,7})-l([1-9][0-9]{0,7}))?")


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
        patterns.update(case_id=r"[a-f0-9]{32}", tab=r"report|evidence|graph|activity", doc=r"d[0-9]{2,8}",
                        raw_ref=r"inspection-use/d[0-9]{2,8}/p[1-9][0-9]{0,7}/l[1-9][0-9]{0,7}")
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
    params = result.get("params", {})
    anchor = result.get("anchor", "")
    if raw := result.get("raw_ref"):
        if not result.get("rev") or raw != f"inspection-use/{result.get('doc')}/p{result.get('page')}/l{result.get('line')}" or params:
            raise CaseError("请选择该版底稿中对应的付款用途原行。",400)
    if screen == "case" and anchor.startswith(("quality-H","retest-H","inspection-use-")):
        pin = QUALITY_PIN.fullmatch(anchor) or RETEST_PIN.fullmatch(anchor) or USE_PIN.fullmatch(anchor)
        if not pin or not result.get("rev") or params != {"view":"payment-checks", "stage":pin[1]}:
            raise CaseError("请选择底稿版本及相应验收款检查项。", 400)
    if screen == "case" and (params.get("view") == "board-decision" or {"filing","part"}.intersection(params)):
        if (params.get("view") != "board-decision" or not result.get("rev") or set(params)-{"view","filing","part"}
                or "filing" in params and not re.fullmatch(r"(?:d[0-9]{2,8}|unit/d[0-9]{2,8}/p[1-9][0-9]{0,7})",params["filing"])
                or params.get("part","decision") not in ("decision","signing","payments")):
            raise CaseError("请选择底稿所据的董事会审批原件与位置。",400)
    if screen == "case" and (params.get("view") == "revision-comparison" or {"prior","entry"}.intersection(params)):
        if (params.get("view") != "revision-comparison" or not re.fullmatch(r"[1-9][0-9]{0,7}", params.get("prior",""))
                or int(params["prior"]) >= result.get("rev",0) or set(params)-{"view","prior","entry"}
                or "entry" in params and not re.fullmatch(r"(?:old|new)-H0[1-7]-[1-9][0-9]{0,7}",params["entry"])):
            raise CaseError("请记录同一底稿中可定位的两版履约发现。",400)
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
        position = context.get("params",{})
        anchor = context.get("anchor","")
        use_pin = USE_PIN.fullmatch(anchor)
        if context["screen"] == "case" and (use_pin or context.get("raw_ref")):
            rows = db.execute("""SELECT json_extract(f.value,'$.id'),json_extract(f.value,'$.inspection_use.notes')
                              FROM reports, json_each(content,'$.findings') AS f WHERE case_id=? AND rev=?
                              AND json_type(f.value,'$.inspection_use.notes')='array'""",(context["case_id"],context["rev"]))
            proof = {fid: {n["row"] for n in json.loads(notes)} for fid,notes in rows}
            raw = context.get("raw_ref")
            if use_pin and use_pin[2]:
                raw = f"inspection-use/{use_pin[2]}/p{use_pin[3]}/l{use_pin[4]}"
            cited = proof.get(use_pin[1],set()) if use_pin else set().union(*proof.values())
            if not cited or raw and raw not in cited:
                raise CaseError("所选版本的付款发现没有引用该用途原行。",404)
        if context["screen"] == "case" and (pin := QUALITY_PIN.fullmatch(anchor) or RETEST_PIN.fullmatch(anchor)):
            retest = pin.re == RETEST_PIN
            row = db.execute("""SELECT json_extract(f.value,?) FROM reports, json_each(content,'$.findings') AS f
                           WHERE case_id=? AND rev=? AND json_extract(f.value,'$.id')=?""",
                             ("$.retest_reference" if retest else "$.payment_quality",context["case_id"],context["rev"],pin[1])).fetchone()
            check = json.loads(row[0]) if row and row[0] else {}
            field = pin[2]
            has_order = "days_from_final" in check if retest else bool(check.get("payment"))
            if (not check or field == "order" and not has_order or
                    check.get("state") == "unresolved" and field not in (None,"citation") or
                    field not in (None,"terms","order") and field not in check.get("fields",{})):
                raise CaseError("所选版本的这项验收款检查没有引用该位置。",404)
        if position.get("view") == "board-decision" and ("filing" in position or "part" in position):
            records = db.execute("""SELECT json_extract(f.value,'$.effect_review.board_decision.records')
                              FROM reports, json_each(content,'$.findings') AS f WHERE case_id=? AND rev=?
                              AND json_extract(f.value,'$.rule')='H01'""", (context["case_id"],context["rev"])).fetchall()
            proofs = [ref for row in records if row[0] for ref in json.loads(row[0])]
            if not proofs or "filing" in position and not any(ref.partition("/")[2] == position["filing"] for ref in proofs):
                raise CaseError("所选版本没有引用这份董事会审批原件。",404)
        if position.get("view") == "revision-comparison":
            prior = int(position["prior"])
            if not db.execute("SELECT 1 FROM reports WHERE case_id=? AND rev=?", (context["case_id"],prior)).fetchone():
                raise CaseError("未找到记录时选作对照的历史底稿。",404)
            if "entry" in position:
                side, fid = position["entry"].split("-",1)
                rev = prior if side == "old" else context["rev"]
                if not db.execute("""SELECT 1 FROM reports, json_each(reports.content,'$.findings') AS f
                             WHERE case_id=? AND rev=? AND json_extract(f.value,'$.id')=?""",(context["case_id"],rev,fid)).fetchone():
                    raise CaseError("所选版本没有这项履约发现。",404)
        if "doc" in context and not db.execute("SELECT 1 FROM pages WHERE case_id=? AND doc=? AND number=?",
                                               (context["case_id"], context["doc"], context["page"])).fetchone():
            raise CaseError("未找到记录时的资料原页。", 404)
        created = stamp()
        db.execute("INSERT INTO walkthrough_notes(workspace,author,id,created,note,context) VALUES(?,?,?,?,?,?)",
                   (*args, created, text, packed))
    return {"id": ident, "created": created, "text": text, "context": context}, 201
