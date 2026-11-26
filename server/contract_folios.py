"""Trace payment provisions to the physical pages of one submitted contract."""

import hashlib
import math
import re
import unicodedata
from collections import Counter, defaultdict

import folio_transcription
from delegation import complete_id, is_page_marker
from reinspection_wait import standard_contract_line

LEGACY = "contract-payment-folios-v1"
FORMAT = "contract-payment-folios-v2"
SINCE = "2026.11.26.10"
TRANSCRIPTION_SINCE = "2026.11.26.11"
ROOT_IDS = {"合同编号", "合同号", "采购合同编号"}
IDS = ROOT_IDS | {
    "关联协议编号",
    "关联合同编号",
    "对应主合同编号",
    "主合同编号",
    "适用合同",
    "适用合同编号",
    "所属合同编号",
}
CONTINUATIONS = {
    "续页",
    "合同续页",
    "采购合同续页",
    "付款条款续页",
    "付款条款（续）",
    "付款条款(续)",
}
ANNEX = re.compile(r"附件|附表|另附|附录|补充协议|另行约定|付款计划表|另行签署")
PROVISIONAL = re.compile(
    r"仅供讨论|仅供参考|草案|草稿|未确认|未签认|未经确认|待.{0,8}(?:确认|签认|签署)|作废|暂不执行"
)
WHOLE = re.compile(
    r"(?:本合同|本协议|合同整体)(?:为|系|尚|暂|仍|仅|草|待|未|作废|不生效)"
)
DETAILS = {
    "continued": "各期付款条款可在同一份原件中逐行定位。",
    "foreign": "续页引用的完整合同编号与正文不同。请取得对应合同或双方确认的现行付款表。",
    "provisional": "付款页载有拟议或尚待确认的说明。请核对双方最终确认的付款安排。",
    "attachment": "原件涉及独立附表或补充约定。请核实该版本是否纳入已签合同。",
    "duplicate": "同一期次或合同标题在原件中重复出现。请核对页序、版本及完整条款。",
    "numeral": "原页的期款数字有断字或特殊数字字符。请逐字核定约定比例与对应款项。",
    "identity": "正文标题、完整编号或续页所引编号尚待核清。",
    "scope": "付款依据还有未归入已核条款的原文，请核对其适用范围。",
    "source": "付款条款所在合同有影像、辨读异议或未获原行支持的记录，请核图。",
    "terms": "原件上的期次与已提取的付款约定尚未逐行对应。",
}
INDEPENDENT = "首款约定:首笔款项按合同正文独立执行,续页修改不影响首笔款项"
PAGE_DRAFT = {
    "本页付款安排仅供讨论,双方未确认",
    "续页说明:本页付款安排仅供讨论,双方未确认",
}
SEVERITY = (
    "foreign",
    "provisional",
    "attachment",
    "duplicate",
    "numeral",
    "source",
    "identity",
    "terms",
    "scope",
)
HINT = re.compile(
    r"付款|支付|结算|预付|质保金|保留款|尾款|第[一二三四五六七八九十两0-9]+期"
)


def literal(value):
    return unicodedata.normalize("NFKC", value).strip()


def complete_number(value):
    # Keep internal whitespace, redactions and uncertainty visible when comparing identifiers.
    return (
        complete_id(value)
        and value
        not in {"不详", "未提供", "待填写", "未知", "不适用", "见正文", "见合同"}
        and not re.search(r"暂定|待补|同上|未载|尾号|脱敏", value)
    )


