"""Trace effectiveness conditions through the contract and its board approval originals."""

import hashlib
import re
from collections import defaultdict

from acceptance_authority import parts
from delegation import is_page_marker
from performance_versions import EFFECT_FORMATS
from calculations import normalized
import signing_parties


LEGACY = "contract-effect-sources-v1"
SEAL_FORMAT = "contract-effect-sources-v2"
APPROVAL_FORMAT = "contract-effect-sources-v3"
SIGNING_FORMAT = signing_parties.NATIVE_FORMAT
FORMAT = signing_parties.IMAGE_FORMAT
SIGNING_FORMATS = (SIGNING_FORMAT, FORMAT)
BOARD_FORMATS = (APPROVAL_FORMAT, *SIGNING_FORMATS)
APPROVAL_SINCE = "2026.11.25.17"
PARTY_SINCE = "2026.11.26.02"
IMAGE_SINCE = "2026.11.26.03"
APPROVAL_FIELDS = {"contract_approval","contract_id","buyer","seller","approval_authority",
                   "approval_result","approved_on","approval_signer"}
SEAL_FIELDS = {"甲方盖章日期":"buyer_sealed_on","乙方盖章日期":"seller_sealed_on"}
SEAL_LABEL = re.compile(r"(?:甲方|乙方|买方|卖方|采购方|供应方)(?:实际)?(?:盖章|签章|签署|签字)(?:日期|时间|日)|^(?:双方)?(?:实际)?(?:盖章|签章)(?:日期|时间)[:：]")
SEAL_CLAUSES = {"本合同自双方盖章之日起生效","合同自双方盖章之日起生效","自双方盖章之日起生效"}
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


def approval_field(raw, fact):
    from graph import PRINTED_TITLES
    from performance import LABELS, SOURCE_LABELS, day
    field = fact["field"]
    if field not in APPROVAL_FIELDS or normalized(raw) != normalized(fact["quote"]):
        return False
    value = normalized(fact["value"])
    if field == "contract_approval":
        return value == normalized(raw) and PRINTED_TITLES.get(value) == field
    label, body = parts(raw)
    if not body or label not in (LABELS.get(field) or SOURCE_LABELS.get(field, ())):
        return False
    if field == "approved_on" and (re.search(r"\d\s+\d", body) or not day(normalized(body))):
        return False
    if field == "contract_id" and re.search(r"[0-9A-Za-z]\s+[0-9A-Za-z]",body):
        return False
    if field == "approval_signer" and re.search(r"[;；,，:：。]|仅限|另行|另须|尚待|暂缓|不得",body):
        return False
    return value in (normalized(raw), normalized(body))


