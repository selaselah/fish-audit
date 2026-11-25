"""Trace a failed acceptance through one identified defect, repair and signed final reinspection."""

import hashlib
import re
import unicodedata


LABELS = {
    "acceptance_number": ("验收单编号", "验收报告编号", "复验单编号", "复验报告编号"),
    "original_acceptance": ("原验收单编号", "原验收报告编号"),
    "defect_number": ("缺陷编号", "问题单编号"),
    "repair_number": ("整改记录编号", "整改单编号"),
    "repair_subject": ("整改对象", "复验对象", "对应缺陷事项"),
    "repair_action": ("实际整改措施", "已实施整改措施"),
    "repair_result": ("整改状态", "整改完成情况"),
    "repaired_on": ("整改完成日期",),
    "repair_signer": ("整改签认", "整改负责人签认"),
    "defect_closure": ("缺陷关闭结论", "缺陷关闭状态"),
}
LINK_KEYS = ("contract_id","buyer","seller","subject")
ORIGINAL = ("acceptance","acceptance_number","accepted_on","acceptance_scope","acceptance_result",
            "defect_number","acceptance_exception","inspection_basis","measured_result","acceptance_signer","quantity_accepted")
REPAIR = ("remediation","original_acceptance","defect_number","repair_number","repair_subject","repair_action",
          "repair_result","repaired_on","repair_signer")
FINAL = ("reinspection","acceptance","original_acceptance","repair_number","defect_number","repair_subject","defect_closure",*ORIGINAL[1:])
SIGNED_FAILURE = {"不合格","验收不合格","未通过","验收未通过","拒收","最终验收不合格","终验不合格","有条件通过","待整改","整改后复验"}
CLOSED = {"已关闭","全部关闭","缺陷已关闭"}
CODE = re.compile(r"(?=[A-Za-z0-9\u4e00-\u9fff._-]*[0-9])[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff._-]{0,63}")
NUMBER_TYPES = {"acceptance_number":"acceptance_reference","original_acceptance":"acceptance_reference",
                "defect_number":"defect_number","repair_number":"repair_number"}


def verify_number_links(graph):
    nodes = {n["id"]:n for n in graph["nodes"]}
    held = {item["fact"] for item in graph.get("quality_references", {}).get("holds", [])}
    expected = []
    def compact(value):
        return "".join(unicodedata.normalize("NFKC",value).split())
    for fact in graph["facts"]:
        kind = NUMBER_TYPES.get(fact["field"])
        if not kind or fact["status"] not in ("anchored","confirmed"):
            continue
        if fact["id"] in held:
            expected.append((fact.get("unit", fact["doc"]), fact["id"], "incomplete_"+fact["field"], (fact["id"],)))
            continue
        value = compact(fact["value"])
        target = kind+"-"+hashlib.sha256(value.encode()).hexdigest()[:18]
        node = nodes.get(target)
        if not node or node["type"]!=kind or compact(node["label"])!=value:
            raise ValueError("整改复验编号与所据原文实体不符")
        expected.append((fact.get("unit",fact["doc"]),target,fact["field"],(fact["id"],)))
    kinds = set(NUMBER_TYPES) | {"incomplete_"+field for field in NUMBER_TYPES}
    actual = [(e["from"],e["to"],e["type"],tuple(e["evidence"])) for e in graph["edges"] if e["type"] in kinds]
    if sorted(actual)!=sorted(expected):
        raise ValueError("整改复验编号边与资料归属、编号或引文不符")


def linked(contract, record):
    return all(contract.body(k) and contract.body(k) == record.body(k) for k in LINK_KEYS)


def identifier(doc, field):
    value = doc.body(field)
    return value if CODE.fullmatch(value) else ""


def step(role, doc, date_field, fields, read_date, repair_checks):
    date = read_date(doc, date_field)
    sources = doc.evidence(*fields)
    sources.extend(f"{h['doc']}/p{h['page']}" for h in doc.quality_holds if h["field"] in fields and h["lines"])
    sources.extend(note["fact"] for h in doc.quality_holds if h["field"] in fields for note in h["observations"])
    result = {"role":role, "unit":doc.unit, "date":date.isoformat() if date else None}
    if role == "repair" and doc.unit in repair_checks:
        check = repair_checks[doc.unit]
        result.update(date=check["date"], completion=check)
        sources.extend(check["evidence"])
    result["evidence"] = list(dict.fromkeys(sources))
    return result


def closed_steps(findings):
    for item in findings:
        chain = item.get("reinspection",{})
        if item["rule"]=="H02" and item["status"]=="ok" and chain.get("state")=="closed":
            return {s["role"]:s["unit"] for s in chain["steps"]}
    return {}


