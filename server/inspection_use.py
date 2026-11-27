"""Compare the stated use of an inspection document with a bank receipt explicitly citing it."""
from collections import defaultdict
from hashlib import sha256
import re

import installment_approval
import approval_clock
import approval_names
import approval_changes
from contract_folios import line_numbers, verify_page_geometry
from delegation import is_page_marker
from delivery_batches import NUM, ordinal
from payment_acceptance import GRAPH_KEY, LEVEL


FIRST_FORMAT = "cited-inspection-payment-use-v1"
CROSS_FORMAT = "cited-inspection-payment-use-v2"
APPROVAL_FORMAT = "cited-inspection-payment-use-v3"
CLOCK_FORMAT = "cited-inspection-payment-use-v4"
NAMES_FORMAT = approval_names.FIRST_FORMAT
UNNAMED_FORMAT = approval_names.FORMAT
FORMAT = approval_changes.FORMAT
KEY = "inspection_use_sources"
RECTS = "inspection_use_rects"
SINCE = (2026, 11, 27, 19)
CROSS_DOCUMENT_SINCE = (2026, 11, 27, 20)
APPROVAL_SINCE = (2026, 11, 27, 21)
CLOCK_SINCE = (2026, 11, 27, 24)
NAMES_SINCE = (2026, 11, 28, 1)
UNNAMED_SINCE = (2026, 11, 28, 2)
CHANGES_SINCE = (2026, 11, 28, 3)
SCOPE_SINCE = (2026, 11, 28, 4)
JOINT_SINCE = (2026, 11, 28, 8)
PURPOSE_HEADINGS = {"用途说明", "付款用途说明", "付款依据说明", "审批说明", "凭证用途", "用途限制"}
HEADINGS = PURPOSE_HEADINGS | {"付款说明", "付款意见", "验收备注", "复验备注"}
SHEET = r"本(?:单|报告|复验单|复验报告|验收单|验收报告)"
PHASE = rf"(?:第(?P<index>{NUM})期)?(?P<role>验收款|预付款|质保金)?"
BAN = re.compile(SHEET+r"(?:不得|不能|不可|不)(?:作|用)为"+PHASE+r"(?:的)?(?:付款|支付)依据")
APPROVAL = re.compile(r"(?:"+SHEET+r"仅确认(?:质量|验收结果)[，,])?"+PHASE+r"(?:付款)?(?:须|需)(?:另经|另行取得|另由)(?:甲方)?(?P<authority>财务负责人|有权审批人|总经理)(?:书面)?(?:审批|批准)")
CONDITIONAL = re.compile(r"未经(?:甲方)?(?P<authority>财务负责人|有权审批人|总经理)(?:签字|审批|批准)[，,]"+BAN.pattern)
HINT = re.compile(r"(?:付款|支付)(?:的)?(?:依据|授权|批准)|(?:另经|另由|另行|尚须|未经).{0,18}(?:审批|批准|签字)|"
                  r"(?:前款|上述限制|上述说明|本限制).{0,22}(?:除外|豁免|例外|取消|作废|解除)|"
                  r"(?:作为|用作).{0,18}(?:付款|支付)凭证|(?:仅供|仅用于|不得据此|禁止据此).{0,26}(?:付款|支付)")


def classify(quote):
    parts = re.split(r"[：:]", quote, maxsplit=1)
    label = parts[0].strip() if len(parts) == 2 else ""
    body = parts[-1].strip().removesuffix("。")
    for kind, pattern in (("conditional",CONDITIONAL),("ban",BAN),("approval",APPROVAL)):
        m = pattern.fullmatch(body)
        if m and (not label or label in HEADINGS):
            index = ordinal(m["index"]) if m["index"] else None
            if m["index"] and not index:
                break
            return kind, index, m["role"], m.groupdict().get("authority")
    if HINT.search(quote) or label in PURPOSE_HEADINGS and re.search(r"审批|批准|付款|支付|凭证|例外|除外",body):
        return "unclear", None, None, None
    return None


