"""Personal product walkthrough notes, separate from signed audit workpapers."""

import json
import re

from config import CaseError
from payment_quality import FORMAT as QUALITY_FORMAT, OPEN_FORMAT
from storage import encode, stamp


SCREENS = {"home", "desk", "case", "rules", "library", "team", "account"}
HOME_PARAMS = {"scene", "slip", "copy", "edition", "batch", "record", "pdf", "carrier", "term", "agreement"}
CASE_PARAMS = {"view", "stage", "instrument", "receipt", "ticket", "call", "agreement", "acceptance", "finding", "fact", "prior", "entry", "filing", "part"}
READING_LOCATION = r"reading-d[0-9]{2,8}-p[1-9][0-9]{0,7}-l[1-9][0-9]{0,7}"
FORM_PIN = re.compile(r"form-(H0[1245]-[1-9][0-9]{0,7})-(d[0-9]{2,8})-p([1-9][0-9]{0,7})-l([1-9][0-9]{0,7})")
ACCEPTANCE_LINE_PIN = re.compile(r"(?:number|serial)-(H0[245]-[1-9][0-9]{0,7})-(d[0-9]{2,8})-p([1-9][0-9]{0,7})-l([1-9][0-9]{0,7})")
QUALITY_PIN = re.compile(r"quality-(H0[45]-[1-9][0-9]{0,7})(?:-(clause|acceptance_criteria|inspection_basis|measured_result|"
                         r"acceptance_scope|acceptance_result|accepted_on|payment_designation|transfer_status|paid_on|terms|order|"+READING_LOCATION+r"))?")
LIMIT_PIN = re.compile(r"limits-(H02-[1-9][0-9]{0,7})(?:-(acceptance_criteria|inspection_basis|measured_result|acceptance_result|"+READING_LOCATION+r"))?")
RETEST_PIN = re.compile(r"retest-(H05-[1-9][0-9]{0,7})(?:-(clause|citation|payment_designation|transfer_status|paid_on|terms|order|schedule|"
                        r"(?:original|final)_(?:acceptance_number|accepted_on|acceptance_result|acceptance_scope|defect_number)|"
                        r"(?:repair|final)_(?:original_acceptance|repair_number)|repair_(?:repaired_on|defect_number)|final_defect_closure))?")
