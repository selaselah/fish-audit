"""Bind a Word contract review to the printed installment it actually selects."""

import re

import acceptance_comments as word

FORMAT = "word-contract-payment-comments-v1"
SINCE = (2026, 11, 26, 18)
STAGE_RULES = {"H04", "H05", "H06"}
# Only these complete, expressly local requests establish the reach of a note.
# Any adoption or timing of the proposed term requires independent evidence.
LOCAL_REQUEST = re.compile(r"建议本期付款前取得双方签认的(?:技术终验单|质保复核单|交付确认单)[，,]待双方签订补充协议[。.]?")


def line_key(text):
    # Word's printable text may add a single space between a Chinese word and a number.
    return re.sub(r"(?<=[\u3400-\u9fff]) (?=[0-9])", "", text)


def sources(graph, read_original, read_text):
    return word.sources(graph, read_original, read_text, kinds=("contract",), role="contract", format_id=FORMAT, compare=line_key)


def source_graph(ledger):
    return word.source_graph(ledger, role="contract", label="合同", relation="contract_word_review")


def clause_ref(document, note, stages, facts):
    loc, anchor = note["location"], note["anchor"]
    if (document["coverage"] != "complete" or not loc or not anchor or note["shortened"] or
            loc["unit"] not in document["units"] or not LOCAL_REQUEST.fullmatch(note["text"].strip())):
        return None
    candidates = [facts[ref] for ref in loc["facts"] if ref in facts and facts[ref]["field"] == "payment_stage"
                  and facts[ref]["status"] in {"confirmed", "anchored"}]
    if len(candidates) != 1:
        return None
    fact, = candidates
    matches = [stage for stage in stages if stage["clause_ref"] == fact["id"]]
    if len(matches) != 1:
        return None
    stage, = matches
    heading = re.fullmatch(r"([^：:]+)[：:](.+)", anchor["quote"])
    if not heading:
        return None
    label, body = heading.groups()
    condition, payment, _ = body.partition("支付")
    if (label == stage["name"] and payment and condition and
            anchor["selected"] in {condition, body, anchor["quote"]} and
            sum(s["name"] == label for s in stages) == 1):
        return fact["id"]
    return None


def checks(graph, findings, ledger=None):
    ledger = graph.get("contract_word_reviews") if ledger is None else ledger
    if not ledger or not ledger["documents"]:
        return []
    facts = {f["id"]: f for f in graph["facts"]}
    stages = [f["stage"] for f in findings if f["rule"] == "H04" and f.get("stage")]
    output = []
    for document in ledger["documents"]:
        notes = []
        for note in document["notes"]:
            location = note["location"]
            if location and location["unit"] not in document["units"] and location["unit"] != document["doc"]:
                continue
            refs = [note["id"]]
            if location:
                refs += [f"{document['doc']}/p{location['page']}", *location["facts"]]
            notes.append((note["id"], clause_ref(document, note, stages, facts), refs))
        output.append((document, notes))
    return output


def assessment(records, finding):
    plan = finding["rule"] == "H03"
    if not plan and finding["rule"] not in STAGE_RULES:
        return None
    clause = finding.get("stage", {}).get("clause_ref")
    documents, assigned, evidence = [], {}, []
    whole = False
    for document, notes in records:
        if not set(document["units"]).intersection(finding["scope"]):
            continue
        partial = document["coverage"] != "complete"
        applicable = [(key, target, refs) for key, target, refs in notes if plan or target is None or target == clause]
        if not plan and not partial and not applicable:
            continue
        documents.append(document["id"])
        evidence.extend([document["doc"], document["id"]])
        whole |= partial or any(target is None for key, target, refs in applicable)
        for key, target, refs in applicable:
            assigned[key] = target
            evidence.extend(refs)
    if not documents:
        return None
    return {"status": "missing" if whole or assigned else "ok", "whole": whole, "documents": documents,
            "notes": list(assigned), "clauses": assigned, "evidence": list(dict.fromkeys(evidence))}


def attach(finding, check):
    if check is None:
        return
    finding["contract_comments"] = check
    finding["evidence"] = list(dict.fromkeys([*finding["evidence"], *check["evidence"]]))
    if check["status"] == "ok":
        return
    if check["whole"]:
        detail = "合同审阅意见的范围或版本待核，请核实正式付款安排。"
    elif finding["rule"] == "H03":
        detail = "合同所列期款另有付款前提的修订建议，请核实对应期次的正式约定。"
    else:
        detail = "本期付款前提另有修订建议，请取得双方确认的适用条款及生效时间。"
    if finding["status"] == "ok":
        finding.update(status="missing", detail=detail)
    else:
        finding["detail"] += " " + detail


def verify(report, read_original, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("contract_word_reviews")
    nodes = [n for n in graph["nodes"] if n["type"] in {"contract_word_review", "contract_word_comment"}]
    edges = [e for e in graph["edges"] if e["type"].startswith("contract_word_review_")]
    if marker is None and "contract_word_reviews" not in graph:
        version = tuple(int(part) for part in policy.get("version", "").split(".") if part.isdecimal())
        if version >= SINCE or "contract_comments.py" in policy.get("code_sha256", {}) or nodes or edges:
            raise ValueError("缺少合同 Word 审阅记录")
        if signing and word.word_units(graph, ("contract",)):
            records = checks(graph, report["findings"], sources(graph, read_original, read_text))
            for finding in report["findings"]:
                if finding["status"] == "ok" and (check := assessment(records, finding)) and check["status"] != "ok":
                    raise ValueError("旧版相符结论未核清合同付款批注，请重新审计后签收。")
        return
    if marker != FORMAT:
        raise ValueError("合同 Word 审阅程序标记不符")
    ledger = sources(graph, read_original, read_text)
    if graph.get("contract_word_reviews") != ledger or (nodes, edges) != source_graph(ledger):
        raise ValueError("合同 Word 批注、原文位置或图谱引用与原件不符")