def sources(graph, read_text, read_layout, version=FORMAT):
    from graph import LABELS, PRINTED_TITLES
    ledger = {"format":version, "rows":[]}
    with_changes=version in (approval_changes.FIRST_FORMAT,*approval_changes.SCOPED)
    with_names=with_changes or version in (NAMES_FORMAT,UNNAMED_FORMAT)
    with_time=with_names or version==CLOCK_FORMAT
    if with_names:
        terms=approval_names.pages(graph,read_text,read_layout)
        if terms:
            ledger["approver_terms"]=terms
    if with_changes and ledger.get("approver_terms"):
        changes=approval_changes.pages(graph,read_text,read_layout)
        if changes:ledger["approver_changes"]=changes
    if not any(r["role"]=="bank_receipt" and r["kind"]=="citation" for r in graph.get(GRAPH_KEY,{}).get("rows",())):
        return ledger
    nodes = {p["id"]:p for p in graph["nodes"] if p["type"]=="page"}
    observations = defaultdict(list)
    for f in graph["facts"]:
        if point := f.get("source_line"):
            observations[f["doc"],f["page"],point["number"]].append(f)
    known = {label for labels in LABELS.values() for label in labels}
    by_unit = defaultdict(list)
    for p in graph.get("payment_window_sources",{}).get("pages",()):
        if not p["native"] or p["document_kind"] not in ("acceptance","reinspection"):
            continue
        unit, doc, n = p["unit"], p["doc"], p["page"]
        node = nodes[f"{doc}/p{n}"]
        text = read_text(doc,n)
        if not isinstance(text,str) or sha256(text.encode()).hexdigest()!=node["text_sha256"]:
            raise ValueError("验收单付款用途所据原文与底稿摘要不符")
        for i, raw in enumerate(text.splitlines(),1):
            label = re.split("[:：]",raw,maxsplit=1)[0].strip()
            parsed = classify(raw)
            opinion = label in HEADINGS and re.search(r"同意|暂缓|准予|禁止|作废|解除",raw)
            if not parsed and not opinion and (not raw.strip() or is_page_marker(raw) or raw.strip() in PRINTED_TITLES or label in known):
                continue
            kind,index,role,authority = parsed or ("rider",None,None,None)
            seen = [f for f in observations[doc,n,i] if f["source_line"]["text"]==raw]
            by_unit[unit].append({"id":f"inspection-use/{doc}/p{n}/l{i}", "unit":unit, "doc":doc, "page":n, "line":i,
                "quote":raw, "kind":kind, "index":index, "role":role, "authority":authority, "facts":[f["id"] for f in seen],
                "disputed":any(f["status"]=="disputed" for f in seen), "page_sha256":node["sha256"]})
    for rows in by_unit.values():
        if any(r["kind"]!="rider" for r in rows):
            for r in rows:
                r["rects"]=read_layout(r["doc"],r["page"]).get("lines",{}).get(str(r["line"]),[])
            ledger["rows"].extend(rows)
    if (with_time or version==APPROVAL_FORMAT) and any(r["kind"]=="approval" for r in ledger["rows"]):
        ledger["approvals"]=installment_approval.sources(graph,read_text,read_layout,with_time=with_time,with_names=with_names)
        if with_time and ledger["approvals"]:
            ledger["bank_clocks"]=approval_clock.bank_pages(graph,read_text,read_layout)
    return ledger


def all_rows(ledger):
    return [*ledger["rows"],*(r for key in ("approvals","bank_clocks","approver_terms","approver_changes") for p in ledger.get(key,()) for r in p["rows"])]


def source_graph(ledger):
    nodes, edges = [], []
    for r in all_rows(ledger):
        page = f"{r['doc']}/p{r['page']}"
        kind = {"contract-approver":"contract_approver","payment-clock":"payment_clock","payment-approval":"payment_approval",
                "approval-change":"approval_change","inspection-use":"inspection_use"}[r["id"].split("/")[0]]
        nodes.append({"id":r["id"],"type":kind+"_line","label":r["quote"],"doc":r["doc"],"page":r["page"],"line":r["line"]})
        edges.append({"type":kind+"_source","from":page,"to":r["id"],"evidence":[page,*r["facts"]]})
    return nodes,edges


def reference(f):
    r = f.get("retest_reference")
    if r and r["state"] in ("original","final"):
        units = r["units"]
        return r["bank"],r["fields"]["citation"],r["number"],units[r["state"]],{units["original"],units["final"]},r["fields"][r["state"]+"_acceptance_number"]
    b = f.get("payment_acceptance")
    if b and b["state"] in ("matched","other_batch") and len(b["cited"])==len(b["citations"])==1:
        unit, = b["cited"]
        own = next((r for r in b["register"] if r["unit"]==unit and r["identified"]),None)
        if own:
            return b["bank"],b["citations"][0],b["number"],unit,{r["unit"] for r in b["register"]},own["number_row"]
    return None