def classify(raw, facts, first, version, transcription):
    from graph import PRINTED_TITLES
    from performance import STAGE_PREFIX

    def matches(fact):
        if transcription and transcription["ref"] == fact["id"]:
            return True
        if version == FORMAT and fact["field"] in {*folio_transcription.FIELDS, "contract_id"}:
            parts = re.split(r"[:：]", raw, maxsplit=1)
            if len(parts) == 2:
                if fact["field"] in folio_transcription.FIELDS and folio_transcription.ambiguous_number(parts[1]):
                    return False
                if fact["value"].strip().removesuffix("。") not in (parts[1].strip().removesuffix("。"), raw.strip().removesuffix("。")):
                    return False
        return standard_contract_line(raw, [fact])

    text = literal(raw)
    label, sep, _ = text.partition(":")
    label = label.strip()
    if first and text == INDEPENDENT:
        return {"kind": "independent"}
    if PROVISIONAL.search(text):
        return {"kind": "provisional", "whole": bool(WHOLE.search(text))}
    if sep and label in IDS:
        # Compatibility folds can turn circled digits or a full-width identifier into a different printed number.
        original = re.split(r"[:：]", raw, maxsplit=1)
        value = original[1].strip() if len(original) == 2 else ""
        standard = first and label in ROOT_IDS
        return {
            "kind": "root_id" if standard else "related_id",
            "number": value if complete_number(value) else None,
            "anchored": any(
                f["field"] == "contract_id" and matches(f)
                for f in facts
            ),
        }
    if ANNEX.search(text):
        return {"kind": "attachment"}
    if PRINTED_TITLES.get(text) == "contract":
        return {
            "kind": "title",
            "anchored": any(
                f["field"] == "contract" and matches(f)
                for f in facts
            ),
        }
    if text in CONTINUATIONS:
        return {"kind": "heading"}
    prefix = STAGE_PREFIX.match(text)
    if prefix:
        label = prefix[0][:-1]
        return {
            "kind": "stage",
            "label": label,
            **({"ambiguous_body": body} if version == FORMAT and (body := folio_transcription.ambiguous_stage(raw)) else {}),
            "observations": [
                f["id"]
                for f in facts
                if f["field"] in ("payment_stage", "payment_term")
                and matches(f)
            ],
        }
    if any(matches(f) for f in facts):
        return {"kind": "transcription"} if transcription else None
    return {"kind": "qualification"}


def sources(graph, read_text, version=FORMAT, *, calls=None):
    from graph import compact, index_lines
    from warranty_terms import dedicated as warranty_clause

    contracts = set(graph["documents_by_kind"].get("contract", []))
    pages_by_doc = defaultdict(list)
    for page in graph["nodes"]:
        if page["type"] == "page":
            doc, suffix = page["id"].rsplit("/p", 1)
            # Split document sections are deliberately never joined across physical originals or titles.
            if doc in contracts:
                pages_by_doc[doc].append((int(suffix), page))
    docs = {d["id"]: d for d in graph["documents"]}
    facts_by_page = defaultdict(list)
    for f in graph["facts"]:
        if f.get("unit", f["doc"]) in contracts:
            facts_by_page[f["doc"], f["page"]].append(f)
    result = {"format": version, "pages": [], "lines": []}
    for doc, candidates in pages_by_doc.items():
        first_text = None
        if len(candidates) < 2:
            n, page = candidates[0]
            if version == LEGACY or page.get("layer") != "text":
                continue
            first_text = read_text(doc, n)
            if not any(folio_transcription.ambiguous_stage(line) for line in first_text.splitlines()):
                continue
        pages, lines = [], []
        relevant = False
        for n, page in sorted(candidates):
            native = page.get("layer") == "text"
            physical = []
            if native:
                text = first_text if first_text is not None else read_text(doc, n)
                if not isinstance(text, str) or hashlib.sha256(
                    text.encode()
                ).hexdigest() != page.get("text_sha256"):
                    raise ValueError("合同付款续页的文字摘要与原页不符")
                physical = text.splitlines()
            here = {
                "doc": doc,
                "unit": doc,
                "page": n,
                "source_sha256": docs[doc]["sha256"],
                "page_sha256": page["sha256"],
            }
            pages.append(
                {
                    **here,
                    "native": native,
                    "text_only": page.get("clause_text_only") is True,
                    "content_lines": sum(not is_page_marker(raw) for raw in physical),
                }
            )
            located = defaultdict(list)
            comparisons = {}
            unlocated = []
            observations = facts_by_page[doc, n]
            positions = index_lines(text) if native and version == FORMAT else {}
            references = Counter((f.get("source_line") or {}).get("number") for f in observations)
            for f in observations:
                loc = f.get("source_line") or {}
                i = loc.get("number")
                if type(i) is int and 0 < i <= len(physical) and loc.get("rects") and loc["text"] == physical[i - 1]:
                    raw = physical[i - 1]
                    if (
                        version == FORMAT and page.get("clause_text_only") is True and references[i] == 1
                        and f.get("page_sha256") == here["page_sha256"] and f.get("source_sha256") == here["source_sha256"]
                        and positions.get(compact(raw).strip("。;；")) == (i, raw)
                    ):
                        match = folio_transcription.compare(raw, f)
                        if match:
                            basis = folio_transcription.witness(f, (calls or {}).get((doc, n), {}))
                            if basis:
                                comparisons[i] = {**match, "basis": basis}
                    same_quote = literal(f["quote"]) == literal(raw) if version == LEGACY else f["quote"] == raw
                    if same_quote or i in comparisons:
                        located[i].append(f)
                        continue
                if not is_page_marker(f["quote"]):
                    unlocated.append(f)
            relevant |= any(
                f["field"] in ("payment_stage", "payment_term")
                for f in facts_by_page[doc, n]
            )
            for i, raw in enumerate(physical, 1):
                if is_page_marker(raw):
                    continue
                relevant |= bool(HINT.search(raw))
                facts = located[i]
                comparison = comparisons.get(i)
                detail = classify(raw, facts, n == 1, version, comparison)
                if len(candidates) == 1 and detail == {"kind": "qualification"} and warranty_clause(raw) and any(
                    f["field"] in ("warranty_period", "warranty_condition") and f["status"] in ("anchored", "confirmed")
                    and f["quote"] == raw and re.split(r"[:：]", raw, maxsplit=1)[-1] == f["value"] for f in facts
                ):
                    # Warranty timing and release conditions are checked against their own phase.
                    detail = None
                disputed = any(
                    f["status"] == "disputed"
                    or f.get("visual_check") in ("conflict", "unreadable")
                    and f["status"] != "confirmed"
                    for f in facts
                )
                if not detail and not disputed:
                    continue
                lines.append(
                    {
                        **here,
                        **(detail or {"kind": "qualification"}),
                        **({"transcription": comparison} if comparison else {}),
                        "line": i,
                        "quote": raw,
                        "id": f"contract-folio/{doc}/p{n}/l{i}",
                        "facts": [f["id"] for f in facts],
                        "supported": native
                        and page.get("clause_text_only") is True
                        and not disputed,
                    }
                )
            for f in unlocated:
                relevant |= bool(HINT.search(f["quote"]))
                lines.append(
                    {
                        **here,
                        "kind": "unlocated",
                        "line": None,
                        "quote": f["quote"],
                        "id": "contract-folio/" + f["id"],
                        "facts": [f["id"]],
                        "supported": False,
                    }
                )
        if relevant:
            result["pages"].extend(pages)
            result["lines"].extend(lines)
    return result