USE_PIN = re.compile(r"(?:inspection-use|payment-approval|payment-clock|contract-approver)-(H05-[1-9][0-9]{0,7})(?:-(d[0-9]{2,8})-p([1-9][0-9]{0,7})-l([1-9][0-9]{0,7}))?")
CHANGE_PIN = re.compile(r"approver-change-(H0[45]-[1-9][0-9]{0,7})(?:-(approval-change|contract-approver|payment-approval|payment-clock|inspection-use)-(d[0-9]{2,8})-p([1-9][0-9]{0,7})-l([1-9][0-9]{0,7}))?")
PARTY_PIN = re.compile(r"party-reading-(d[0-9]{2,8})-p1-(f[1-9][0-9]{0,7})")
COUNT_PIN = re.compile(r"installment-count-(H0[3456]-[1-9][0-9]{0,7})")


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
                        raw_ref=r"(?:inspection-use|payment-approval|payment-clock|contract-approver|approval-change|installment-count|measurement-note|contract-signing-form|measurement-number|inspection-line)/d[0-9]{2,8}/p[1-9][0-9]{0,7}/l[1-9][0-9]{0,7}")
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
        elif screen == "case" and key == "page_point":
            if (not isinstance(item, dict) or set(item) != {"x", "y", "page_sha256"}
                    or any(type(item[k]) is not int or not 0 <= item[k] <= 10000 for k in ("x", "y"))
                    or not isinstance(item["page_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["page_sha256"])):
                raise CaseError("原图标记需要有效的位置及页图摘要。", 400)
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
    if params.get("view")=="contract-signing-form" and (not result.get("rev") or set(params)!={"view"}):
        raise CaseError("请选择一版合同签署底稿。",400)
    if anchor.startswith(("form-H","number-H","serial-H")):
        pin = FORM_PIN.fullmatch(anchor) or ACCEPTANCE_LINE_PIN.fullmatch(anchor)
        view = pin and {"H01":"contract-signing-form","H02":"acceptance-checks"}.get(pin[1][:3])
        if (not pin or screen!="case" or not result.get("rev") or result.get("tab","report")!="report"
                or {"doc","dialog"}.intersection(result) or params != (
                    {"view":view} if view else {"view":"payment-checks","stage":pin[1]})):
            raise CaseError("请选择该版底稿在当前检查项引用的原行。",400)
    if anchor.startswith("limits-H"):
        pin = LIMIT_PIN.fullmatch(anchor)
        if not pin or screen!="case" or not result.get("rev") or params!={"view":"acceptance-limits"}:
            raise CaseError("请选择该版底稿中相应的验收限值。",400)
    if "page_point" in result and (not result.get("rev") or not result.get("doc") or result.get("dialog") != "page-dialog"
                                   or params or {"line", "raw_ref", "anchor"}.intersection(result)):
        raise CaseError("请在选定版本的资料原页上标记位置。", 400)
    if anchor.startswith("party-reading-"):
        pin = PARTY_PIN.fullmatch(anchor)
        if (not pin or screen!="case" or not result.get("rev") or result.get("dialog")!="page-dialog"
                or (result.get("doc"),result.get("page"))!=(pin[1],1) or not result.get("line")
                or params!={"fact":f"{pin[1]}/p1/{pin[2]}"}):
            raise CaseError("请选择该版原页中的主体核字位置。",400)
    if raw := result.get("raw_ref"):
        if (not result.get("rev") or raw.partition("/")[2] != f"{result.get('doc')}/p{result.get('page')}/l{result.get('line')}" or params
                or raw.startswith(("contract-signing-form/","measurement-number/","inspection-line/")) and result.get("dialog")!="page-dialog"):
            raise CaseError("请选择该版底稿所引的原件页和行。",400)
    if screen == "case" and anchor.startswith(("quality-H","retest-H","inspection-use-","payment-approval-","payment-clock-","contract-approver-","approver-change-","installment-count-")):
        pin = QUALITY_PIN.fullmatch(anchor) or RETEST_PIN.fullmatch(anchor) or USE_PIN.fullmatch(anchor) or CHANGE_PIN.fullmatch(anchor) or COUNT_PIN.fullmatch(anchor)
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
        if point := context.get("page_point"):
            page = db.execute("""SELECT json_extract(n.value,'$.sha256'), p.sha256
                FROM reports r JOIN pages p ON p.case_id=r.case_id, json_each(r.content,'$.graph.nodes') n
                WHERE r.case_id=? AND r.rev=? AND p.doc=? AND p.number=?
                AND json_extract(n.value,'$.type')='page' AND json_extract(n.value,'$.id')=p.doc||'/p'||p.number""",
                (context["case_id"], context["rev"], context["doc"], context["page"])).fetchone()
            if not page:
                raise CaseError("这版底稿中没有所标记的原页。", 404)
            if not page[0] == page[1] == point["page_sha256"]:
                raise CaseError("原图标记与这版底稿的页图摘要不符。", 409)
        position = context.get("params",{})
        anchor = context.get("anchor","")
        if PARTY_PIN.fullmatch(anchor):
            linked = db.execute("""SELECT 1 FROM reports, json_each(content,'$.graph.reviewed_party_lines.rows') AS r
                    WHERE case_id=? AND rev=? AND json_extract(content,'$.policy.party_readings')='reviewed-party-line-v1'
                    AND json_extract(r.value,'$.model_ref')=? AND json_extract(r.value,'$.id')=?
                    AND json_extract(r.value,'$.doc')=? AND json_extract(r.value,'$.page')=? AND json_extract(r.value,'$.line')=?
                    AND json_array_length(r.value,'$.rects')>0""",
                    (context["case_id"],context["rev"],position["fact"],f"party-line/{context['doc']}/p1/l{context['line']}",
                     context["doc"],context["page"],context["line"])).fetchone()
            if not linked:
                raise CaseError("所选版本没有引用这个主体字段和原件行。",404)
        use_pin = USE_PIN.fullmatch(anchor)
        change_pin=CHANGE_PIN.fullmatch(anchor)
        count_pin=COUNT_PIN.fullmatch(anchor)
        count_raw=context.get("raw_ref","").startswith("installment-count/")
        if context["screen"]=="case" and (count_pin or count_raw):
            finding=count_pin[1] if count_pin else None
            raw=context.get("raw_ref")
            linked=db.execute("""SELECT 1 FROM reports,json_each(content,'$.findings') f,json_each(content,'$.graph.installment_count_sources.rows') r
                WHERE case_id=? AND rev=? AND json_extract(content,'$.policy.installment_count')='printed-installment-count-v1'
                AND json_extract(f.value,'$.installment_count')=json_extract(r.value,'$.id') AND json_array_length(r.value,'$.rects')>0
                AND (? IS NULL OR json_extract(f.value,'$.id')=?) AND (? IS NULL OR json_extract(r.value,'$.id')=?)""",
                (context["case_id"],context["rev"],finding,finding,raw,raw)).fetchone()
            if not linked:
                raise CaseError("所选底稿没有引用这条合同分期总述。",404)
        elif context["screen"]=="case" and (FORM_PIN.fullmatch(anchor) or context.get("raw_ref","").startswith("contract-signing-form/")):
            form = FORM_PIN.fullmatch(anchor)
            doc, page, line = (form[2],int(form[3]),int(form[4])) if form else (context["doc"],context["page"],context["line"])
            ref = f"contract-signing-form/{doc}/p{page}/l{line}"
            linked = db.execute("""SELECT 1 FROM reports,json_each(content,'$.findings') f,
                json_each(f.value,'$.evidence') e,json_each(content,'$.graph.contract_effect_sources.conditions') r,
                json_each(content,'$.calls.pages') p WHERE case_id=? AND rev=?
                AND json_extract(content,'$.policy.contract_effect') IN ('contract-effect-sources-v8','contract-effect-sources-v9')
                AND e.value=? AND json_extract(r.value,'$.id')=e.value AND json_extract(r.value,'$.kind')='signing_form'
                AND (json_extract(f.value,'$.rule') IN ('H01','H04','H05') OR (
                    json_extract(f.value,'$.rule')='H02' AND json_extract(content,'$.policy.contract_effect')='contract-effect-sources-v9'
                    AND json_extract(r.value,'$.applies_to')=json_array('contract','acceptance')
                    AND EXISTS (SELECT 1 FROM json_each(f.value,'$.acceptance_signing_requirements') a WHERE a.value=e.value)))
                AND ((? IS NULL AND json_extract(f.value,'$.rule')='H01') OR json_extract(f.value,'$.id')=?)
                AND json_extract(p.value,'$.doc')=? AND json_extract(p.value,'$.page')=? AND json_array_length(p.value,?)>0""",
                (context["case_id"],context["rev"],ref,form[1] if form else None,form[1] if form else None,
                 doc,page,f'$.contract_signing_form_rects."{line}"')).fetchone()
            if not linked:
                raise CaseError("所选底稿没有引用这条合同签署要求。",404)
        elif context["screen"]=="case" and (ACCEPTANCE_LINE_PIN.fullmatch(anchor) or context.get("raw_ref","").startswith(("measurement-number/","inspection-line/"))):
            pin = ACCEPTANCE_LINE_PIN.fullmatch(anchor)
            doc,page,line = pin.groups()[1:] if pin else (context["doc"],context["page"],context["line"])
            serial = anchor.startswith("serial-") or context.get("raw_ref","").startswith("inspection-line/")
            if serial:
                prefix, finding_key, ledger, marker, version, rects = ("inspection-line","delivery_register",
                    "inspection_coverage_sources","inspection_coverage","inspection-coverage-v3","delivery_register_rects")
            else:
                prefix, finding_key, ledger, marker, version, rects = ("measurement-number","measurement_numbers",
                    "measurement_number_sources","measurement_numbers","printed-measurement-spacing-v1","measurement_number_rects")
            ref = f"{prefix}/{doc}/p{page}/l{line}"
            linked = db.execute("""SELECT 1 FROM reports,json_each(content,'$.findings') f,
                json_each(f.value,?) n,json_each(content,?) r,
                json_each(content,'$.calls.pages') p WHERE case_id=? AND rev=?
                AND json_extract(content,?)=? AND (?=0 OR json_extract(content,'$.graph.inspection_coverage_sources.purpose')='delivery_register')
                AND n.value=? AND json_extract(r.value,'$.id')=n.value
                AND EXISTS (SELECT 1 FROM json_each(f.value,'$.evidence') e WHERE e.value=n.value)
                AND ((? IS NULL AND json_extract(f.value,'$.rule')='H02') OR json_extract(f.value,'$.id')=?)
                AND json_extract(r.value,'$.doc')=? AND json_extract(r.value,'$.page')=? AND json_extract(r.value,'$.line')=?
                AND json_extract(p.value,'$.doc')=? AND json_extract(p.value,'$.page')=? AND json_array_length(p.value,?)>0""",
                ("$."+finding_key,"$.graph."+ledger+".rows",context["case_id"],context["rev"],"$.policy."+marker,version,int(serial),
                 ref,pin[1] if pin else None,pin[1] if pin else None,doc,int(page),int(line),doc,int(page),f'$.{rects}."{line}"')).fetchone()
            if not linked:
                raise CaseError("所选底稿没有引用这条验收原行。",404)
        elif context["screen"]=="case" and context.get("raw_ref","").startswith("measurement-note/"):
            linked=db.execute("""SELECT 1 FROM reports,json_each(content,'$.findings') f,
                json_each(COALESCE(json_extract(f.value,'$.quality_comparison.reading_notes'),json_extract(f.value,'$.reading_caveats'))) n,
                json_each(content,'$.calls.pages') p
                WHERE case_id=? AND rev=? AND json_extract(content,'$.policy.payment_quality') IN (?,?)
                AND json_extract(f.value,'$.rule')='H02' AND json_extract(n.value,'$.doc')=? AND json_extract(n.value,'$.page')=?
                AND json_extract(n.value,'$.line')=? AND json_extract(p.value,'$.doc')=json_extract(n.value,'$.doc')
                AND json_extract(p.value,'$.page')=json_extract(n.value,'$.page') AND json_array_length(p.value,?)>0""",
                (context["case_id"],context["rev"],OPEN_FORMAT,QUALITY_FORMAT,context["doc"],context["page"],context["line"],
                 f'$.measurement_note_rects."{context["line"]}"')).fetchone()
            if not linked:
                raise CaseError("所选版本没有可定位的测量精度说明原行。",404)
        elif context["screen"] == "case" and (use_pin or change_pin or context.get("raw_ref")):
            rows = db.execute("""SELECT json_extract(f.value,'$.id'),json_extract(f.value,'$.inspection_use.notes'),
                              json_extract(f.value,'$.inspection_use.approval.rows'),json_extract(f.value,'$.inspection_use.approval.clock.rows'),
                              json_extract(f.value,'$.inspection_use.approval.names.rows')
                              FROM reports, json_each(content,'$.findings') AS f WHERE case_id=? AND rev=?
                              AND json_type(f.value,'$.inspection_use.notes')='array'""",(context["case_id"],context["rev"]))
            proof = {}
            sections = set()
            for fid,notes,approval,clocks,terms in rows:
                proof[fid] = {n["row"] for n in json.loads(notes)}
                sections.add(("inspection-use",fid))
                if approval is not None:
                    proof[fid].update(json.loads(approval))
                    sections.add(("payment-approval",fid))
                if clocks is not None:
                    proof[fid].update(json.loads(clocks))
                    sections.add(("payment-clock",fid))
                if terms is not None:
                    proof[fid].update(json.loads(terms))
                    sections.add(("contract-approver",fid))
            raw = context.get("raw_ref")
            prefix = anchor.partition("-H05-")[0]
            if use_pin and use_pin[2]:
                raw = f"{prefix}/{use_pin[2]}/p{use_pin[3]}/l{use_pin[4]}"
            cited = proof.get(use_pin[1],set()) if use_pin else set().union(*proof.values())
            if change_pin:
                if change_pin[2]:raw=f"{change_pin[2]}/{change_pin[3]}/p{change_pin[4]}/l{change_pin[5]}"
            if not use_pin and (change_pin or raw and raw not in cited):
                permitted=db.execute("""SELECT json_extract(f.value,'$.approval_change.evidence') FROM reports,json_each(content,'$.findings') f
                    WHERE case_id=? AND rev=? AND json_type(f.value,'$.approval_change')='object' AND (? IS NULL OR json_extract(f.value,'$.id')=?)
                    AND json_extract(content,'$.policy.inspection_use') IN ('cited-inspection-payment-use-v7','cited-inspection-payment-use-v8','cited-inspection-payment-use-v9')""",
                    (context["case_id"],context["rev"],change_pin[1] if change_pin else None,change_pin[1] if change_pin else None)).fetchall()
                change_refs={ref for item in permitted for ref in json.loads(item[0])}
                if change_pin and (not permitted or raw and raw not in change_refs):
                    raise CaseError("所选版本的签批人变更核对没有引用该位置。",404)
                cited.update(change_refs)
            if not use_pin and not change_pin and raw and raw.startswith("contract-approver/") and raw not in cited:
                stage=db.execute("""SELECT 1 FROM reports,json_each(content,'$.findings') f,
                    json_each(f.value,'$.evidence') e WHERE case_id=? AND rev=? AND e.value=?
                    AND json_extract(f.value,'$.rule') IN ('H03','H04','H05')
                    AND json_extract(content,'$.policy.inspection_use') IN ('cited-inspection-payment-use-v5','cited-inspection-payment-use-v6','cited-inspection-payment-use-v7','cited-inspection-payment-use-v8','cited-inspection-payment-use-v9')""",
                    (context["case_id"],context["rev"],raw)).fetchone()
                if stage:
                    cited.add(raw)
            if use_pin and (prefix,use_pin[1]) not in sections or raw and raw not in cited:
                raise CaseError("所选版本的付款发现没有引用该用途原行。",404)
            if context.get("raw_ref") or change_pin and raw:
                location = db.execute("""WITH paper AS (SELECT content FROM reports WHERE case_id=? AND rev=?),
                    lines AS (SELECT r.value AS line FROM paper,json_each(content,'$.graph.inspection_use_sources.rows') r
                        UNION ALL SELECT r.value FROM paper,json_each(content,'$.graph.inspection_use_sources.approvals') p,
                        json_each(p.value,'$.rows') r
                        UNION ALL SELECT r.value FROM paper,json_each(content,'$.graph.inspection_use_sources.bank_clocks') p,
                        json_each(p.value,'$.rows') r
                        UNION ALL SELECT r.value FROM paper,json_each(content,'$.graph.inspection_use_sources.approver_terms') p,
                        json_each(p.value,'$.rows') r
                        UNION ALL SELECT r.value FROM paper,json_each(content,'$.graph.inspection_use_sources.approver_changes') p,
                        json_each(p.value,'$.rows') r)
                    SELECT 1 FROM lines WHERE json_extract(line,'$.id')=? AND json_array_length(line,'$.rects')>0""",
                    (context["case_id"],context["rev"],raw)).fetchone()
                if not location:
                    raise CaseError("所选版本没有可定位的付款依据行框。",404)
        if context["screen"] == "case" and (pin := QUALITY_PIN.fullmatch(anchor) or RETEST_PIN.fullmatch(anchor) or LIMIT_PIN.fullmatch(anchor)):
            retest = pin.re == RETEST_PIN
            path = "$.quality_comparison" if pin.re==LIMIT_PIN else ("$.retest_reference" if retest else "$.payment_quality")
            row = db.execute("""SELECT json_extract(f.value,?),json_extract(f.value,'$.reading_caveats') FROM reports, json_each(content,'$.findings') AS f
                           WHERE case_id=? AND rev=? AND json_extract(f.value,'$.id')=?""",
                             (path,context["case_id"],context["rev"],pin[1])).fetchone()
            check = json.loads(row[0]) if row and row[0] else {}
            if not check and pin.re==LIMIT_PIN and row and row[1]:
                check = {"reading_notes":json.loads(row[1])}
            field = pin[2]
            has_order = "days_from_final" in check if retest else bool(check.get("payment"))
            note_pin = field and field.startswith("reading-")
            if note_pin:
                proof = check if pin.re==LIMIT_PIN else check.get("comparison",{})
                if not any(field==f"reading-{n['doc']}-p{n['page']}-l{n['line']}" for n in proof.get("reading_notes",())):
                    raise CaseError("所选版本没有引用该行测量精度说明。",404)
            if field == "schedule":
                schedule = check.get("schedule_review") or {}
                plan = db.execute("""SELECT json_extract(f.value,'$.evidence') FROM reports, json_each(content,'$.findings') f
                          WHERE case_id=? AND rev=? AND json_extract(content,'$.policy.retest_reference')=?
                          AND json_extract(f.value,'$.rule')='H03' AND json_extract(f.value,'$.status')='missing'""",
                                  (context["case_id"],context["rev"],check.get("format"))).fetchone()
                refs = [schedule.get("header"), *schedule.get("clauses",[])]
                if (not plan or check.get("format") != "reinspection-receipt-reference-v2"
                        or check.get("fields",{}).get("clause") not in refs[1:]
                        or not set(refs) <= set(check.get("evidence",[])) & set(json.loads(plan[0]))):
                    raise CaseError("所选版本没有对应的分期安排待核记录。",404)
            if (not check or field == "order" and not has_order or
                    check.get("state") == "unresolved" and field not in (None,"citation") or
                    not note_pin and field not in (None,"terms","order","schedule") and field not in check.get("fields",{})):
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
