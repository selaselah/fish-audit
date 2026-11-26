"""Compare the words of two issued warranty records without deciding coverage or payment."""

import hashlib
import re
from collections import Counter, defaultdict

from acceptance_authority import parts, signed_name
from contract_changes import SOURCE_LABELS
from delegation import complete_id, is_page_marker
from reinspection import LINK_KEYS
import warranty_service as service


FORMAT = "contract-warranty-release-v5"
SINCE = (2026,11,27,7)
RULE = ("期满确认与维修工单记载差异", "逐张核对同一合同、双方及标的的原件所载缺陷声明、工单编号、报修日期和工单状态。")
EDGE = "warranty_record_difference"
CLEAR = {"无未关闭缺陷", "无未结质量问题", "无未解决质量问题"}
CLAIM_HINT = re.compile(r"工单|报修|维修|修复|保修|质保|故障|缺陷|销单|消缺|清结|关闭|续单|结案")
QUALIFIER = re.compile(r"争议|存疑|异议|撤回|撤销|更正|作废|重开|待确认|不适用|不含|除外|不包括|另见|另附|另行|仅限|以.{1,16}为准")
# Accept simple descriptions of a physical fault. Free-form narratives and qualifications stay with the reviewer.
FAULT = re.compile(r"(?:柜体|柜内|设备|冷藏柜|机组|主机|制冷|冷凝|蒸发|温控|温度|供电|循环|冷却|散热|排气|进气|上部|下部|左侧|右侧|内置|外置|回风|测温|主|副|冷藏|冷冻){0,3}"
                   r"(?P<part>风扇|风机|探头|传感器|压缩机|电机|控制器|控制板|电源|接头|阀门|泵|柜门|门封|显示屏|温控|制冷|设备)"
                   r"(?:故障|异常|损坏|失灵|失效|不转|停转|偏差|异响|渗漏)")
UNCERTAIN = re.compile(r"待定|待填|待核|待补|待确认|不详|未知|未填|未明|未提供|另见|同上|不适用|[＊*?？…]|^无$|^[-—/]+$")
ORDINARY = {"total","currency","unit","signed_on","effect_on","effect_clause","buyer_signature","seller_signature",
            "quantity_agreed","acceptance_criteria","payment_stage","payment_term","acceptance_authority","buyer_agent_signature","seller_agent_signature"}
OTHER_DOCS = {"bank_receipt","acceptance","invoice","reinspection"}
BANK_WARRANTY_NAME = re.compile(r"(?:第[一二三四五六七八九十0-9]+期)?(?:质保金|质量保证金)(?:款)?")
SINGLE_ROLES = {"contract","warranty",service.TITLE}


def physical_facts(graph):
    """A named observation must belong to exactly one original page in this graph."""
    manifests=defaultdict(list)
    nodes=defaultdict(list)
    parents=defaultdict(list)
    fields=set()
    for doc in graph["documents"]:
        manifests[doc["id"]].append(doc)
    for node in graph["nodes"]:
        nodes[node["id"]].append(node)
    for edge in graph["edges"]:
        if edge["type"] in ("contains","records"):
            parents[edge["type"],edge["to"]].append((edge["from"],edge["evidence"]))
        elif len(edge["evidence"])==1:
            fields.add((edge["from"],edge["type"],edge["evidence"][0]))
    counts=Counter(f["id"] for f in graph["facts"])
    for f in graph["facts"]:
        doc,ref=f["doc"],f["id"]
        page=f"{doc}/p{f['page']}"
        if (counts[ref]!=1 or f.get("unit",doc)!=doc or not ref.startswith(page+"/") or
                not all(len(items)==1 for items in (manifests[doc],nodes[doc],nodes[page],nodes[ref]))):
            continue
        if (nodes[doc][0]["type"]=="document" and nodes[page][0]["type"]=="page" and nodes[ref][0]["type"]=="observation" and
                nodes[ref][0].get("status")==f["status"] and f.get("source_sha256") and
                manifests[doc][0].get("sha256")==nodes[doc][0].get("sha256")==f["source_sha256"] and
                f.get("page_sha256") and nodes[page][0].get("sha256")==f["page_sha256"] and
                parents["contains",page]==[(doc,[page])] and parents["records",ref]==[(page,[ref])] and
                (doc,f["field"],ref) in fields):
            yield f