def source_graph(ledger):
    nodes, edges = [], []
    for row in ledger["lines"]:
        page = f"{row['doc']}/p{row['page']}"
        nodes.append(
            {
                "id": row["id"],
                "type": "contract_folio_line",
                "label": row["quote"],
                "doc": row["doc"],
                "page": row["page"],
                "line": row["line"],
            }
        )
        edges.append(
            {
                "from": page,
                "to": row["id"],
                "type": "contract_folio_basis",
                "evidence": [page, *row["facts"]],
            }
        )
    return nodes, edges


def assess(ledger, unit, stage_refs):
    pages = [p for p in ledger.get("pages", []) if p["unit"] == unit]
    if not pages:
        return None
    lines = [s for s in ledger["lines"] if s["unit"] == unit]
    primary = [r for r in lines if r["kind"] == "root_id"]
    titles = [r for r in lines if r["kind"] == "title"]
    root = primary[0] if len(primary) == 1 else None
    rooted = bool(root and root["supported"] and root["anchored"] and root["number"])
    title_ok = (
        len(titles) == 1
        and titles[0]["page"] == 1
        and titles[0]["supported"]
        and titles[0]["anchored"]
    )
    stages = [r for r in lines if r["kind"] == "stage"]
    counts = Counter(r["label"] for r in stages)
    views = []
    evidence = []
    for page in pages:
        n = page["page"]
        ref = f"{unit}/p{n}"
        reasons = []
        if not page["native"] or not page["text_only"]:
            reasons.append(("source", None))
        selected = [r for r in lines if r["page"] == n]
        related = [r for r in selected if r["kind"] == "related_id"]
        if n == 1 and (not rooted or not title_ok):
            reasons.append(("identity", root and root["id"]))
        if len(related) > 1 or n == 1 and related:
            reasons.append(("identity", related[0]["id"]))
        if not page["content_lines"] or n != len(views) + 1:
            reasons.append(("source", None))
        for r in selected:
            kind = r["kind"]
            issue = None
            if kind == "stage" and r.get("ambiguous_body") and page["native"] and page["text_only"]:
                issue = "numeral"
            elif not r["supported"]:
                issue = "source"
            elif kind == "related_id":
                if not rooted or not r["number"]:
                    issue = "identity"
                elif r["number"] != root["number"]:
                    issue = "foreign"
            elif kind == "title" and (n != 1 or len(titles) != 1):
                issue = "duplicate"
            elif kind == "stage":
                if counts[r["label"]] > 1:
                    issue = "duplicate"
                elif (
                    len(r["observations"]) != 1
                    or r["observations"][0] not in stage_refs
                ):
                    issue = "terms"
            elif kind in ("provisional", "attachment"):
                issue = kind
            elif kind == "qualification":
                issue = "scope"
            if issue:
                reasons.append((issue, r["id"]))
        state = next(
            (s for s in SEVERITY if any(reason == s for reason, _ in reasons)),
            "continued",
        )
        default = next((r for reason, r in reasons if reason == state and r), None)
        if default is None:
            default = next(
                (
                    r["id"]
                    for r in selected
                    if r["kind"] in ("root_id", "related_id", "stage")
                ),
                None,
            )
        views.append(
            {
                "page": n,
                "ref": ref,
                "state": state,
                "focus": default,
                "issues": [{"state": why, "ref": ref} for why, ref in reasons],
                "lines": [r["id"] for r in selected],
                "stages": [r["label"] for r in selected if r["kind"] == "stage"],
            }
        )
        evidence.append(ref)
        for r in selected:
            evidence.extend([r["id"], *r["facts"]])
    state = next(
        (s for s in SEVERITY if any(p["state"] == s for p in views)), "continued"
    )
    standalone = None
    clauses = [r for r in lines if r["kind"] == "independent"]
    first = [r for r in stages if r["page"] == 1]
    holds = {issue["ref"] for p in views for issue in p["issues"]}
    local_drafts = {
        r["id"]
        for r in lines
        if r["page"] > 1
        and r["supported"]
        and r["kind"] == "provisional"
        and literal(r["quote"]) in PAGE_DRAFT
    }
    if (
        views[0]["state"] == "continued"
        and state == "provisional"
        and holds == local_drafts
        and len(clauses) == len(first) == 1
        and first[0]["label"] in ("第一期", "第1期")
        and len(first[0]["observations"]) == 1
    ):
        standalone = {
            "clause_ref": first[0]["observations"][0],
            "authority": clauses[0]["id"],
        }
    return {
        "state": state,
        "standalone": standalone,
        "status": "ok"
        if state == "continued"
        else "risk"
        if state == "foreign"
        else "missing",
        "detail": DETAILS[state],
        "unit": unit,
        "root_ref": root["id"] if root else None,
        "pages": views,
        "whole": [r["id"] for r in lines if r.get("whole")],
        "evidence": list(dict.fromkeys(evidence)),
    }


