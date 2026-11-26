"""Check a contract's named acceptance signatories against distinct original signature lines."""

import hashlib
import re
import unicodedata
from collections import defaultdict

from calculations import normalized
from contract_changes import SOURCE_LABELS, labelled_sources
from delegation import agent_kind, complete_id, covered_rows
from performance_versions import SIGNATORY_FORMATS
from reinspection import LINK_KEYS, linked
import signer_timing


LEGACY_FORMAT = "named-acceptance-signatures-v1"
FORMAT = signer_timing.FORMAT
PERFORMANCE_FORMATS = SIGNATORY_FORMATS
CLAUSE = "acceptance_signing_clause"
SIGNER = "acceptance_signer"
LABELS = {CLAUSE:("验收签认约定","验收签署约定","验收签字要求","终验签认约定","指定验收人","甲方指定验收人")}
SIGN_LABELS = ("验收签认","验收负责人","验收人","验收签字","复验签认")
TITLES = {"contract":{"采购合同","设备采购合同","购销合同","采购协议"},
          "acceptance":{"验收单","到货验收单","验收报告","采购验收单","设备验收单"},
          "reinspection":{"复验报告","整改复验单","最终复验报告","整改复验报告"}}
SCALARS = {**SOURCE_LABELS, "net":("不含税金额","不含税合计"),"tax":("税额",),"total":("含税总额","含税总价","价税合计","含税合计"),
           "currency":("币种","结算货币"),"unit":("金额单位","计价单位"),
           "accepted_on":("验收日期","验收时间","复验日期","复验时间"),
           "payment_term":("结算条款","付款条款","付款方式","结算方式","支付条件","付款条件"),
           "acceptance_result":("验收结果","验收结论","复验结果","复验结论")}
HINT = re.compile(r"(?:验收|复验|终验).{0,36}(?:签字确认|签认约定|指定.{0,8}(?:人员|代表|签字)|"
                  r"签字要求|共同签|联合签|会签|须由|需由|应由|须经|应经|需经|会同|由.{1,22}(?:签[字名署章认]|确认)|"
                  r"未到场|未参与|冒签|补签|拒签|代签|签名不符|另行授权|另须.{0,12}(?:签|批准))|"
                  r"(?:指定|授权).{0,12}(?:验收人|验收代表|签认验收)|(?:还须|还需|另须|另需).{0,14}(?:复签|会签)")
SUBJECT = re.compile(r"(终验及整改复验|最终验收及整改复验|终验|最终验收)(?:均)?(?:须|应)?由(.+?)(共同签字确认|共同签名确认|签字确认|签名确认)")
SIGNED = re.compile(r"(.+?)\s*\(\s*已签(?:字|名)\s*\)")


def parts(raw):
    label, sep, body = unicodedata.normalize("NFKC",raw).strip().partition(":")
    return normalized(label),body.strip() if sep else ""


def mentions(raw):
    label,_ = parts(raw)
    return label in LABELS[CLAUSE] or bool(HINT.search(normalized(raw)))


def person(value):
    return bool(value and not re.search(r"\s",value) and agent_kind(value)=="named"
                and not re.search(r"代签|代为|代表|未签|待签|代验",value)
                and not re.search(r"(?:组|员|职工|工程师|负责人|总工|班长|老师|经办)$",value)
                and value not in {"经办人","收货人","验收人","签章","待核","空缺","甲单位","乙单位","待补","未知","待确认",
                                  "待明确","未提供","未记载","未注明","无名氏","不清楚","签字栏","仅盖章"})


def required_names(value, joint):
    names = [p.strip() for p in re.split("[、与和]",value)] if joint else [value.strip()]
    if len(names)!=(2 if joint else 1) or len(set(names))!=len(names) or not all(person(p) for p in names):
        return None
    return names


def instruction(raw):
    label,body = parts(raw)
    if label not in LABELS[CLAUSE]:
        return None
    body = body.rstrip("。")
    if label in {"指定验收人","甲方指定验收人"} and person(body):
        return "single","final",[body]
    match = SUBJECT.fullmatch(body)
    if not match:
        return None
    joint = match[3].startswith("共同")
    names = required_names(match[2],joint)
    if not names:
        return None
    return "joint" if joint else "single","final_and_reinspection" if "复验" in match[1] else "final",names


