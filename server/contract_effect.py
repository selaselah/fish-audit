"""Trace effectiveness conditions through the contract and its board approval originals."""

import hashlib
import re
from collections import defaultdict

from acceptance_authority import parts
from delegation import is_page_marker
from performance_versions import EFFECT_FORMATS
from calculations import normalized
import signing_parties
import contract_calendar


LEGACY = "contract-effect-sources-v1"
SEAL_FORMAT = "contract-effect-sources-v2"
APPROVAL_FORMAT = "contract-effect-sources-v3"
SIGNING_FORMAT = signing_parties.NATIVE_FORMAT
IMAGE_FORMAT = signing_parties.IMAGE_FORMAT
WORD_FORMAT = signing_parties.WORD_FORMAT
FORMAT = signing_parties.SHARED_FORMAT
SIGNING_FORMATS = (SIGNING_FORMAT, *signing_parties.IMAGE_FORMATS)
BOARD_FORMATS = (APPROVAL_FORMAT, *SIGNING_FORMATS)
APPROVAL_SINCE = "2026.11.25.17"
PARTY_SINCE = "2026.11.26.02"
IMAGE_SINCE = "2026.11.26.03"
WORD_SINCE = "2026.11.26.12"
CALENDAR_SINCE = "2026.11.26.13"
FORM_SINCE = (2026, 11, 28, 12)
SHARED_SINCE = (2026, 11, 28, 13)
FORM_RECTS = "contract_signing_form_rects"
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
FORM_LABEL = re.compile(r"(?:(?:本|主|采购)?合同|协议)?(?:甲方|乙方|采购方|供应方)?(?:签署|签约|签订|签字|签章|用印)(?:方式|要求|约定|条件)")
MAIN_SUBJECT = re.compile(r"^(?:第[一二三四五六七八九十百0-9]+条[、.：:]?)?(?:本合同|本协议|主合同|本采购合同|签订本合同|签署本合同)")
OTHER_FORM = re.compile(r"补充协议|验收[单表书]|验收报告|付款申请|付款审批|审批单|委托书|确认单|结算单|保函|回单|发票|送货单")
SIGN = r"签(?:字|名)"
SEAL = r"(?:加盖(?:双方|各自|本单位|单位|公司)?(?:公章|印章|合同专用章)|盖章|用印)"
JOIN = r"[,、]?(?:并且|并|且|同时|及|和|后再)"
JOINT_FORM = re.compile(SIGN + r"(?:确认)?" + JOIN + r"(?:须|应|需)?(?:再)?" + SEAL +
                        r"|(?:公章|印章|合同专用章|盖章|用印)" + JOIN +
                        r"(?:须|应|需)?(?:由|经)?(?:甲乙双方|双方|甲方|乙方|各方)?(?:的)?(?:法定代表人|授权代表|代表)?(?:亲自|亲笔)?" + SIGN)
SIMPLE_EITHER = re.compile(r"(?:本合同|本协议)?(?:须|应|需)?(?:经|由|自)?(?:甲乙双方|双方|各方)"
                           r"(?:" + SIGN + r"(?:或|或者)" + SEAL + r"|" + SEAL + r"(?:或|或者)" + SIGN + r")(?:即可)?")

CONTRACT_NOUN = r"(?:本采购合同|采购合同|主合同|本合同|合同|本协议)"
ACCEPTANCE_NOUN = r"(?:(?:采购|设备|到货|交付|最终)?验收(?:报告|单|表|书))"
AND_DOCUMENT = r"(?:以及|及|和|与|、)"
SHARED_SUBJECT = re.compile(r"^(?:第[一二三四五六七八九十百0-9]+条[、.：:]?)?(?:" +
                            CONTRACT_NOUN + AND_DOCUMENT + ACCEPTANCE_NOUN + "|" +
                            ACCEPTANCE_NOUN + AND_DOCUMENT + CONTRACT_NOUN + ")")
COLLECTIVE = re.compile(r"^,?(?:(?:两者|二者|两份文件)?(?:均|皆|都|一律))?")
OBLIGATION = r"(?:必须|应当|需要|须|应|需)?"
SIGNING_ACTOR = r"(?:经|由)?(?:甲乙双方|双方|各方|甲方|乙方)?(?:各自的|的|各自)?(?:法定代表人|授权代表|代表)?(?:亲自|亲笔)?"
SIGNED_ACT = SIGNING_ACTOR + SIGN + r"(?:确认)?"
SEALED_ACT = SIGNING_ACTOR + SEAL
SHARED_DUAL = re.compile(OBLIGATION + "(?:" + SIGNED_ACT + JOIN + OBLIGATION + SEALED_ACT +
                         "|" + SEALED_ACT + JOIN + OBLIGATION + SIGNED_ACT + r")(?:后生效|后方可生效|方为有效)?")