def checks(graph, findings):
    ledger = graph.get(KEY,{})
    rows = ledger.get("rows",())
    if not rows:
        return
    for f in findings:
        if f["rule"]!="H05" or not f.get("stage") or f.get("execution_basis") or not (link:=reference(f)):
            continue
        bank,citation,number,cited,units,number_ref = link
        if not {citation,number_ref}<=set(f["evidence"]):
            continue
        stage = re.fullmatch("第("+NUM+")期",f["stage"]["name"])
        index = ordinal(stage[1]) if stage else None
        notes,refs,active = [],[citation,number_ref,f["stage"]["clause_ref"]],[]
        review_units = {cited}
        if ledger["format"] != FIRST_FORMAT:
            review_units.update(r["unit"] for r in rows if r["unit"] in units)
        reviews = [d for d in graph.get("acceptance_word_reviews",{}).get("documents",())
                   if review_units.intersection(d["units"]) and (d["notes"] or d["coverage"] != "complete")]
        for r in rows:
            if r["unit"] not in units:
                continue
            review = any(r["unit"] in d["units"] for d in reviews)
            if r["unit"] != cited:
                if ledger["format"] == FIRST_FORMAT:
                    local = r["kind"] != "approval" or bool(re.search(SHEET,r["quote"]))
                else:
                    # A note filed on the initial sheet can explicitly govern a different sheet or the whole installment.
                    initial = f.get("retest_reference",{}).get("units",{}).get("original")
                    foreign_title = r["unit"] == initial and re.search(r"本复验(?:单|报告)", r["quote"])
                    local = r["kind"] in ("ban","conditional") and r["rects"] and not (r["disputed"] or foreign_title or review)
                scope = "other_document" if local else "unresolved"
            elif r["disputed"] or not r["rects"] or review:
                scope = "unresolved"
            elif r["index"] and index and r["index"]!=index:
                scope = "other_stage"
            elif r["kind"] in ("rider","unclear") or not index or r["role"] not in (None,"验收款"):
                scope = "unresolved"
            else:
                scope = "cited"
            notes.append({"row":r["id"],"scope":scope})
            refs.extend([r["id"],f"{r['doc']}/p{r['page']}",*r["facts"]])
            if scope in ("cited","unresolved"):
                active.append(r["kind"] if scope=="cited" else "unclear")
        if not notes:
            continue
        refs.extend(ref for d in reviews for ref in (d["id"],*(n["id"] for n in d["notes"])))
        state = "other_document" if all(n["scope"]=="other_document" for n in notes) else "other_stage"
        if active:
            state = active[0] if len(active)==1 else "unclear"
        status = "risk" if state=="ban" else "missing" if active else "ok"
        check = {"format":ledger["format"],"bank":bank,"cited":cited,"citation":citation,"number_ref":number_ref,"number":number,
                 "state":state,"status":status,"notes":notes,"evidence":list(dict.fromkeys(refs))}
        if state=="approval" and ledger.get("approvals"):
            required = next(r for r in rows if r["kind"]=="approval" and {"row":r["id"],"scope":"cited"} in notes)
            approval = installment_approval.compare(graph,f,check,required,ledger["approvals"])
            check["approval"]=approval
            check["status"]=approval["status"]
            check["evidence"]=list(dict.fromkeys([*check["evidence"],*approval["evidence"]]))
        yield f,check


WORDING = {"ban":"该单明示不得作为本期付款依据，与回单所引用途相冲突，请核实实际付款凭据及审批。",
    "approval":"该单写明本期付款须另行审批，请调取审批原件，核对审批人权限、签批与扣款先后。",
    "conditional":"该单对用于本期付款附有签批条件，请核实付款时是否已满足。",
    "unclear":"验收资料中付款用途的适用范围或签批条件待核，请核对原件及审批记录。",
    "other_stage":"所引单据的用途附注明确列了其他期次。",
    "other_document":"另有验收单写有付款用途附注，请分别核对两份原件。"}


def apply(graph, findings):
    for f,c in checks(graph,findings):
        f["inspection_use"]=c
        detail = installment_approval.WORDING[c["approval"]["state"]] if "approval" in c else WORDING[c["state"]]
        if clock:=c.get("approval",{}).get("clock"):
            detail=approval_clock.WORDING[clock["state"]]
        if names:=c.get("approval",{}).get("names"):
            detail+=" "+(approval_names.joint_detail(names) if names["state"]=="joint_difference" else approval_names.WORDING[names["state"]])
        f["detail"]+=" "+detail
        if LEVEL[c["status"]]>LEVEL[f["status"]]:
            f["status"]=c["status"]
        f["evidence"]=list(dict.fromkeys([*f["evidence"],*c["evidence"]]))