def register_pages(graph, read_text, ticket_pages):
    """Retain only original line refs for the named operands and record any limit on their scope."""
    from graph import PRINTED_TITLES
    import warranty_terms as terms
    kinds = graph["documents_by_kind"]
    if not ticket_pages or not kinds.get("warranty") or not kinds.get("contract"):
        return []
    roles = defaultdict(set)
    for role, units in kinds.items():
        for unit in units:
            roles[unit].add(role)
    located = defaultdict(list)
    for fact in physical_facts(graph):
        source = fact.get("source_line") or {}
        if source.get("rects"):
            located[fact["doc"],fact["page"],source["number"],source["text"]].append(fact)
    labelled = {label:field for field in LINK_KEYS for label in SOURCE_LABELS[field]}
    for field, labels in {**terms.LABELS, **service.LABELS, "warranty_release":("质保期满确认","质保期满记录"),
                          "acceptance_signer":("验收签认","验收签字","验收人","验收人员")}.items():
        labelled.update(dict.fromkeys(labels,field))
    required = {"contract":set(LINK_KEYS)|{"warranty_period","warranty_condition"},
                "warranty":terms.RELEASE_FIELDS, service.TITLE:set(LINK_KEYS)|set(service.LABELS)}
    blocked = {(g["doc"],g.get("page")) for g in graph.get("gaps",[]) if g.get("doc")}
    blocked.update((f["doc"],f["page"]) for f in graph["facts"] if f["status"] not in ("confirmed","anchored") or (f.get("attestation") or {}).get("decision")=="dispute")
    pages = []
    for node in graph["nodes"]:
        if node["type"]!="page":
            continue
        doc,suffix=node["id"].rsplit("/p",1)
        page=int(suffix)
        role=next(iter(roles[doc])) if len(roles[doc])==1 else "unresolved"
        text_only=node.get("clause_text_only") is True
        clean = node.get("layer")=="text" and text_only and role in SINGLE_ROLES | OTHER_DOCS
        fields=defaultdict(list)
        if node.get("layer")=="text":
            text=read_text(doc,page)
            if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=node.get("text_sha256"):
                raise ValueError("质保记载对照的物理原页文字摘要不符")
            rows=[(i,row) for i,row in enumerate(text.splitlines(),1) if not is_page_marker(row)]
            if role in SINGLE_ROLES:
                clean=clean and bool(rows) and PRINTED_TITLES.get(service.literal(rows[0][1]))==role and (doc,page) not in blocked
                for i,raw in rows:
                    quote=service.literal(raw)
                    label,body=parts(raw)
                    field=PRINTED_TITLES.get(quote) or labelled.get(label)
                    facts=[f for f in located[doc,page,i,raw] if f.get("unit",doc)==doc and f["status"] in ("confirmed","anchored")
                           and service.literal(f["quote"])==quote and service.literal(f["value"]) in (body,quote)]
                    if field==role:
                        title=[f["id"] for f in facts if f["field"]==role]
                        if title and i==rows[0][0]:
                            fields[role].append(title[0])
                        else:
                            clean=False
                    elif field in required[role]:
                        if (QUALIFIER.search(body) or field=="warranty_period" and not terms.parse_period(label,body) or
                                field=="warranty_condition" and body.rstrip("。") not in terms.DEFECT_CONDITION):
                            clean=False
                        exact=[f["id"] for f in facts if f["field"]==field]
                        if len(exact)==1:
                            fields[field].extend(exact)
                        else:
                            clean=False
                    elif role=="contract" and len(facts)==1 and facts[0]["field"] in ORDINARY:
                        kind=terms.contract_kind(raw)
                        if kind=="unresolved" or QUALIFIER.search(raw) or (CLAIM_HINT.search(raw) and
                                facts[0]["field"] not in ("payment_stage","payment_term")):
                            clean=False
                        if facts[0]["field"] in ("payment_stage","payment_term"):
                            fields["clause"].append(facts[0]["id"])
                    else:
                        clean=False
                if any(len(ids)!=1 for field,ids in fields.items() if field!="clause"):
                    clean=False
            else:
                if not rows or PRINTED_TITLES.get(service.literal(rows[0][1]))!=role:
                    clean=False
                for _,raw in rows:
                    label,body=parts(raw)
                    if role=="bank_receipt" and label in ("款项用途","付款用途","款项性质","银行附言") and BANK_WARRANTY_NAME.fullmatch(body):
                        continue
                    if CLAIM_HINT.search(raw) or QUALIFIER.search(raw):
                        clean=False
        pages.append({"doc":doc,"page":page,"role":role,"text_only":text_only,"bounded":clean,"refs":dict(fields)})
    return pages


