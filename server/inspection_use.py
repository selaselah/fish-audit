"""Compare the stated use of an inspection document with a bank receipt explicitly citing it."""
from collections import defaultdict
from hashlib import sha256
import re

from contract_folios import line_numbers, verify_page_geometry
from delegation import is_page_marker
from delivery_batches import NUM, ordinal
from payment_acceptance import GRAPH_KEY, LEVEL


FORMAT = "cited-inspection-payment-use-v1"
KEY = "inspection_use_sources"
RECTS = "inspection_use_rects"
SINCE = (2026, 11, 27, 19)
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


def sources(graph, read_text, read_layout):
    from graph import LABELS, PRINTED_TITLES
    ledger = {"format":FORMAT, "rows":[]}
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
    return ledger


def source_graph(ledger):
    nodes, edges = [], []
    for r in ledger["rows"]:
        page = f"{r['doc']}/p{r['page']}"
        nodes.append({"id":r["id"],"type":"inspection_use_line","label":r["quote"],"doc":r["doc"],"page":r["page"],"line":r["line"]})
        edges.append({"type":"inspection_use_source","from":page,"to":r["id"],"evidence":[page,*r["facts"]]})
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
    rows = graph.get(KEY,{}).get("rows",())
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
        reviews = [d for d in graph.get("acceptance_word_reviews",{}).get("documents",())
                   if cited in d["units"] and (d["notes"] or d["coverage"] != "complete")]
        for r in rows:
            if r["unit"] not in units:
                continue
            if r["unit"]!=cited and r["kind"]=="approval" and not re.search(SHEET,r["quote"]):
                scope = "unresolved"
            elif r["unit"]!=cited:
                scope = "other_document"
            elif r["disputed"] or not r["rects"] or reviews:
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
        yield f, {"format":FORMAT,"bank":bank,"cited":cited,"citation":citation,"number_ref":number_ref,"number":number,
                  "state":state,"status":status,"notes":notes,"evidence":list(dict.fromkeys(refs))}


WORDING = {"ban":"该单明示不得作为本期付款依据，与回单所引用途相冲突，请核实实际付款凭据及审批。",
    "approval":"该单写明本期付款须另行审批，请调取审批原件，核对审批人权限、签批与扣款先后。",
    "conditional":"该单对用于本期付款附有签批条件，请核实付款时是否已满足。",
    "unclear":"验收资料中付款用途的适用范围或签批条件待核，请核对原件及审批记录。",
    "other_stage":"所引单据的用途附注明确列了其他期次。",
    "other_document":"另有验收单写有付款用途附注，请分别核对两份原件。"}


def apply(graph, findings):
    for f,c in checks(graph,findings):
        f["inspection_use"]=c
        f["detail"]+=" "+WORDING[c["state"]]
        if LEVEL[c["status"]]>LEVEL[f["status"]]:
            f["status"]=c["status"]
        f["evidence"]=list(dict.fromkeys([*f["evidence"],*c["evidence"]]))


def edges(findings):
    return [{"type":"cites_inspection_use","from":c["citation"],"to":n["row"],"evidence":[c["citation"],c["number_ref"],n["row"]]}
            for f in findings if (c:=f.get("inspection_use")) for n in c["notes"] if n["scope"]=="cited"]


def verify_originals(report, read_original):
    from payment_quality import verify_units

    graph = report["graph"]
    checks = [f["inspection_use"] for f in report["findings"] if f.get("inspection_use")]
    if not checks:
        return
    ids = {note["row"] for c in checks for note in c["notes"]}
    rows = [r for r in graph[KEY]["rows"] if r["id"] in ids]
    if {r["id"] for r in rows} != ids:
        raise ValueError("已引用的验收单付款用途原行缺失")
    units = {c["bank"] for c in checks} | {c["cited"] for c in checks} | {r["unit"] for r in rows}
    verify_units(graph, units | set(graph["documents_by_kind"]["contract"]), read_original, "验收单付款用途", extra_lines=rows)


def verify(report, read_text, *, read_layout=None, signing=False):
    g,p,fs = report["graph"],report["policy"],report["findings"]
    calls = report.get("calls",{}).get("pages",[])
    actual_nodes = [n for n in g["nodes"] if n["type"]=="inspection_use_line"]
    source_edges = [e for e in g["edges"] if e["type"]=="inspection_use_source"]
    links = [e for e in g["edges"] if e["type"]=="cites_inspection_use"]
    claims = {f["id"]:f["inspection_use"] for f in fs if "inspection_use" in f}
    by_page = {(c["doc"],c["page"]):c for c in calls}
    layout = read_layout or (lambda d,n:{"lines":by_page.get((d,n),{}).get(RECTS,{})})
    if tuple(map(int,p.get("version","0").split(".")))<SINCE:
        if KEY in g or p.get("inspection_use") or "inspection_use.py" in p.get("code_sha256",{}) or claims or actual_nodes or source_edges or links or any(RECTS in c for c in calls):
            raise ValueError("历史底稿含未出具的验收单付款用途判断")
        if signing and any(f["rule"]=="H05" and reference(f) for f in fs):
            current={**g,KEY:sources(g,read_text,layout)}
            if any(c["status"]=="risk" or f["status"]=="ok" and c["status"]=="missing" for f,c in checks(current,fs)):
                raise ValueError("旧底稿所引验收单另有付款用途限制，请重审后签收")
        return
    ledger=sources(g,read_text,layout)
    if (p.get("inspection_use")!=FORMAT or "code_sha256" in p and "inspection_use.py" not in p["code_sha256"] or
            g.get(KEY)!=ledger or (actual_nodes,source_edges)!=source_graph(ledger) or links!=edges(fs)):
        raise ValueError("验收单付款用途原文、方法或图关系不符")
    expected={f["id"]:c for f,c in checks(g,fs)}
    if claims!=expected or any(LEVEL[f["status"]]<LEVEL[c["status"]] or not set(c["evidence"])<=set(f["evidence"])
                              for f in fs if (c:=expected.get(f["id"]))):
        raise ValueError("付款用途与所引验收单、付款期次或原行不符")
    if "calls" in report:
        supported = {(e["from"], e["to"]) for e in g["edges"] if e["type"] == "supports_result" and e["evidence"] == [e["from"]]}
        if any((ref, "finding/" + fid) not in supported for fid,c in expected.items() for ref in c["evidence"]):
            raise ValueError("本期付款发现与验收单用途原行之间的依据缺失")
        coords=defaultdict(dict)
        for r in ledger["rows"]:
            if r["page_sha256"]!=by_page.get((r["doc"],r["page"]),{}).get("page_sha256"):
                raise ValueError("验收单用途所据页图与调用记录不符")
            if r["rects"]:
                coords[r["doc"],r["page"]][str(r["line"])]=r["rects"]
        verify_page_geometry(calls,line_numbers(ledger["rows"]),coords,RECTS,"验收单付款用途",read_layout)
