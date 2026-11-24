"""Bind a review of the whole receipt image to the exact transaction reference and source bytes."""

from calculations import normalized

DECLARATION = "receipt-visibility-v1"
OPINIONS = ("complete","partial")
UNCHECKED = "visibility_unchecked"
PARTIAL = "reviewed_partial"


def declaration(fact, opinion):
    return {"format":DECLARATION,"fact":fact["id"],"value":fact["value"],"quote":fact["quote"],"opinion":opinion}


def needs_review(fact, page):
    line = fact.get("source_line") or {}
    native = page.get("layer")=="text" and line.get("rects") and normalized(line["text"]).strip("。;；")==normalized(fact["quote"]).strip("。;；")
    return fact["field"]=="transfer_ref" and not native


def verify_declaration(fact, page, claim):
    if (not isinstance(claim,dict) or claim.get("opinion") not in OPINIONS or not needs_review(fact,page)
            or claim!=declaration(fact,claim["opinion"])):
        raise ValueError("流水展示范围的核图决定与所选字段、引文或原页类型不符")


def review_declarations(graph, selected, choices):
    if not isinstance(choices,dict) or set(choices)-set(selected or ()):
        raise ValueError("流水展示范围须对应本次所选的回单字段")
    if not choices:
        return {}
    if graph.get("profile")!="cn-bank-contract-payment/v1":
        raise ValueError("整页流水核图适用于付款回单任务")
    facts = {f["id"]:f for f in graph["facts"]}
    pages = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    limited = {m["fact"] for m in graph.get("transfer_references",{}).get("facts",[])
               if m.get("state") not in (UNCHECKED,PARTIAL) or m.get("notes") or m.get("lines")}
    claims = {}
    for ref,opinion in choices.items():
        fact = facts[ref]
        claim = declaration(fact,opinion)
        verify_declaration(fact,pages[f"{fact['doc']}/p{fact['page']}"],claim)
        if opinion=="complete" and ref in limited:
            raise ValueError("该流水已有遮盖字符或同页展示说明，请核实原页和对应引文")
        claims[ref] = claim
    return claims


def image_holds(graph, marked, *, trust_reviews):
    banks = set(graph["documents_by_kind"].get("bank_receipt",[]))
    pages = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    result = {m["fact"]:m for m in marked}
    for fact in graph["facts"]:
        unit = fact.get("unit",fact["doc"])
        if fact["field"]!="transfer_ref" or unit not in banks or fact["status"] not in ("confirmed","anchored"):
            continue
        page = pages[f"{fact['doc']}/p{fact['page']}"]
        if not needs_review(fact,page):
            continue
        action = fact.get("attestation") or {}
        receipt = action.get("source_check") or {}
        claim = receipt.get("reference_visibility") if trust_reviews else None
        if claim is not None:
            verify_declaration(fact,page,claim)
            if (fact["status"]!="confirmed" or action.get("fact")!=fact["id"] or action.get("decision")!="confirm" or receipt.get("operation")!="confirm"
                    or (receipt.get("doc"),receipt.get("page"),receipt.get("original_sha256"),receipt.get("page_sha256"))
                    != (fact["doc"],fact["page"],fact["source_sha256"],fact["page_sha256"])):
                raise ValueError("整页流水核图缺少对应的原件、页图或人工确认")
        if fact["id"] in result:
            if claim and claim["opinion"]=="partial" and result[fact["id"]].get("state")=="pending_note":
                result[fact["id"]] = {**result[fact["id"]],"state":PARTIAL}
            continue
        if claim and claim["opinion"]=="complete":
            continue
        result[fact["id"]] = {"fact":fact["id"],"field":fact["field"],"unit":unit,"doc":fact["doc"],"page":fact["page"],
                              "value":fact["value"],"lines":[],"state":PARTIAL if claim else UNCHECKED}
    return list(result.values())


def unchecked(marked):
    return any(m.get("state")==UNCHECKED for m in marked)


def recorded_actions(graph, selected=None):
    actions = []
    for fact in graph["facts"]:
        if selected is not None and fact["id"] not in selected:
            continue
        action = fact.get("attestation") or {}
        if "reference_visibility" in (action.get("source_check") or {}):
            if action.get("fact")!=fact["id"]:
                raise ValueError("流水整页核图记录与所引字段不符")
            actions.append(action)
    return sorted(actions,key=lambda a:a["fact"])