def edges(findings):
    links=[]
    for f in findings:
        if c:=f.get("inspection_use"):
            links.extend({"type":"cites_inspection_use","from":c["citation"],"to":n["row"],"evidence":[c["citation"],c["number_ref"],n["row"]]}
                         for n in c["notes"] if n["scope"]=="cited")
            if a:=c.get("approval"):
                links.extend({"type":"compares_payment_approval","from":a["request"],"to":row,"evidence":[a["request"],c["citation"],row]}
                             for row in a["rows"])
                if name_link:=approval_names.edge(a,c,f["stage"]):
                    links.append(name_link)
                clock=a.get("clock",{})
                if clock.get("state") in {"debit_first","approval_first","overlap"}:
                    links.append({"type":"compares_debit_time","from":clock["signed"],"to":clock["debit"],
                                  "evidence":[a["request"],c["citation"],clock["signed"],clock["debit"]]})
    return links+approval_changes.edges(findings)


def verify_originals(report, read_original):
    from payment_quality import verify_units

    graph = report["graph"]
    checks = [f["inspection_use"] for f in report["findings"] if f.get("inspection_use")]
    ledger = graph.get(KEY,{"rows":[]})
    requires_approval = any(row["kind"]=="approval" for row in ledger["rows"])
    timing = [pair["event"] for f in report["findings"] for kind in ("retest_reference","payment_acceptance")
              for pair in f.get(kind,{}).get("timing_notes",())]
    if not checks and not requires_approval and not ledger.get("approver_terms") and not timing:
        return
    ids = {note["row"] for c in checks for note in c["notes"]}
    ids.update(r for c in checks for r in c.get("approval",{}).get("rows",()))
    ids.update(r for c in checks for r in c.get("approval",{}).get("clock",{}).get("rows",()))
    ids.update(r for c in checks for r in c.get("approval",{}).get("names",{}).get("rows",()))
    ids.update(r["id"] for p in ledger.get("approver_terms",()) for r in p["rows"])
    ids.update(r["id"] for p in ledger.get("approver_changes",()) for r in p["rows"])
    for f in report["findings"]:
        if change:=f.get("approval_change"):
            ids.update(ref for ref in change["evidence"] if ref.startswith(("inspection-use/","payment-approval/","payment-clock/","contract-approver/","approval-change/")))
    ids.update(timing)
    rows = [r for r in all_rows(ledger) if r["id"] in ids]
    if {r["id"] for r in rows} != ids:
        raise ValueError("已引用的验收单付款用途原行缺失")
    units = {c["bank"] for c in checks} | {c["cited"] for c in checks} | {r["unit"] for r in rows}
    if requires_approval or ledger.get("approver_changes"):
        # The choice of a separate approval depends on which instruments were filed.
        units.update(p["unit"] for p in graph["payment_window_sources"]["pages"])
    verify_units(graph, units | set(graph["documents_by_kind"]["contract"]), read_original, "验收单付款用途", extra_lines=rows)