def signed_name(raw):
    label,body = parts(raw)
    matched = SIGNED.fullmatch(body) if label in SIGN_LABELS else None
    name = matched[1].strip() if matched else ""
    return name if person(name) else None


def covers(field, value, quote):
    # Importing at evaluation time keeps these standalone evidence checks usable by the offline verifier.
    from performance import LABELS as performance_labels, STAGE_PREFIX
    label,body = parts(quote)
    line, value = normalized(quote).rstrip("。"),normalized(value).rstrip("。")
    if field in TITLES:
        return line==value and line in TITLES[field]
    if field=="payment_stage" and STAGE_PREFIX.match(line):
        return bool(value and value in (line,normalized(body).rstrip("。")))
    if field=="payment_deadline":
        from payment_windows import label_matches
        return label_matches(label) and bool(value and body) and value in (line,normalized(body).rstrip("。"))
    names = performance_labels.get(field,SCALARS.get(field,()))
    return label in names and bool(value) and value in (line,normalized(body).rstrip("。"))


def page_evidence(graph, read_text, version=FORMAT):
    pages = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    sections = {(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents",[]) if "source" in d}
    by_page = defaultdict(list)
    for f in graph["facts"]:
        by_page[(f["doc"],f["page"])].append(f)
    kinds = graph["documents_by_kind"]
    contracts = set(kinds.get("contract",[]))
    receipts = set(kinds.get("acceptance",[])) | set(kinds.get("reinspection",[]))
    releases = set(kinds.get("warranty",[])) if "warranty_sources" in graph else set()
    # A narrowly identified confirmation of bank credit belongs to the payment condition.
    prior = graph.get("prior_installment_sources", {})
    credit_rows = {(s["doc"], s["page"], s["line"], s["quote"]) for s in prior.get("lines", ())
                   if prior.get("format")=="prior-installment-bank-evidence-v2" and s.get("credit_only")}
    rules, signatures, dates = [], [], []
    for ref,page in pages.items():
        doc, suffix = ref.rsplit("/p",1)
        number = int(suffix)
        unit = sections.get((doc,number),doc)
        observations = by_page[(doc,number)]
        by_line = defaultdict(list)
        for fact in observations:
            loc = fact.get("source_line")
            if loc and loc["rects"]:
                by_line[loc["number"],loc["text"]].append(fact)
        seen = set()
        def record(raw, line, facts, native):
            label,body = parts(raw)
            if version == FORMAT and unit in receipts:
                dated = signer_timing.dated_line(unit, doc, number, line, raw, facts)
                if dated:
                    dates.append(dated)
            clause = mentions(raw) or any(f["field"]==CLAUSE for f in facts) or unit in contracts and label in SIGN_LABELS
            if native and any(s["role"]=="authority" and (s["doc"],s["page"],s["line"],s["quote"])==(doc,number,line,raw)
                              for s in graph.get("payment_release_sources",{}).get("lines",[])):
                clause=False
            if native and (doc, number, line, raw) in credit_rows:
                clause=False
            if unit in releases and label in SIGN_LABELS and not re.search(r"终验|复验|验收|合同",body):
                clause=False
            signature = unit in receipts and (label in SIGN_LABELS or any(f["field"]==SIGNER for f in facts))
            for active,field,rows in ((clause,CLAUSE,rules),(signature,SIGNER,signatures)):
                if not active:
                    continue
                supported = [f for f in facts if f["field"]==field and f["status"] in ("anchored","confirmed")
                             and covers(field,f["value"],f["quote"]) and normalized(raw)==normalized(f["quote"])]
                fact = supported[0] if len(supported)==len(facts)==1 else None
                row = {"unit":unit,"doc":doc,"page":number,"line":line,"quote":raw,"facts":[f["id"] for f in facts],
                       "fact":fact["id"] if fact else None,"native":native}
                if field==SIGNER:
                    name = signed_name(raw)
                    signoff = (fact.get("attestation") or {}) if fact else {}
                    row.update(name=name,confirmed=bool(native and name and fact and name==signed_name(fact["quote"])
                               and fact["status"]=="confirmed" and signoff.get("decision")=="confirm" and signoff.get("source_check")))
                elif fact and instruction(raw)!=instruction(fact["quote"]):
                    row["fact"] = None
                rows.append(row)
        if page.get("layer")=="text":
            source=read_text(doc,number)
            if not isinstance(source,str) or hashlib.sha256(source.encode()).hexdigest()!=page.get("text_sha256"):
                raise ValueError("验收签认约定与归档文字层摘要不符")
            for i,raw in enumerate(source.splitlines(),1):
                matched=by_line[(i,raw)]
                seen.update(f["id"] for f in matched)
                record(raw,i,matched,True)
        for f in observations:
            if f["id"] not in seen:
                record(f["quote"],None,[f],False)
    ambiguous = any(not s["name"] for s in signatures)
    timing = {}
    if version == FORMAT:
        joint = any((instruction(s["quote"]) or (None,))[0] == "joint" for s in rules)
        timing = {"dates": dates if rules or ambiguous else [],
                  "bank_pages": signer_timing.bank_pages(graph, read_text, pages) if joint else []}
    if not rules and not ambiguous:
        return {"format":version,"clauses":[],"signatures":[],"pages":[],"visual_notes":[],**timing}
    units = set(kinds.get("contract",[])) | receipts | {r["unit"] for r in rules}
    fields = {f["field"] for f in graph["facts"]}
    coverage = covered_rows(graph,read_text,units,fields,covers,"验收签认依据")
    for p in coverage:
        if credit_rows:
            p["uncovered"] = [r for r in p["uncovered"] if (p["doc"],p["page"],r["line"],r["quote"]) not in credit_rows]
        p["text_only"] = pages[f"{p['doc']}/p{p['page']}"].get("clause_text_only") is True
    mixed = {(p["doc"],p["page"]) for p in coverage if not p["text_only"]}
    notes = [{"unit":f.get("unit",f["doc"]),"doc":f["doc"],"page":f["page"],"fact":f["id"],"quote":f["quote"]}
             for f in graph["facts"] if (f["doc"],f["page"]) in mixed and not (f.get("source_line") or {}).get("rects")
             and f["field"] not in (CLAUSE,SIGNER)]
    return {"format":version,"clauses":rules,"signatures":signatures,"pages":coverage,"visual_notes":notes,**timing}


def refs(row):
    return row["facts"] or [f"{row['doc']}/p{row['page']}"]


def coverage_gaps(source):
    return [{"id":f"{p['doc']}/p{p['page']}","doc":p["doc"],"page":p["page"],"quality":"acceptance_authority_clause","field":CLAUSE,**line}
            for p in source["pages"] for line in p["uncovered"]]


def attach(graph, read_text):
    source = page_evidence(graph,read_text)
    graph["acceptance_authority_sources"] = source
    graph["gaps"].extend(coverage_gaps(source))
    nodes, edges = signer_timing.source_graph(source["dates"])
    graph["nodes"].extend(nodes)
    graph["edges"].extend(edges)


def check(graph, contract, receipts, retests, *, contract_supported, other_terms=False, name_records=False):
    source = graph.get("acceptance_authority_sources",{})
    if not source.get("clauses") and not source.get("signatures"):
        return None
    clauses = source["clauses"]
    units = list(dict.fromkeys([contract.unit,*(r["unit"] for r in clauses),*(d.unit for d in [*receipts,*retests])]))
    contract_refs = contract.evidence("contract",*LINK_KEYS,"signed_on","effect_on","valid_until")
    cited = [*contract_refs,*(ref for row in clauses for ref in refs(row))]
    cited.extend(f"{p['doc']}/p{p['page']}" for p in source["pages"])
    cited.extend(n["fact"] for n in source["visual_notes"])
    primary = [r for r in clauses if r["unit"]==contract.unit and r["fact"] and r["native"] and instruction(r["quote"])]
    parsed = instruction(primary[0]["quote"]) if len(primary)==1 else None
    mode,scope,required = parsed or ("unresolved",None,[])
    def readable(unit):
        pages=[p for p in source["pages"] if p["unit"]==unit]
        return bool(pages) and all(p["native"] and p["text_only"] and not p["uncovered"] for p in pages)
    if not parsed:
        reason = "需明确原合同所列具名验收人、签署方式及其他签认约定。" if clauses else "验收签认尚不能对应到已核实的具名签字人。"
    elif len(clauses)!=1:
        reason = "已见原合同具名约定，另有其他签认线索，请查清全部条件和适用文本。"
    elif other_terms:
        reason = "还需查明附件或变更是否修改了本次验收的签认人员与权限。"
    elif not readable(contract.unit) or not contract_supported:
        reason = "需核对完整合同、页内附注及约定的生效依据。"
    elif not complete_id(contract.body("contract_id")) or graph.get("quality_addenda",{}).get("limited_numbers"):
        reason = "合同或协议编号的完整记载仍待核对。"
    else:
        reason = ""
    records = []
    effective, expiry = contract.date("effect_on"), contract.date("valid_until")
    for doc in [*receipts,*retests]:
        repeated = doc in retests or any(doc.fields[k] or k in doc.uncertain for k in ("original_acceptance","repair_number","defect_closure"))
        role = "reinspection" if repeated else "acceptance"
        accepted = doc.date("accepted_on")
        rows = [s for s in source["signatures"] if s["unit"]==doc.unit]
        actual = [s["name"] for s in rows if s["confirmed"]]
        missing = [name for name in required if name not in actual]
        extra = list(dict.fromkeys(name for name in actual if name not in required)) if parsed else []
        evidence = doc.evidence(*LINK_KEYS,"acceptance","reinspection","accepted_on","acceptance_scope",SIGNER)
        evidence.extend(ref for s in rows for ref in refs(s))
        detail,status = reason,"missing"
        if not detail:
            if (not linked(contract,doc) or not all(labelled_sources(d,LINK_KEYS) for d in (contract,doc))
                    or not labelled_sources(contract,("signed_on","effect_on","valid_until"))):
                detail = "验收记录的合同编号、双方和标的尚未与本合同逐项对应。"
            elif repeated and scope!="final_and_reinspection":
                detail = "原条款只明确终验签认，需核对其对本次整改复验的适用范围。"
            elif not all(covers(field,f["value"],f["quote"]) for field in ("accepted_on","acceptance_scope") for f in doc.fields[field]):
                detail = "需从验收或复验的原始栏位核实日期和范围。"
            elif doc.body("acceptance_scope") not in {"全部交付终验","全部交付最终验收","全部标的最终验收","最终验收","终验"}:
                detail = "该记录尚未明确覆盖约定的全部终验范围。"
            elif not accepted or not effective or accepted==effective:
                detail = "需核对验收时具名条款已经生效的日期或当日时分。"
            elif accepted<effective or expiry and accepted>expiry:
                status,detail = "risk","验收日期在已核合同期间之外，请核查当时适用的签认条款。"
            elif extra:
                status,detail = "risk","核图签字人"+"、".join(extra)+"与本条款指定人员不符，请核查代签授权或其他依据。"
            elif not readable(doc.unit) or any(not s["name"] for s in rows):
                detail = "签字栏、影像附注或其他原文待辨，请核对每位签字人的原页。"
            elif missing:
                detail = "尚缺"+"、".join(missing)+"逐人对照原页核准的签字。"
            elif len(actual)!=len(rows) or len(actual)!=len(required):
                detail = "需逐人核对独立签字栏、重复记录和核图决定。"
            else:
                status,detail = "ok","合同指定的"+"、".join(required)+"均有独立签字栏及核图记录。"
        records.append({"unit":doc.unit,"role":role,"date":accepted.isoformat() if accepted else None,
                        "status":status,"detail":detail,"signed":rows,"missing_names":missing,
                        "other_names":extra,"evidence":list(dict.fromkeys(evidence))})
        cited.extend(evidence)
    status = "risk" if any(r["status"]=="risk" for r in records) else "ok" if records and all(r["status"]=="ok" for r in records) else "missing"
    detail = reason or (" ".join(dict.fromkeys(r["detail"] for r in records)) if records else "缺少本合同对应的终验签认原件。")
    if name_records and len(records)>1 and not reason:
        detail = " ".join(("整改复验" if r["role"]=="reinspection" else "原验收")+"（"+(r["date"] or "日期待核")+"）"+r["detail"] for r in records)
    return {"mode":mode,"applies_to":scope,"required":required,"clause_evidence":[ref for s in clauses for ref in refs(s)],
            "contract_evidence":contract_refs,
            "units":units,"status":status,"detail":detail,"records":records,"evidence":list(dict.fromkeys(cited))}


def witness_edges(findings):
    result=[]
    for finding in findings:
        entry=finding.get("acceptance_authority")
        if not entry or entry["mode"]=="unresolved" or len(entry["clause_evidence"])!=1:
            continue
        clause,=entry["clause_evidence"]
        for record in entry["records"]:
            if record["status"]=="ok":
                for row in record["signed"]:
                    result.append({"from":clause,"to":row["fact"],"type":"named_acceptance_signature",
                                   "evidence":list(dict.fromkeys([clause,row["fact"],*entry["contract_evidence"],*record["evidence"]]))})
    return result


def verify_sources(report,read_text,*,signing=False):
    policy,graph=report["policy"],report["graph"]
    marker=policy.get("acceptance_authority")
    dated_nodes = [n for n in graph["nodes"] if n["type"] == "acceptance_signer_date"]
    dated_edges = [e for e in graph["edges"] if e["type"] == "signer_date_source"]
    if marker != FORMAT and (policy.get("version","") >= signer_timing.SINCE or
            "signer_timing.py" in policy.get("code_sha256",{}) or dated_nodes or dated_edges or
            any("signer_timing" in f for f in report["findings"])):
        raise ValueError("底稿缺少共同签认时序程序或混入其他版本的原行")
    if not marker:
        if "acceptance_authority.py" in policy.get("code_sha256",{}) or "acceptance_authority_sources" in graph or policy.get("performance_checks") in PERFORMANCE_FORMATS:
            raise ValueError("缺少底稿所据的具名验收签认程序")
        if signing and any(f["rule"]=="H02" and f["status"]=="ok" for f in report["findings"]):
            legacy=page_evidence(graph,read_text,LEGACY_FORMAT)
            if legacy["clauses"] or legacy["signatures"]:
                raise ValueError("旧版终验有具名签认约定或待辨签字栏，请按现行程序重审后签收。")
        return
    source=page_evidence(graph,read_text,marker)
    if (marker not in (LEGACY_FORMAT,FORMAT) or policy.get("performance_checks") not in PERFORMANCE_FORMATS or graph.get("acceptance_authority_sources")!=source or
            coverage_gaps(source)!=[g for g in graph["gaps"] if g["quality"]=="acceptance_authority_clause"]):
        raise ValueError("验收签认条款、签字原行或版式覆盖与提交材料不符")
    expected=sorted((f.get("unit",f["doc"]),f["id"],f["field"],(f["id"],)) for f in graph["facts"] if f["field"] in (CLAUSE,SIGNER)
                    and f["status"] in ("anchored","confirmed"))
    actual=sorted((e["from"],e["to"],e["type"],tuple(e["evidence"])) for e in graph["edges"] if e["type"] in (CLAUSE,SIGNER))
    if expected!=actual or witness_edges(report["findings"])!=[e for e in graph["edges"] if e["type"]=="named_acceptance_signature"]:
        raise ValueError("验收签字的原件归属、具名约定或逐人证据关系不符")
    if (dated_nodes, dated_edges) != signer_timing.source_graph(source.get("dates", [])):
        raise ValueError("共同签认日期的原行或归属关系不符")
    if signing and marker == LEGACY_FORMAT and source["clauses"] and any(f["rule"] == "H05" for f in report["findings"]):
        from performance import compute
        current = compute({**graph, "acceptance_authority_sources": page_evidence(graph,read_text)})
        for entry in current:
            timing = entry.get("signer_timing")
            if not timing:
                continue
            old = [f for f in report["findings"] if f["rule"] == "H05" and timing["bank"] in f["scope"]]
            if timing["state"] == "before" or (timing["state"] != "after" and any(f["status"] == "ok" for f in old)):
                raise ValueError("旧版付款时点尚未核对共同签认日期，请重新审计后签收。")