def attach(finding, check):
    finding["evidence"] = list(
        dict.fromkeys([*finding["evidence"], *check["evidence"]])
    )
    if check["status"] == "ok":
        return
    if finding["status"] == "ok":
        finding.update(status=check["status"], detail=check["detail"])
    else:
        finding["detail"] += " " + check["detail"]
        if finding["status"] == "missing" and check["status"] == "risk":
            finding["status"] = "risk"


def withhold_shares(rows, ledger, unit):
    """Keep physical text for an ambiguous phase and leave its computational share empty."""
    if ledger.get("format") != FORMAT:
        return
    ambiguous = defaultdict(list)
    for record in ledger["lines"]:
        if record["unit"] == unit and record.get("ambiguous_body"):
            ambiguous[record["label"]].append(record)
    for row in rows:
        records = ambiguous.get(row["label"])
        if records:
            original = next((r for r in records if row["ref"] in r["facts"]), None)
            if not original and len(records) == 1:
                original = records[0]
            row.update(share="", kind="", condition="", ambiguous_number=True,
                       text=original["ambiguous_body"] if original else "本期原文存在多个候选")


def page_lines(ledger):
    numbers = defaultdict(list)
    for row in ledger["lines"]:
        if row["line"] is not None:
            numbers[row["doc"], row["page"]].append(str(row["line"]))
    return numbers