def confirmed_signature(fact):
    action=fact.get("attestation") or {}
    receipt=action.get("source_check") or {}
    return (fact["status"]=="confirmed" and action.get("decision")=="confirm" and action.get("fact")==fact["id"] and
            signed_name(fact["source_line"]["text"]) and receipt.get("format")=="field-source-v1" and
            receipt.get("operation")=="confirm" and type(action.get("rev")) is int and action["rev"]>0 and
            receipt.get("rev")==action["rev"] and re.fullmatch(r"[0-9a-f]{64}",receipt.get("report_hash") or "") and
            receipt.get("doc")==fact["doc"] and receipt.get("page")==fact["page"] and
            receipt.get("original_sha256")==fact["source_sha256"] and receipt.get("page_sha256")==fact["page_sha256"])


def findings(graph, phases):
    from performance import result
    import warranty_terms as terms
    ledger=graph.get("warranty_sources",{})
    pages=ledger.get("register_pages",[])
    if ledger.get("format")!=FORMAT or not pages or not all(p["bounded"] for p in pages):
        return []
    by_role=defaultdict(list)
    for p in pages:
        by_role[p["role"]].append(p)
    if len(by_role["contract"])!=1 or len(by_role["warranty"])!=1:
        return []
    contract,release=by_role["contract"][0],by_role["warranty"][0]
    checked=[f for f in phases if f["rule"]=="H04" and f.get("warranty_check")]
    if len(checked)!=1:
        return []
    phase=checked[0]
    w=phase["warranty_check"]
    condition=w["condition_ref"]
    clause=phase["stage"]["clause_ref"]
    c,r=contract["refs"],release["refs"]
    eligible=r.get("warranty_release")==[w["confirmation_ref"]] and r.get("warranty_defects")==[w["defect_ref"]]
    if not (eligible and clause in c.get("clause",[]) and condition and w["requires_defect_clearance"] and
            (c.get("warranty_condition")==[condition] or condition==clause) and r.get("acceptance_signer")):
        return []
    facts={f["id"]:f for f in physical_facts(graph)}
    if any(ref not in facts for p in pages for refs in p["refs"].values() for ref in refs):
        return []
    def body(ref):
        return parts(facts[ref]["source_line"]["text"])[1]
    signed=facts[r["acceptance_signer"][0]]
    cert=terms.CONFIRM.fullmatch(body(w["confirmation_ref"]))
    confirmation=service.printed_date(cert[1]) if cert else None
    cutoff=w.get("at_submission",{}).get("as_of")
    if (not confirmation or confirmation!=w["confirmed_on"] or not cutoff or confirmation>cutoff or
            body(w["defect_ref"]).rstrip("。") not in CLEAR or w["at_submission"]["defects"]!="stated_clear" or
            not confirmed_signature(signed)):
        return []
    if not all(c.get(k) and r.get(k) and body(c[k][0])==body(r[k][0]) and not UNCERTAIN.search(body(c[k][0])) for k in LINK_KEYS):
        return []
    ticket_pages={p["doc"]:p for p in by_role[service.TITLE]}
    tickets=w.get("tickets",[])
    if (len(ticket_pages)!=len(by_role[service.TITLE]) or {t["unit"] for t in tickets}!=set(ticket_pages) or
            any(not t["number"] or not t["fault"] for t in tickets)):
        return []
    _,bounded=service.classified(ledger)
    numbers=Counter(t["number"].casefold() for t in tickets)
    components={}
    for t in tickets:
        match=FAULT.fullmatch(t["fault"])
        if match:
            part=match["part"]
            components[t["unit"]]={"风机":"风扇","传感器":"探头"}.get(part,part)
    output=[]
    for t in tickets:
        p=ticket_pages[t["unit"]]
        refs=t["refs"]
        number,fault,opened=t["number"],t["fault"],t["reported_on"]
        if not (t["unit"] in bounded and t["state"] in ("period","open") and t["linked"] and all(p["refs"].get(k)==[refs.get(k)] for k in (*LINK_KEYS,"warranty_ticket_id","warranty_fault","warranty_reported_on","warranty_ticket_state"))
                and numbers[number.casefold()]==1 and complete_id(number) and number[-1].isalnum() and not UNCERTAIN.search(number) and
                t["unit"] in components and t["printed_state"] in service.OPEN and
                not {"warranty_closed_on","warranty_closed_by"}.intersection(p["refs"]) and opened and opened<confirmation):
            continue
        if (w["accepted_on"] and opened<=w["accepted_on"] or w["calendar_end"] and opened>=w["calendar_end"] or
                any(other is not t and not other["identity_conflicts"] and
                    components.get(other["unit"]) in (None,components[t["unit"]]) for other in tickets)):
            continue
        refs_out={"condition":condition,"confirmation":w["confirmation_ref"],"defects":w["defect_ref"],
                  "ticket_id":refs["warranty_ticket_id"],"reported_on":refs["warranty_reported_on"],
                  "fault":refs["warranty_fault"],"ticket_state":refs["warranty_ticket_state"]}
        proof=[clause,*refs_out.values(),signed["id"]]
        for src in (contract,release,p):
            proof.extend([src["doc"],f"{src['doc']}/p{src['page']}",src["refs"][src["role"]][0]])
            proof.extend(src["refs"][k][0] for k in LINK_KEYS)
        detail=(f"期满确认单于 {confirmation} 载明“{body(w['defect_ref'])}”。工单 {number} 的报修日为 {opened}，"
                f"报修事项为“{fault}”，工单状态栏载“{t['printed_state']}”。请对照两份记载，查验该工单的后续处理和关闭签认。")
        entry=result("H07","risk",detail,proof,[contract["doc"],release["doc"],p["doc"]])
        entry["warranty_difference"]={"state":"record_difference","ticket_unit":p["doc"],"release_unit":release["doc"],
                                      "number":number,"reported_on":opened,"confirmed_on":confirmation,"printed_state":t["printed_state"],"refs":refs_out}
        output.append(entry)
    return output