SHARED_CHOICE = re.compile(r"(?:可以|可|必须|须|应当|应|需)?(?:(?:经|由)?(?:甲乙双方|双方|各方))?(?:可以|可)?(?:" +
                           SIGN + r"(?:或者|或)" + SEAL + "|" + SEAL + r"(?:或者|或)" + SIGN + r")(?:任选其一|即可|均可)?")
SIGNING_START = re.compile(r"(?:分别|可不|无需|无须|不得|不必|可|可以)?" + OBLIGATION + SIGNING_ACTOR + r"(?:签字|签名|加盖|盖章|用印)")
SHARED_DOCUMENTS = ("contract","acceptance")


def shared_form(raw):
    label, body = parts(raw)
    label_pair = SHARED_SUBJECT.match(label) if body else None
    shared_heading = bool(label_pair and FORM_LABEL.fullmatch(label[label_pair.end():]))
    ordinary_heading = not body or FORM_LABEL.fullmatch(label) or label in ("生效条款","合同生效条件","生效条件","特别约定","签署")
    clauses = [s for s in re.split(r"[;。]",normalized(body or raw)) if s]
    for index,clause in enumerate(clauses):
        pair = SHARED_SUBJECT.match(clause)
        if not pair and not (shared_heading and index==0):
            continue
        predicate = COLLECTIVE.sub("",clause[pair.end():] if pair else clause,count=1)
        explicit = len(clauses)==1 and (ordinary_heading or shared_heading)
        if explicit and SHARED_CHOICE.fullmatch(predicate):
            return "either"
        if not SIGNING_START.match(predicate):
            continue
        if explicit and SHARED_DUAL.fullmatch(predicate):
            return "joint"
        # The two named documents are clear. An exception, different actors or an unparsed condition still needs review.
        return "review"
    return None


def signing_form(raw):
    label, body = parts(raw)
    headed = bool(body and FORM_LABEL.fullmatch(label))
    primary = label in ("生效条款","合同生效条件","生效条件","合同生效条款")
    text = normalized(body or raw)
    qualified = re.search(r"无需|无须|不必|不得|不需|不要求|可不|免予|若|如果|仅在|除非|除外|但|可选",text)
    found = None
    for piece in re.split(r"[;。]|,(?=本合同|本协议|主合同|验收单|验收报告|付款申请|委托书|补充协议)",text):
        if not piece or not (headed or primary or MAIN_SUBJECT.match(piece)):
            continue
        # Signing an acceptance, a mandate or a payment request does not establish who signs this contract.
        if OTHER_FORM.search(piece) or SIMPLE_EITHER.fullmatch(piece):
            continue
        signature, seal = re.search(SIGN,piece), re.search(r"盖章|公章|印章|合同专用章|用印",piece)
        if signature and seal:
            if JOINT_FORM.search(piece):
                if qualified or re.search(r"或(?:者)?(?:加盖|盖章|用印)",piece):
                    return "review"
                found = "joint"
                continue
            # The base effectiveness checker already handles an unqualified choice expressed in the main clause.
            from performance import BOARD_CONDITION, EFFECT
            if not (EFFECT.fullmatch(piece) or BOARD_CONDITION.fullmatch(piece)):
                return "review"
        elif (signature or seal) and (headed or MAIN_SUBJECT.match(piece)) and re.search(r"代表人|授权代表|亲笔|专用章",piece):
            return "review"
    return found


def form_rows(ledger):
    return [row for row in ledger.get("conditions", ()) if row.get("kind") == "signing_form"]


def review_acceptance(finding, rows):
    finding["acceptance_signing_requirements"] = [r["id"] for r in rows]
    refs = [ref for r in rows for ref in (r["id"], f"{r['doc']}/p{r['page']}", *r["facts"])]
    finding["evidence"] = list(dict.fromkeys([*finding["evidence"],*refs]))
    finding["scope"] = list(dict.fromkeys([*finding["scope"],*(r["unit"] for r in rows)]))
    detail = ("合同约定验收文件也须签字并盖章，请核对本次验收的签字人、用印及签署版本。"
              if any(r["form"]=="joint" for r in rows) else
              "合同另列适用于验收文件的签署约定，请核对所引原行、适用范围及本次验收的签署凭证。")
    if finding["status"]=="ok":
        finding.update(status="missing", detail=detail)
    else:
        finding["detail"] += " " + detail
    if finding.get("reinspection",{}).get("state")=="closed":
        finding["reinspection"]["state"] = "open"