def geometry(numbers, layer):
    return {n: layer.get("lines", {}).get(n, []) for n in numbers}


def verify_geometry(report, ledger, read_layout=None):
    numbers = page_lines(ledger)
    facts = {f["id"]: f for f in report["graph"]["facts"]}
    transcribed = defaultdict(dict)
    for row in ledger["lines"]:
        if proof := row.get("transcription"):
            transcribed[row["doc"], row["page"]][str(row["line"])] = facts[proof["ref"]]["source_line"]["rects"]
    for call in report["calls"]["pages"]:
        address = (call["doc"], call["page"])
        saved = call.get("contract_folio_rects")
        expected = numbers.pop(address, [])
        if not expected and saved is None:
            continue
        if not expected or not isinstance(saved, dict) or set(saved) != set(expected):
            raise ValueError("合同付款续页定位的行号与分页记录不符")
        for rects in saved.values():
            if not isinstance(rects, list) or any(
                not isinstance(rect, list)
                or len(rect) != 4
                or not all(
                    type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1
                    for x in rect
                )
                or rect[0] >= rect[2]
                or rect[1] >= rect[3]
                for rect in rects
            ):
                raise ValueError("合同付款续页的原行坐标不符")
        if any(not saved[line] or saved[line] != rects for line, rects in transcribed[address].items()):
            raise ValueError("付款续页转录对照的行框与原文观察不符")
        if read_layout and geometry(expected, read_layout(*address)) != saved:
            raise ValueError("合同付款续页定位与原件分页不符")
    if numbers:
        raise ValueError("合同付款续页缺少分页记录")


def check_older_approval(graph, findings, read_text, calls):
    positive = [f for f in findings if f["status"] == "ok" and f["rule"] in ("H01", "H03", "H04", "H05")]
    if not positive:
        return
    ledger = sources(graph, read_text, calls=calls)
    stages = {f["stage"]["clause_ref"] for f in findings if f["rule"] == "H04" and f.get("stage")}
    for unit in graph["documents_by_kind"].get("contract", []):
        check = assess(ledger, unit, stages)
        if not check:
            continue
        for f in positive:
            if unit not in f["scope"]:
                continue
            if f["rule"] == "H01":
                if not check["whole"]:
                    continue
            elif check["status"] == "ok" or (
                f["rule"] == "H04" and check["standalone"] and
                (f.get("stage") or {}).get("clause_ref") == check["standalone"]["clause_ref"]
            ):
                continue
            raise ValueError("旧版未核清付款续页的适用依据，请重新审计后签收。")


def verify(report, read_text, *, signing=False, read_layout=None):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("contract_folios")
    nodes = [n for n in graph["nodes"] if n["type"] == "contract_folio_line"]
    edges = [e for e in graph["edges"] if e["type"] == "contract_folio_basis"]
    findings = report["findings"]
    calls = {(p["doc"], p["page"]): p for p in report.get("calls", {}).get("pages", [])}
    if marker is None:
        if (
            policy.get("version", "") >= SINCE
            or "contract_folios.py" in policy.get("code_sha256", {})
            or "contract_folio_sources" in graph
            or nodes
            or edges
            or any("contract_folios" in f for f in findings)
            or any(
                "contract_folio_rects" in c
                for c in report.get("calls", {}).get("pages", [])
            )
        ):
            raise ValueError("缺少合同付款续页程序标记")
        if signing:
            check_older_approval(graph, findings, read_text, calls)
        return
    expected = FORMAT if policy.get("version", "") >= TRANSCRIPTION_SINCE else LEGACY
    ledger = sources(graph, read_text, expected, calls=calls)
    if (
        marker != expected
        or policy.get("version", "") < SINCE
        or marker != FORMAT and "folio_transcription.py" in policy.get("code_sha256", {})
        or graph.get("contract_folio_sources") != ledger
        or (nodes, edges) != source_graph(ledger)
    ):
        raise ValueError("合同付款续页原文、页序或证据关系与归档不符")
    verify_geometry(report, ledger, read_layout)
    if signing and marker == LEGACY:
        check_older_approval(graph, findings, read_text, calls)