def sources(graph,read_text,format=FORMAT):
    def effect_signal(raw):
        if not relevant(raw):
            return False
        if "payment_window_sources" in graph:
            from payment_windows import spec
            if spec(raw):
                return False
        return True
    contracts=set(graph["documents_by_kind"].get("contract",[]))
    approvals=set(graph["documents_by_kind"].get("contract_approval",[])) if format in BOARD_FORMATS else set()
    sections={(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents",[]) if "source" in d}
    observations=defaultdict(list)
    for fact in graph["facts"]:
        observations[fact["doc"],fact["page"]].append(fact)
    pages,conditions,signing_rows=[],[],[]
    for node in graph["nodes"]:
        if node["type"]!="page":
            continue
        doc,suffix=node["id"].rsplit("/p",1)
        page=int(suffix)
        unit=sections.get((doc,page),doc)
        board = unit in approvals
        if unit not in contracts and not board:
            continue
        place={"unit":unit,"doc":doc,"page":page}
        native=node.get("layer")=="text"
        entry={**place,"native":native,"text_only":node.get("clause_text_only") is True}
        if board:
            entry["kind"]="board_approval"
        pages.append(entry)
        facts=observations[doc,page]
        by_line=defaultdict(list)
        for fact in facts:
            line=fact.get("source_line")
            if format in SIGNING_FORMATS and not board and not (native and line):
                signature=signing_parties.row(place,fact["quote"],None,[fact])
                if signature:
                    signing_rows.append(signature)
            if native and line:
                by_line[line["number"],line["text"]].append(fact)
            elif board:
                if not is_page_marker(fact["quote"]) and not approval_field(fact["quote"],fact):
                    conditions.append({**place,"line":None,"quote":fact["quote"],"facts":[fact["id"]],"kind":"approval_note"})
            elif format!=LEGACY and SEAL_LABEL.search(normalized(fact["quote"])):
                conditions.append({**place,"line":None,"quote":fact["quote"],"facts":[fact["id"]],"kind":"seal_date"})
            elif effect_signal(fact["quote"]):
                conditions.append({**place,"line":None,"quote":fact["quote"],"facts":[fact["id"]]})
        if native:
            text=read_text(doc,page)
            if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=node.get("text_sha256"):
                raise ValueError("合同生效条件所据的整页文字与底稿不符")
            for number,raw in enumerate(text.splitlines(),1):
                matches=by_line[number,raw]
                if format in SIGNING_FORMATS and not board:
                    signature=signing_parties.row(place,raw,number,matches)
                    if signature:
                        signing_rows.append(signature)
                if board:
                    if is_page_marker(raw) or any(f["status"] in ("anchored","confirmed")
                            and f["source_line"].get("rects") and approval_field(raw,f) for f in matches):
                        continue
                    conditions.append({**place,"line":number,"quote":raw,"facts":[f["id"] for f in matches],"kind":"approval_note"})
                elif format!=LEGACY and SEAL_LABEL.search(normalized(raw)):
                    conditions.append({**place,"line":number,"quote":raw,"facts":[f["id"] for f in matches],"kind":"seal_date"})
                elif effect_signal(raw) and not recognized(raw,matches):
                    conditions.append({**place,"line":number,"quote":raw,"facts":[f["id"] for f in matches]})
    ledger={"format":format,"pages":pages,"conditions":conditions}
    if format in SIGNING_FORMATS:
        ledger["signing_rows"]=signing_rows
    return ledger


def seal_check(contract,rows,clear):
    from performance import printed_day
    dates={}
    for label,field in SEAL_FIELDS.items():
        matched=[r for r in rows if parts(r["quote"])[0]==label]
        when=printed_day(contract,field)
        facts=contract.fields[field]
        if (len(matched)==1 and matched[0]["line"] and len(facts)==1 and facts[0]["id"] in matched[0]["facts"]
                and facts[0]["quote"]==matched[0]["quote"] and when):
            dates[field]=when.isoformat()
    effective=printed_day(contract,"effect_on")
    evidence={"dates":dates,"declared_on":effective.isoformat() if effective else None,"completed_on":None}
    if (not clear or len(rows)!=2 or len(dates)!=2 or contract.body("effect_clause") not in SEAL_CLAUSES
            or not all(contract.signed(side+"_signature",contract.single(party),"seal") for side,party in (("buyer","buyer"),("seller","seller")))):
        return evidence,"missing","须核实双方盖章日期原行、印章、条款及各日期的对应关系。"
    last=max(dates.values())
    evidence["completed_on"]=last
    if not effective:
        return evidence,"missing",f"双方最后盖章日为 {last}，实际生效日期原件待核。"
    if last!=effective.isoformat():
        return evidence,"risk",f"双方最后盖章日为 {last}，与合同所列生效日 {effective} 不一致，须核对现行约定及履行依据。"
    return evidence,"ok",f"双方最后盖章日 {last} 与合同所列生效日相符。"


def review(finding,ledger,contract,graph):
    unit=contract.unit
    board_pages=[p for p in ledger.get("pages",[]) if p.get("kind")=="board_approval" and p["unit"] in finding["scope"]]
    units={unit,*(p["unit"] for p in board_pages)}
    pages=[p for p in ledger.get("pages",[]) if p["unit"] in units]
    conditions=[s for s in ledger.get("conditions",[]) if s["unit"] in units]
    mixed=[p for p in pages if not p["text_only"] or not p["native"]]
    finding["effect_review"]={"conditions":conditions,"mixed_pages":mixed}
    if board_pages:
        finding["effect_review"]["approval_pages"]=board_pages
    refs=[f"{p['doc']}/p{p['page']}" for p in pages]
    refs.extend(ref for s in conditions for ref in s["facts"])
    finding["evidence"]=list(dict.fromkeys(finding["evidence"]+refs))
    seals=[s for s in conditions if s.get("kind")=="seal_date"]
    conditions=[s for s in conditions if s.get("kind")!="seal_date"]
    if seals:
        data,status,detail=seal_check(contract,seals,finding["status"]=="ok" and not conditions and not mixed and bool(pages))
        finding["effect_review"]["seals"]=data
        finding["evidence"]=list(dict.fromkeys(finding["evidence"]+contract.evidence("effect_on","buyer_sealed_on","seller_sealed_on")))
        if finding["status"]=="ok":
            finding.update(status=status,detail=detail)
        else:
            finding["detail"]+=" "+detail
    if ledger.get("format") in SIGNING_FORMATS:
        signing_parties.review(finding,ledger,contract,graph)
    if not conditions and not mixed and pages:
        return
    if finding["status"]=="ok":
        finding.update(status="missing",detail="双方签署栏有据，合同生效条件仍待核实。")
    if any(s.get("kind")=="approval_note" for s in conditions):
        finding["detail"]+=" 董事会审批记录另有待核原文，请核对批准范围、附加条件及后续决议。"
    if any(s.get("kind")!="approval_note" for s in conditions):
        finding["detail"]+=" 请核对另列的生效约定或状态记载，以及所需批准、证明或确认的日期。"
    if any(p.get("kind")=="board_approval" for p in mixed):
        finding["detail"]+=" 须核对审批记录整页的影像及批注。"
    if any(p.get("kind")!="board_approval" for p in mixed) or not pages:
        finding["detail"]+=" 需通读合同原页的影像、批注和附加条件。"


def verify(report,read_text,*,signing=False):
    graph,policy=report["graph"],report["policy"]
    marker=policy.get("contract_effect")
    version=policy.get("version","")
    positive=[f for f in report["findings"] if f["rule"]=="H01" and f["status"]=="ok"]
    if signing and marker not in BOARD_FORMATS and positive and graph["documents_by_kind"].get("contract_approval"):
        scope={unit for finding in positive for unit in finding["scope"]}
        current=sources(graph,read_text)
        if (any(s.get("kind")=="approval_note" and s["unit"] in scope for s in current["conditions"])
                or any(p.get("kind")=="board_approval" and p["unit"] in scope and not (p["native"] and p["text_only"]) for p in current["pages"])):
            raise ValueError("旧版董事会批准依据另有待核原文或影像，请按现行程序重审后签收。")
    if signing and marker!=FORMAT and positive:
        from performance import Material
        scope={unit for finding in positive for unit in finding["scope"]}
        current=sources(graph,read_text)
        for unit in graph["documents_by_kind"].get("contract",[]):
            if unit in scope and any(r["status"]!="ok" for r in signing_parties.assess(current,Material(graph,unit),graph)):
                raise ValueError("旧版合同的签章主体仍待核对，请按现行程序重审后签收。")
    if signing and marker==SIGNING_FORMAT:
        from performance import Material
        mixed=[f for f in report["findings"] if f["rule"]=="H01" and f.get("effect_review",{}).get("mixed_pages")]
        if mixed:
            current=sources(graph,read_text)
            for finding in mixed:
                known={tuple(r["comparison"]) for r in finding["effect_review"].get("party_seals",[]) if r["state"]=="different"}
                for unit in graph["documents_by_kind"].get("contract",[]):
                    if unit not in finding["scope"]:
                        continue
                    for record in signing_parties.assess(current,Material(graph,unit),graph):
                        if record["state"]=="different" and tuple(record["comparison"]) not in known:
                            raise ValueError("旧版底稿未列出合同签章名称的已核差异，请按现行程序重审后签收。")
    if not policy.get("contract_effect"):
        if ("contract_effect.py" in policy.get("code_sha256",{}) or "contract_effect_sources" in graph or
                policy.get("performance_checks") in EFFECT_FORMATS):
            raise ValueError("合同附加生效条件的程序标记缺失")
        if signing and any(f["rule"]=="H01" and f["status"]=="ok" for f in report["findings"]):
            ledger=sources(graph,read_text)
            if ledger["conditions"] or any(not p["native"] or not p["text_only"] for p in ledger["pages"]):
                raise ValueError("旧版合同尚有附加生效约定或待核的整页版式，请按现行程序重审后签收。")
        return
    if marker==LEGACY and signing and any(f["rule"]=="H01" and f["status"]=="ok" for f in report["findings"]):
        from performance import Material
        ledger=sources(graph,read_text)
        for unit in graph["documents_by_kind"].get("contract",[]):
            seals=[s for s in ledger["conditions"] if s["unit"]==unit and s.get("kind")=="seal_date"]
            if seals and seal_check(Material(graph,unit),seals,True)[1]!="ok":
                raise ValueError("旧版未核清双方实际盖章日，请按现行规则重审后签收。")
    if (marker not in (*BOARD_FORMATS,SEAL_FORMAT,LEGACY) or version>=IMAGE_SINCE and marker!=FORMAT or
            version>=PARTY_SINCE and marker not in SIGNING_FORMATS or version>=APPROVAL_SINCE and marker not in BOARD_FORMATS or
            version>="2026.11.25.03" and marker==LEGACY or policy.get("performance_checks") not in EFFECT_FORMATS or
            graph.get("contract_effect_sources")!=sources(graph,read_text,marker)):
        raise ValueError("合同生效所据的整页记录、附加条件或引文与归档不符")
    if marker in SIGNING_FORMATS:
        nodes,edges=signing_parties.source_graph(graph["contract_effect_sources"])
        if ([n for n in graph["nodes"] if n["type"]=="contract_signing_line"]!=nodes or
                [e for e in graph["edges"] if e["type"]=="contract_signing_source"]!=edges or
                [e for e in graph["edges"] if e["type"]=="contract_seal_name_comparison"]!=signing_parties.comparisons(report["findings"])):
            raise ValueError("签章主体比较的图谱关系与原行或审计结果不符")