def assess(contract, receipts, repairs, retests, evaluate, *, signature_ok=None, read_date=None, repair_checks=None):
    # A regular acceptance form may explicitly reference the record that it reinspects.
    originals, followups = [], list(retests)
    for doc in receipts:
        markers = {"original_acceptance","repair_number","defect_closure"}
        marked = (any(doc.fields[field] for field in markers) or doc.uncertain.intersection(markers)
                  or any(g.get("field") in markers for g in doc.gaps))
        (followups if marked else originals).append(doc)
    first = evaluate(contract, originals)
    if len(originals)>1:
        for doc in originals:
            issue = evaluate(contract,[doc])
            if issue["status"]=="issue" and linked(contract,doc):
                first.update(status="issue",detail=issue["detail"]+" 多份验收记录的覆盖范围及先后关系待核。")
                break
    if not (repairs or followups or (first["status"] in ("issue","risk") and any(d.fields["defect_number"] for d in originals))):
        return first, originals[0].date("accepted_on") if first["status"]=="ok" else None
    groups = (("original",originals,"accepted_on",ORIGINAL),("repair",repairs,"repaired_on",REPAIR),
              ("final",followups,"accepted_on",FINAL))
    if read_date is None:
        read_date = type(contract).date
    repair_checks = repair_checks or {}
    steps = [step(role,doc,date_field,fields,read_date,repair_checks) for role,docs,date_field,fields in groups for doc in docs]
    refs = [*first["evidence"],*(ref for s in steps for ref in s["evidence"])]
    for doc in [*repairs,*followups]:
        refs.extend(doc.evidence(*LINK_KEYS))
    scope = list(dict.fromkeys([*first["scope"],*(s["unit"] for s in steps)]))
    initial = first["status"]
    open_status = initial if initial in ("issue","risk") else "missing"

    def outcome(status, detail, date=None, focus=None):
        result = {**first,"status":status,"detail":detail,"scope":scope,"evidence":list(dict.fromkeys(refs)),
                  "reinspection":{"state":"closed" if date else "open","steps":steps}}
        if repair_checks and focus:
            result["reinspection"]["focus"] = focus
        return result, date

    def incomplete(reason, focus=None):
        prefix = first["detail"]+" " if initial in ("issue","risk") else ""
        return outcome(open_status,prefix+reason,focus=focus)

    if not all(len(docs)==1 for _,docs,_,_ in groups):
        return incomplete("整改复验需逐一对应原验收、整改记录和最终复验，目前资料有缺件或多个候选。")
    original, repair, final = originals[0], repairs[0], followups[0]
    if not (original.fields["acceptance"] and repair.fields["remediation"] and (final.fields["reinspection"] or final.fields["acceptance"])):
        return incomplete("三份记录仍需已核的原件标题及单据归属。")
    if not all(linked(contract,doc) for doc in (original,repair,final)):
        return incomplete("原验收、整改或复验的合同号、双方主体及交付标的尚未全部对应。")
    partial = list(dict.fromkeys(LABELS[h["field"]][0]+"“"+h["value"]+"”"
                                 for record in (original, repair, final) for h in record.quality_holds))
    if partial:
        return incomplete("、".join(partial)+"存在遮盖或仅展示部分编号的记载，请核对三份原件的完整编号。")
    original_id, repair_id = identifier(original,"acceptance_number"), identifier(repair,"repair_number")
    final_id, defect = identifier(final,"acceptance_number"), identifier(original,"defect_number")
    if not all((original_id,repair_id,final_id,defect)) or original_id==final_id or not (
            original_id==identifier(repair,"original_acceptance")==identifier(final,"original_acceptance")
            and repair_id==identifier(final,"repair_number")
            and defect==identifier(repair,"defect_number")==identifier(final,"defect_number")):
        issue = "defect" if defect and defect != identifier(final,"defect_number") else None
        return incomplete("原验收号、整改记录号、缺陷号和独立复验号尚未逐项对应。",issue)
    description = original.body("acceptance_exception")
    if not description or description in ("无","无遗留事项","无整改事项","无异常") or not (
            description==repair.body("repair_subject")==final.body("repair_subject")):
        return incomplete("整改与复验所指的缺陷事项尚未逐字对应原验收记录。")
    signed_original = original.signed("acceptance_signer") if signature_ok is None else signature_ok(original)
    if not signed_original or initial not in ("issue","risk") or not (
            original.body("acceptance_result") in SIGNED_FAILURE or initial=="issue"):
        return incomplete("需确定原验收的具体不合格或附条件结论及验收人核图签认。")
    completion = repair_checks.get(repair.unit)
    if completion and completion["status"] != "ok":
        return incomplete(completion["detail"],"dates" if not completion["date"] else "repair")
    action = repair.body("repair_action")
    if not action or re.search(r"计划|拟|待|尚未|未完成|仅部分|未实施",action) or (
            repair.body("repair_result") not in {"已完成","整改完成","已完成整改"} or not repair.signed("repair_signer")):
        return incomplete("整改记录需具备实际措施、明确的完成状态及负责人核图签认。")
    signed, opened = read_date(contract,"signed_on"), read_date(original,"accepted_on")
    fixed, closed = read_date(repair,"repaired_on"), read_date(final,"accepted_on")
    if not all((signed,opened,fixed,closed)) or not signed <= opened <= fixed <= closed:
        return incomplete("签约、原验收、整改完成和复验日期缺失或先后矛盾。")
    latest = evaluate(contract,[final])
    refs.extend(latest["evidence"])
    if latest["status"] != "ok":
        return outcome("issue" if latest["status"]=="issue" else open_status,
                       first["detail"]+" 复验尚未关闭该项缺陷。"+latest["detail"])
    if final.body("defect_closure") not in CLOSED or final.body("acceptance_exception") not in {"无","无遗留事项","无整改事项","无异常"}:
        return incomplete("复验需明确记载缺陷关闭且无遗留事项。")
    if any(doc.incomplete(*fields,*LINK_KEYS) for _,docs,_,fields in groups for doc in docs):
        return incomplete("原验收、整改或复验仍有待核字段或原页覆盖缺口。")
    return outcome("ok", f"原验收 {original_id} 记载缺陷 {defect}。整改记录 {repair_id} 与复验 {final_id} 对应该事项，"
                   f"实物范围、验收结论和签认支持于 {closed.isoformat()} 关闭。",closed)