def edges(findings):
    return [{"from":d["refs"]["defects"],"to":d["refs"]["ticket_state"],"type":EDGE,"evidence":f["evidence"]}
            for f in findings if f["rule"]=="H07" and (d:=f.get("warranty_difference"))]


def verify(report,read_layout=None):
    from config import TRAVEL
    from performance import compute
    graph=report["graph"]
    expected=[]
    if graph.get("warranty_sources",{}).get("register_pages") and graph.get("profile")!=TRAVEL:
        expected=[f for f in compute(graph,report["policy"]["performance_checks"]) if f["rule"]=="H07"]
    saved=[f for f in report["findings"] if f["rule"]=="H07" or "warranty_difference" in f]
    if len(saved)!=len(expected) or any(any(f.get(k)!=v for k,v in e.items()) for f,e in zip(saved,expected)):
        raise ValueError("期满确认与维修工单的记载差异未能按原行复算")
    for f in saved:
        release=f["warranty_difference"]["release_unit"]
        signer,=(fact for fact in graph["facts"] if fact["doc"]==release and fact["field"]=="acceptance_signer" and fact["id"] in f["evidence"])
        if not report.get("case_id") or signer["attestation"]["source_check"].get("case_id")!=report["case_id"]:
            raise ValueError("期满确认的核图签认与本底稿归属不符")
        if read_layout:
            cited=set(f["evidence"])
            for fact in graph["facts"]:
                if fact["id"] in cited:
                    loc=fact["source_line"]
                    original=read_layout(fact["doc"],fact["page"]) or {}
                    if original.get("lines",{}).get(str(loc["number"]))!=loc["rects"]:
                        raise ValueError("质保记载差异的引文定位与登记原页不符")
        target="finding/"+f["id"]
        control=[n for n in graph["nodes"] if n["id"]=="control/H07"]
        if (control!=[{"id":"control/H07","type":"control","label":"H07","version":report["policy"]["version"],"basis":RULE[1]}] or
                f.get("version")!=report["policy"]["version"] or f.get("title")!=RULE[0] or f.get("basis")!=RULE[1]):
            raise ValueError("质保记载差异的程序身份与本版方法不符")
        supports=[e for e in graph["edges"] if e["to"]==target and e["type"]=="supports_result"]
        proof=[{"type":"supports_result","from":ref,"to":target,"evidence":[ref]} for ref in f["evidence"]]
        procedure=[e for e in graph["edges"] if e["type"]=="procedure_result" and e["to"]==target]
        nodes=[n for n in graph["nodes"] if n["id"]==target]
        if (sorted(supports,key=lambda e:e["from"])!=sorted(proof,key=lambda e:e["from"]) or
                procedure!=[{"type":"procedure_result","from":"control/H07","to":target,"evidence":f["evidence"]}] or
                len(nodes)!=1 or any(nodes[0].get(k)!=v for k,v in {"type":"finding","label":RULE[0],"status":"risk","detail":f["detail"]}.items())):
            raise ValueError("质保记载差异缺少本条程序、结论或支持原行")