def guard_legacy_approval(graph, ledger, read_text, layout, policy, findings):
    from performance import FORMAT as PERFORMANCE_FORMAT, compute

    if policy.get("performance_checks")!=PERFORMANCE_FORMAT:
        return
    current = {**graph, KEY:sources(graph,read_text,layout)}
    if current[KEY].get("approver_terms"):
        from acceptance_authority import coverage_gaps, page_evidence
        signers=page_evidence(current,read_text)
        current["acceptance_authority_sources"]=signers
        current["gaps"]=[g for g in graph["gaps"] if g["quality"]!="acceptance_authority_clause"]+coverage_gaps(signers)
    if current[KEY].get("approver_terms") or installment_approval.recognized(current):
        revised=compute(current)
        prior={(f["rule"],f["stage"]["clause_ref"],tuple(f["scope"])) for f in findings if f.get("stage") and f["status"]=="ok"}
        if any(f.get("stage_approvers") and f["status"]!="ok" and (f["rule"],f["stage"]["clause_ref"],tuple(f["scope"])) in prior for f in revised):
            raise ValueError("旧底稿尚未覆盖合同为本期指定的签批人，请重审后签收")
        def risks(items):
            for f in items:
                use=f.get("inspection_use",{})
                approval=use.get("approval",{})
                grounds=(approval.get("state"),approval.get("clock",{}).get("state"),approval.get("names",{}).get("state"))
                for ground in grounds:
                    if ground in {"later","refused","debit_first","different","joint_difference"}:
                        yield (use["bank"],use["citation"],approval["request"],ground)
        if set(risks(revised))-set(risks(findings)):
            raise ValueError("旧底稿所附付款审批单的决定、日期、签发时刻或具名签批依据存在新的风险，请重审后签收")
        def change_risks(items):
            return {(c["fields"]["revised"],c["approval_fields"]["date"],c["issued_on"],c["last_seal_on"],reason)
                    for f in items if (c:=f.get("approval_change")) and c["status"]=="risk"
                    for reason in ("printed_difference","refused","early_debit") if c.get(reason)}
        if change_risks(revised)-change_risks(findings):
            raise ValueError("旧底稿尚未核对签批人变更与实际付款所附审批的在先依据，请重审后签收")
        if ledger.get("format")==approval_changes.FIRST_FORMAT and any(f.get("approval_change_scope") for f in revised):
            if any(f.get("payment_acceptance",{}).get("state")=="reference" for f in findings) and any(
                    f.get("retest_reference",{}).get("state")=="final" for f in revised):
                raise ValueError("旧版将扣款时刻列入验收单号候选，现已定位回单所引复验原件，请重审后签收")
        if ledger.get("format")==NAMES_FORMAT:
            for f in findings:
                names=f.get("inspection_use",{}).get("approval",{}).get("names",{})
                if any(not approval_names.name(n) for k in ("required","listed") for n in names.get(k,())):
                    raise ValueError("旧底稿将岗位或占位文字作为本期签批姓名，请重审后签收")