def form_graph(ledger):
    nodes, edges = [], []
    for row in form_rows(ledger):
        page = f"{row['doc']}/p{row['page']}"
        nodes.append({"id":row["id"], "type":"contract_signing_requirement", "label":row["quote"],
                      "doc":row["doc"], "page":row["page"], "line":row["line"]})
        if "applies_to" in row:
            nodes[-1]["applies_to"] = row["applies_to"]
        edges.append({"from":page, "to":row["id"], "type":"contract_signing_requirement_source", "evidence":[page,*row["facts"]]})
    return nodes, edges


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


def sources(graph,read_text,format=FORMAT,*,calls=None):
    from advance_guarantee import scoped_terms
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
    pages,conditions,signing_rows,date_rows=[],[],[],[]
    original_hashes={d["id"]:d.get("sha256") for d in graph["documents"]}
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
            guarantees = {(r["doc"],r["page"],r["line"],r["quote"]) for r in scoped_terms(graph,unit)}
            for number,raw in enumerate(text.splitlines(),1):
                matches=by_line[number,raw]
                if (doc,page,number,raw) in guarantees:
                    continue
                shared = shared_form(raw) if format == FORMAT and not board else None
                form = None
                if format in signing_parties.FORM_FORMATS and not board and shared != "either":
                    form = shared or signing_form(raw)
                if format in signing_parties.CALENDAR_FORMATS and not board:
                    date_row = contract_calendar.row(place,raw,number,matches,graph,node.get("sha256"),
                                                     original_hashes.get(doc),(calls or {}).get((doc,page),{}))
                    if date_row:
                        date_rows.append(date_row)
                        # Further stipulations on the same line still need a separate review.
                        _, body = parts(raw)
                        if not (form or relevant(body) or APPROVAL.search(body) or QUALIFIER.search(body)):
                            continue
                if format in SIGNING_FORMATS and not board:
                    signature=signing_parties.row(place,raw,number,matches)
                    if signature:
                        signing_rows.append(signature)
                if board:
                    if is_page_marker(raw) or any(f["status"] in ("anchored","confirmed")
                            and f["source_line"].get("rects") and approval_field(raw,f) for f in matches):
                        continue
                    conditions.append({**place,"line":number,"quote":raw,"facts":[f["id"] for f in matches],"kind":"approval_note"})
                elif form:
                    conditions.append({**place, "line":number, "quote":raw, "facts":[f["id"] for f in matches],
                                       "kind":"signing_form", "form":form, "id":f"contract-signing-form/{doc}/p{page}/l{number}"})
                    if shared:
                        conditions[-1]["applies_to"] = list(SHARED_DOCUMENTS)
                if not board and format!=LEGACY and SEAL_LABEL.search(normalized(raw)):
                    conditions.append({**place,"line":number,"quote":raw,"facts":[f["id"] for f in matches],"kind":"seal_date"})
                elif not board and not form and effect_signal(raw) and not recognized(raw,matches):
                    conditions.append({**place,"line":number,"quote":raw,"facts":[f["id"] for f in matches]})
    ledger={"format":format,"pages":pages,"conditions":conditions}
    if format in SIGNING_FORMATS:
        ledger["signing_rows"]=signing_rows
    if format in signing_parties.CALENDAR_FORMATS:
        ledger["date_rows"] = date_rows
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
    finding.setdefault("effect_review", {}).update(conditions=conditions, mixed_pages=mixed)
    if board_pages:
        finding["effect_review"]["approval_pages"]=board_pages
    refs=[f"{p['doc']}/p{p['page']}" for p in pages]
    refs.extend(ref for s in conditions for ref in s["facts"])
    refs.extend(s["id"] for s in form_rows(ledger) if s["unit"] == unit)
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
    if ledger.get("format") in signing_parties.WORD_FORMATS:
        signing_parties.review_word(finding,ledger,contract,graph)
    if ledger.get("format") in signing_parties.CALENDAR_FORMATS:
        contract_calendar.review(finding, contract)
    if not conditions and not mixed and pages:
        return
    if finding["status"]=="ok":
        finding.update(status="missing",detail="双方签署栏有据，合同生效条件仍待核实。")
    if any(s.get("kind")=="approval_note" for s in conditions):
        finding["detail"]+=" 董事会审批记录另有待核原文，请核对批准范围、附加条件及后续决议。"
    forms = [s for s in conditions if s.get("kind")=="signing_form"]
    if forms:
        joint = any(s["form"]=="joint" for s in forms)
        finding["detail"] += (" 合同另列签字及盖章要求，请核对签署原件上两项记录、签字人身份及权限。" if joint else
                              " 合同另列签署方式或签字人要求，请核对所引原行、签署原件及相应权限。")
    if any(s.get("kind") not in ("approval_note","signing_form") for s in conditions):
        finding["detail"]+=" 请核对另列的生效约定或状态记载，以及所需批准、证明或确认的日期。"
    if any(p.get("kind")=="board_approval" for p in mixed):
        finding["detail"]+=" 须核对审批记录整页的影像及批注。"
    if any(p.get("kind")!="board_approval" for p in mixed) or not pages:
        finding["detail"]+=" 需通读合同原页的影像、批注和附加条件。"