def legacy_signoff(report,read_text,submitted):
    """Only stop a signature for a newly provable difference this workpaper did not flag."""
    from performance import compute
    from payment_releases import submission_day
    import warranty_terms as terms
    graph=report["graph"]
    ledger=terms.sources(graph,read_text,FORMAT)
    if not ledger.get("register_pages"):
        return
    updated={**graph,"warranty_sources":ledger,"warranty_as_of":submission_day(submitted) if submitted else graph.get("warranty_as_of")}
    results=compute(updated,report["policy"]["performance_checks"])
    issued=report["findings"]
    for finding in findings(updated,results):
        diff=finding["warranty_difference"]
        for row in issued:
            w=row.get("warranty_check",{})
            if (row["rule"]=="H04" and row["status"]=="risk" and w.get("status")=="risk" and
                    w.get("defect_ref")==diff["refs"]["defects"] and w.get("confirmation_ref")==diff["refs"]["confirmation"] and
                    any(e["type"]=="warranty_ticket_comparison" and e["from"]==row["stage"]["clause_ref"] and
                        e["to"]==diff["refs"]["ticket_state"] and set(diff["refs"].values())<=set(e["evidence"])
                        for e in graph["edges"]) and
                    any(t["unit"]==diff["ticket_unit"] and t["state"]=="open" and t["status"]=="risk" and
                        t["refs"].get("warranty_ticket_state")==diff["refs"]["ticket_state"] for t in w.get("tickets",[]))):
                break
        else:
            raise ValueError("旧版底稿未揭示同一标的期满确认单与维修工单的记载差异，请重新审计后签收。")
