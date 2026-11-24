"""Relate an independently transcribed qualifier to the transaction reference on the same receipt page."""


def annotated_fields(graph, printed, partial_line):
    banks = set(graph["documents_by_kind"].get("bank_receipt",[]))
    pages = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    notes = {}
    for fact in graph["facts"]:
        unit = fact.get("unit",fact["doc"])
        if unit not in banks or fact["field"] not in {"transfer_ref_note","other","transfer_ref"}:
            continue
        if fact["status"] not in {"visual","anchored","confirmed"} or not partial_line(fact["quote"]):
            continue
        if fact["field"]=="transfer_ref" and "说明" not in fact["quote"] and "仅" not in fact["value"]:
            continue
        page = pages[f"{fact['doc']}/p{fact['page']}"]
        if page.get("layer")=="text" and fact["status"]=="visual":
            continue
        address = unit,fact["doc"],fact["page"]
        notes.setdefault(address,[]).append({"fact":fact["id"],"field":fact["field"],
                                             "quote":fact["quote"],"status":fact["status"]})
    marked = {m["fact"]:m for m in printed}
    result = []
    for fact in graph["facts"]:
        if fact["field"]!="transfer_ref" or fact["status"] not in {"anchored","confirmed","visual"}:
            continue
        unit = fact.get("unit",fact["doc"])
        item = marked.get(fact["id"])
        observed = [n for n in notes.get((unit,fact["doc"],fact["page"]),[]) if n["fact"]!=fact["id"]]
        if observed:
            confirmed = item is not None or any(n["status"] in {"anchored","confirmed"} for n in observed)
            if item is None:
                item = {"fact":fact["id"],"field":"transfer_ref","unit":unit,"doc":fact["doc"],"page":fact["page"],
                        "value":fact["value"],"lines":[]}
            item = {**item,"notes":observed,"state":"partial" if confirmed else "pending_note"}
        if item is not None:
            result.append(item)
    return result


def note_edges(marked):
    return [{"from":note["fact"],"to":item["fact"],"type":"proposed_transfer_note" if note["status"]=="visual" else "qualifies_transfer_ref",
             "evidence":[note["fact"],item["fact"]]} for item in marked for note in item.get("notes",[])]


def note_refs(marked):
    return list(dict.fromkeys(n["fact"] for item in marked for n in item.get("notes",[])))


def pending_notes(marked):
    return bool(marked) and all(item.get("state")=="pending_note" for item in marked)
