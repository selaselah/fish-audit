"""Find additional effectiveness conditions on every page attributed to the contract."""

import hashlib
import re
from collections import defaultdict

from acceptance_authority import parts
from performance_versions import EFFECT_FORMATS
from calculations import normalized


FORMAT = "contract-effect-sources-v1"
PERFORMANCE = "contract-performance-v11"
APPROVAL = re.compile(r"批准|审批|核准|许可|备案|公证|登记")
QUALIFIER = re.compile(r"附加条件|生效要件|效力|特别约定|附注|备注")
STATE = re.compile(r"(?:本合同|原合同|本协议|合同|协议).{0,12}(?:已(?:经)?(?:解除|终止|撤销|作废|失效|到期)|无效|效力待定|暂停履行)")
PAYMENT_LABEL = re.compile(r"第[一二两三四五六七八九十0-9]{1,3}期|付款条款|结算条款|付款期次|预付款|首付款")


def relevant(raw):
    from performance import stage_terms
    line=normalized(raw).strip("。")
    label,body=parts(raw)
    if PAYMENT_LABEL.fullmatch(label) and body:
        terms=re.split(r"[;,，。]",normalized(body).rstrip("。"))
        if all(stage_terms(term)[1] for term in terms):
            return False
        line=re.sub(r"(?:本)?合同生效(?=(?:之日)?[起后]|(?:且|并)(?:已)?(?:开票|收到发票))","",line)
    if "生效" in line or STATE.search(line) or "效力待定" in line:
        return True
    if APPROVAL.search(line) and not re.search(r"付款|支付|验收|交付",line):
        return bool(QUALIFIER.search(label) or not body and re.search(r"另须|另需|尚须|须经|必须取得|仍须|尚待",line))
    return False


def recognized(raw,facts):
    from performance import BOARD_CONDITION, EFFECT, LABELS, day
    label,body=parts(raw)
    body=body.rstrip("。")
    for fact in facts:
        if fact["status"] not in ("anchored","confirmed") or not (fact.get("source_line") or {}).get("rects"):
            continue
        if normalized(fact["value"]).rstrip("。") not in (normalized(raw).rstrip("。"),normalized(body)):
            continue
        field=fact["field"]
        if field=="effect_clause" and (label in LABELS[field] or not body):
            clause=body or raw.strip().rstrip("。")
            if EFFECT.fullmatch(clause) or BOARD_CONDITION.fullmatch(clause):
                return True
        if field=="effect_on" and label in LABELS[field] and day(body):
            return True
        if field=="contract_state" and label in LABELS[field] and body in {"已生效","有效","已签署","已签订","履行中"}:
            return True
    return False


def sources(graph,read_text):
    contracts=set(graph["documents_by_kind"].get("contract",[]))
    sections={(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents",[]) if "source" in d}
    observations=defaultdict(list)
    for fact in graph["facts"]:
        observations[fact["doc"],fact["page"]].append(fact)
    pages,conditions=[],[]
    for node in graph["nodes"]:
        if node["type"]!="page":
            continue
        doc,suffix=node["id"].rsplit("/p",1)
        page=int(suffix)
        unit=sections.get((doc,page),doc)
        if unit not in contracts:
            continue
        place={"unit":unit,"doc":doc,"page":page}
        native=node.get("layer")=="text"
        pages.append({**place,"native":native,"text_only":node.get("clause_text_only") is True})
        facts=observations[doc,page]
        by_line=defaultdict(list)
        for fact in facts:
            line=fact.get("source_line")
            if native and line:
                by_line[line["number"],line["text"]].append(fact)
            elif relevant(fact["quote"]):
                conditions.append({**place,"line":None,"quote":fact["quote"],"facts":[fact["id"]]})
        if native:
            text=read_text(doc,page)
            if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=node.get("text_sha256"):
                raise ValueError("合同生效条件所据的整页文字与底稿不符")
            for number,raw in enumerate(text.splitlines(),1):
                matches=by_line[number,raw]
                if relevant(raw) and not recognized(raw,matches):
                    conditions.append({**place,"line":number,"quote":raw,"facts":[f["id"] for f in matches]})
    return {"format":FORMAT,"pages":pages,"conditions":conditions}


def review(finding,ledger,unit):
    pages=[p for p in ledger.get("pages",[]) if p["unit"]==unit]
    conditions=[s for s in ledger.get("conditions",[]) if s["unit"]==unit]
    mixed=[p for p in pages if not p["text_only"] or not p["native"]]
    finding["effect_review"]={"conditions":conditions,"mixed_pages":mixed}
    refs=[f"{p['doc']}/p{p['page']}" for p in pages]
    refs.extend(ref for s in conditions for ref in s["facts"])
    finding["evidence"]=list(dict.fromkeys(finding["evidence"]+refs))
    if not conditions and not mixed and pages:
        return
    if finding["status"]=="ok":
        finding.update(status="missing",detail="双方签署栏有据，合同生效条件仍待核实。")
    if conditions:
        finding["detail"]+=" 请核对另列的生效约定或状态记载，以及所需批准、证明或确认的日期。"
    if mixed or not pages:
        finding["detail"]+=" 需通读合同原页的影像、批注和附加条件。"


def verify(report,read_text,*,signing=False):
    graph,policy=report["graph"],report["policy"]
    if not policy.get("contract_effect"):
        if ("contract_effect.py" in policy.get("code_sha256",{}) or "contract_effect_sources" in graph or
                policy.get("performance_checks") in EFFECT_FORMATS):
            raise ValueError("合同附加生效条件的程序标记缺失")
        if signing and any(f["rule"]=="H01" and f["status"]=="ok" for f in report["findings"]):
            ledger=sources(graph,read_text)
            if ledger["conditions"] or any(not p["native"] or not p["text_only"] for p in ledger["pages"]):
                raise ValueError("旧版合同尚有附加生效约定或待核的整页版式，请按现行程序重审后签收。")
        return
    if (policy["contract_effect"]!=FORMAT or policy.get("performance_checks") not in EFFECT_FORMATS or
            graph.get("contract_effect_sources")!=sources(graph,read_text)):
        raise ValueError("合同生效所据的整页记录、附加条件或引文与归档不符")