def verify(report,read_text,*,signing=False,read_layout=None,read_original=None):
    graph,policy=report["graph"],report["policy"]
    marker=policy.get("contract_effect")
    version=policy.get("version","")
    positive=[f for f in report["findings"] if f["rule"]=="H01" and f["status"]=="ok"]
    calls={(p["doc"],p["page"]):p for p in report.get("calls",{}).get("pages",[])}
    if marker not in signing_parties.FORM_FORMATS and (any(FORM_RECTS in call for call in calls.values()) or
            any(n["type"]=="contract_signing_requirement" for n in graph["nodes"]) or
            any(e["type"]=="contract_signing_requirement_source" for e in graph["edges"])):
        raise ValueError("旧版底稿含未出具的合同签署条款定位")
    if signing and marker != FORMAT and any(f["rule"]=="H01" and (f.get("effect_review") or f["status"]=="ok") for f in report["findings"]):
        current = form_rows(sources(graph,read_text,calls=calls))
        for finding in (f for f in report["findings"] if f["rule"]=="H01"):
            issued = {(s["doc"],s["page"],s["line"],s["quote"]) for s in finding.get("effect_review",{}).get("conditions",())}
            if any(r["unit"] in finding["scope"] and (r["doc"],r["page"],r["line"],r["quote"]) not in issued for r in current):
                raise ValueError("旧版底稿漏列合同原件所载的签字盖章要求，请重审后签收。")
            if any(r.get("applies_to") and r["unit"] in finding["scope"] for r in current):
                raise ValueError("旧版未区分主合同与验收文件共用的签署要求，请重审后签收。")
    if signing and marker not in BOARD_FORMATS and positive and graph["documents_by_kind"].get("contract_approval"):
        scope={unit for finding in positive for unit in finding["scope"]}
        current=sources(graph,read_text)
        if (any(s.get("kind")=="approval_note" and s["unit"] in scope for s in current["conditions"])
                or any(p.get("kind")=="board_approval" and p["unit"] in scope and not (p["native"] and p["text_only"]) for p in current["pages"])):
            raise ValueError("旧版董事会批准依据另有待核原文或影像，请按现行程序重审后签收。")
    if signing and marker not in signing_parties.IMAGE_FORMATS and positive:
        from performance import Material
        scope={unit for finding in positive for unit in finding["scope"]}
        current=sources(graph,read_text)
        for unit in graph["documents_by_kind"].get("contract",[]):
            if unit in scope and any(r["status"]!="ok" for r in signing_parties.assess(current,Material(graph,unit),graph)):
                raise ValueError("旧版合同的签章主体仍待核对，请按现行程序重审后签收。")
    if signing and marker not in signing_parties.WORD_FORMATS and positive:
        scope = {unit for finding in positive for unit in finding["scope"]}
        current = sources(graph, read_text)
        if any(signing_parties.word_signatures(current, graph, unit)
               for unit in graph["documents_by_kind"].get("contract", []) if unit in scope):
            raise ValueError("旧版以 Word 文字栏支持了合同签署，请核对签署凭证并重新审计后签收。")
    if signing and marker not in signing_parties.CALENDAR_FORMATS and positive:
        from performance import Material
        scope = {unit for finding in positive for unit in finding["scope"]}
        current = sources(graph, read_text, calls=calls)
        for unit in scope.intersection(graph["documents_by_kind"].get("contract", [])):
            material = Material(graph, unit)
            if any(contract_calendar.reading(rows, material)[0] not in contract_calendar.READ
                   for rows in contract_calendar.by_field(current, unit).values()):
                raise ValueError("旧版采用的合同日期存在待核原行，请按现行程序重审后签收。")
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
    if (marker not in (*BOARD_FORMATS,SEAL_FORMAT,LEGACY) or
            (tuple(map(int,version.split(".")))>=FORM_SINCE) != (marker in signing_parties.FORM_FORMATS) or
            (tuple(map(int,version.split(".")))>=SHARED_SINCE) != (marker==FORMAT) or
            version>=CALENDAR_SINCE and marker not in signing_parties.CALENDAR_FORMATS or
            version>=WORD_SINCE and marker not in signing_parties.WORD_FORMATS or
            version>=IMAGE_SINCE and marker not in signing_parties.IMAGE_FORMATS or
            version>=PARTY_SINCE and marker not in SIGNING_FORMATS or version>=APPROVAL_SINCE and marker not in BOARD_FORMATS or
            version>="2026.11.25.03" and marker==LEGACY or policy.get("performance_checks") not in EFFECT_FORMATS or
            graph.get("contract_effect_sources")!=sources(graph,read_text,marker,calls=calls)):
        raise ValueError("合同生效所据的整页记录、附加条件或引文与归档不符")
    if marker in SIGNING_FORMATS:
        nodes,edges=signing_parties.source_graph(graph["contract_effect_sources"])
        if ([n for n in graph["nodes"] if n["type"]=="contract_signing_line"]!=nodes or
                [e for e in graph["edges"] if e["type"]=="contract_signing_source"]!=edges or
                [e for e in graph["edges"] if e["type"]=="contract_seal_name_comparison"]!=signing_parties.comparisons(report["findings"])):
            raise ValueError("签章主体比较的图谱关系与原行或审计结果不符")
    if marker in signing_parties.CALENDAR_FORMATS:
        nodes, edges = contract_calendar.source_graph(graph["contract_effect_sources"])
        if ([n for n in graph["nodes"] if n["type"]=="contract_date_line"] != nodes or
                [e for e in graph["edges"] if e["type"]=="contract_date_source"] != edges):
            raise ValueError("合同日期的原行与证据图谱不符")
    if marker in signing_parties.FORM_FORMATS:
        ledger = graph["contract_effect_sources"]
        nodes, edges = form_graph(ledger)
        if ([n for n in graph["nodes"] if n["type"]=="contract_signing_requirement"] != nodes or
                [e for e in graph["edges"] if e["type"]=="contract_signing_requirement_source"] != edges):
            raise ValueError("合同签署要求的原行与证据图谱不符")
        rows = form_rows(ledger)
        for finding in (f for f in report["findings"] if f["rule"]=="H01" and
                        (f.get("effect_review") or len(graph["documents_by_kind"].get("contract",()))==1)):
            cited = [r for r in rows if r["unit"] in finding["scope"]]
            if form_rows(finding.get("effect_review",{})) != cited or (cited and (finding["status"]=="ok" or
                    any(r["id"] not in finding["evidence"] for r in cited))):
                raise ValueError("合同签署发现漏列原件上的签署要求")
        contracts = graph["documents_by_kind"].get("contract",[])
        for finding in (f for f in report["findings"] if f["rule"]=="H02"):
            shared = [r["id"] for r in rows if r.get("applies_to")==list(SHARED_DOCUMENTS) and
                      len(contracts)==1 and r["unit"]==contracts[0]]
            if finding.get("acceptance_signing_requirements") != (shared or None) or (shared and
                    (finding["status"]=="ok" or not set(shared).issubset(finding["evidence"]))):
                raise ValueError("验收发现所引的共同签署要求与原件适用范围不符")
        if calls or policy.get("archived_methods"):
            from contract_folios import line_numbers, verify_page_geometry
            verify_page_geometry(calls.values(),line_numbers(rows),{},FORM_RECTS,"合同签署要求",read_layout)
            pages = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
            originals, located = [], []
            for r in rows:
                node = pages[f"{r['doc']}/p{r['page']}"]
                call = calls[r["doc"],r["page"]]
                if call.get("page_sha256")!=node["sha256"]:
                    raise ValueError("合同签署要求所据的页图与底稿不符")
                originals.append({"doc":r["doc"],"pages":[{"ref":node["id"],"sha256":node["sha256"],
                    "layer":node["layer"],"text_only":node.get("clause_text_only") is True}]})
                located.append({**r,"rects":call[FORM_RECTS][str(r["line"])]})
            if originals and read_original:
                from original_records import verify_rendered
                verify_rendered(graph,originals,read_original,"合同签署要求",extra_lines=located)