def verify(report, read_text, *, read_layout=None, signing=False):
    g,p,fs = report["graph"],report["policy"],report["findings"]
    calls = report.get("calls",{}).get("pages",[])
    actual_nodes = [n for n in g["nodes"] if n["type"] in ("inspection_use_line","payment_approval_line","payment_clock_line","contract_approver_line","approval_change_line")]
    source_edges = [e for e in g["edges"] if e["type"] in ("inspection_use_source","payment_approval_source","payment_clock_source","contract_approver_source","approval_change_source")]
    links = [e for e in g["edges"] if e["type"] in ("cites_inspection_use","compares_payment_approval","compares_debit_time","compares_approval_names","dates_approval_change")]
    claims = {f["id"]:f["inspection_use"] for f in fs if "inspection_use" in f}
    by_page = {(c["doc"],c["page"]):c for c in calls}
    layout = read_layout or (lambda d,n:{"lines":by_page.get((d,n),{}).get(RECTS,{})})
    revision = tuple(map(int,p.get("version","0").split(".")))
    if "code_sha256" in p and ("installment_approval.py" in p["code_sha256"]) != (revision>=APPROVAL_SINCE):
        raise ValueError("付款审批核对程序与底稿版本不符")
    if "code_sha256" in p and ("approval_clock.py" in p["code_sha256"]) != (revision>=CLOCK_SINCE):
        raise ValueError("扣款时刻核对程序与底稿版本不符")
    if "code_sha256" in p and ("approval_names.py" in p["code_sha256"]) != (revision>=NAMES_SINCE):
        raise ValueError("合同具名签批程序与底稿版本不符")
    if "code_sha256" in p and ("approval_changes.py" in p["code_sha256"]) != (revision>=CHANGES_SINCE):
        raise ValueError("签批约定变更程序与底稿版本不符")
    if revision<SINCE:
        if KEY in g or p.get("inspection_use") or "inspection_use.py" in p.get("code_sha256",{}) or claims or actual_nodes or source_edges or links or any(RECTS in c for c in calls):
            raise ValueError("历史底稿含未出具的验收单付款用途判断")
        if signing and any(f["rule"]=="H05" for f in fs):
            current={**g,KEY:sources(g,read_text,layout)}
            guard_legacy_approval(g,current[KEY],read_text,layout,p,fs)
            if any(c["status"]=="risk" or f["status"]=="ok" and c["status"]=="missing" for f,c in checks(current,fs)):
                raise ValueError("旧底稿所引验收单另有付款用途限制，请重审后签收")
        return
    version=next((fmt for since,fmt in ((JOINT_SINCE,FORMAT),(SCOPE_SINCE,approval_changes.SCOPE_FORMAT),(CHANGES_SINCE,approval_changes.FIRST_FORMAT),(UNNAMED_SINCE,UNNAMED_FORMAT),(NAMES_SINCE,NAMES_FORMAT),(CLOCK_SINCE,CLOCK_FORMAT),
                 (APPROVAL_SINCE,APPROVAL_FORMAT),(CROSS_DOCUMENT_SINCE,CROSS_FORMAT)) if revision>=since),FIRST_FORMAT)
    ledger=sources(g,read_text,layout,version)
    if (p.get("inspection_use")!=version or "code_sha256" in p and "inspection_use.py" not in p["code_sha256"] or
            g.get(KEY)!=ledger or (actual_nodes,source_edges)!=source_graph(ledger) or links!=edges(fs)):
        raise ValueError("验收单付款用途原文、方法或图关系不符")
    expected={f["id"]:c for f,c in checks(g,fs)}
    if claims!=expected or any(LEVEL[f["status"]]<LEVEL[c["status"]] or not set(c["evidence"])<=set(f["evidence"])
                              for f in fs if (c:=expected.get(f["id"]))):
        raise ValueError("付款用途与所引验收单、付款期次或原行不符")
    for f in fs:
        change=None
        if ledger.get("approver_changes") and f["rule"] in ("H04","H05") and f.get("stage_approvers"):
            change=approval_changes.inspect(g,f)
            if change:change["evidence"]=list(dict.fromkeys(change["evidence"]))
        if f.get("approval_change")!=change or change and (LEVEL[f["status"]]<LEVEL[change["status"]]
                or not set(change["evidence"])<=set(f["evidence"]) or not set(change["documents"])<=set(f["scope"])):
            raise ValueError("本期签批变更、审批日期或两张名单与原行不符")
        if scope:=f.get("approval_change_scope"):
            terms=[s["approval_change"] for s in fs if s["rule"]=="H04" and s.get("approval_change",{}).get("state")=="terms"
                   and s["stage"]["clause_ref"]==scope.get("clause_ref") and s["stage"]["name"]==scope.get("stage")]
            if (version not in approval_changes.SCOPED or f["rule"] not in ("H02","H03") or len(terms)!=1 or terms[0]["fields"]["scope"]!=scope.get("scope_ref")
                    or terms[0]["execution"]!=scope.get("execution") or terms[0]["documents"]!=[scope.get("unit")]
                    or scope["unit"] not in f["scope"] or terms[0]["evidence"]!=scope.get("evidence")
                    or not set(scope["evidence"])<=set(f["evidence"])):
                raise ValueError("履约或分期检查所据补充协议范围与合同原行不符")
    if "calls" in report:
        supported = {(e["from"], e["to"]) for e in g["edges"] if e["type"] == "supports_result" and e["evidence"] == [e["from"]]}
        if any((ref, "finding/" + fid) not in supported for fid,c in expected.items() for ref in c["evidence"]):
            raise ValueError("本期付款发现与验收单用途原行之间的依据缺失")
        if any((ref,"finding/"+f["id"]) not in supported for f in fs for ref in f.get("evidence",())
               if ref.startswith(("contract-approver/","approval-change/")) or ref in f.get("approval_change",{}).get("evidence",())):
            raise ValueError("本期合同签批条款与发现之间缺少原行依据")
        coords=defaultdict(dict)
        rows = all_rows(ledger)
        for r in rows:
            if r["page_sha256"]!=by_page.get((r["doc"],r["page"]),{}).get("page_sha256"):
                raise ValueError("验收单用途所据页图与调用记录不符")
            if r["rects"]:
                coords[r["doc"],r["page"]][str(r["line"])]=r["rects"]
        verify_page_geometry(calls,line_numbers(rows),coords,RECTS,"验收单付款用途",read_layout)
    if signing and version == FIRST_FORMAT:
        current = {**g,KEY:{**ledger,"format":CROSS_FORMAT}}
        for f,updated in checks(current,fs):
            if expected[f["id"]]["status"] == "ok" and updated["status"] != "ok":
                raise ValueError("旧底稿将另一份验收单的付款附注列作仅适用于原单，其所指单据或本期审批范围待核，请重审后签收")
    if signing and version!=FORMAT:
        guard_legacy_approval(g,ledger,read_text,layout,p,fs)
