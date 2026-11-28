"""Distinguish a request or an acceptance-only notice from evidence of an executed debit."""

import hashlib
import re
from collections import defaultdict
from unicodedata import normalize


FIRST_FORMAT = "payment-execution-basis-v1"
FORMAT = "payment-execution-basis-v2"
KEY = "payment_execution_sources"
SINCE = (2026, 11, 26, 25)
RETURN_SINCE = (2026, 11, 28, 20)
REQUESTS = {"付款申请单", "付款申请书", "对公付款申请单", "银行转账申请单", "转账申请单", "付款审批单",
            "银行受理回执", "转账受理回执", "付款申请受理回执", "网银转账受理回执"}
BANK_TITLES = {"银行付款回单", "银行转账回单", "电子银行回单", "银行电子回单", "转账回单"}
STATUS = {"交易状态", "转账状态", "申请状态", "受理状态", "审批状态"}
SUCCESS = {"交易成功", "转账成功", "付款成功", "支付成功", "成功", "已完成", "已记账", "已入账"}
ACCEPTED = {"受理成功", "已受理", "银行已受理", "提交成功", "审批通过", "等待扣款", "待扣款"}
LIMIT = re.compile(
    r"(?:仅(?:为|表明|说明|代表|证明|表示|作(?:为)?)|只(?:表明|代表|说明)).{0,24}受理"
    r"|(?:尚未|并未|未经)(?:实际|完成)?扣款"
    r"|(?:不代表|不等于|不能证明|不能作为|不作为|不构成|并非).{0,12}(?:实际扣款|已扣款|扣款成功|付款成功|转账成功|转账最终处理结果|付款方交易(?:确认)?的最终依据)"
    r"|(?:扣款|实际支付)(?:是否成功|结果)?以.{0,14}(?:银行对账单|银行流水|实际扣款结果|最终处理结果)为准"
    r"|以(?:实际扣款|银行最终扣款|账户实际扣账)结果为准"
)
NOTE_PREFIXES = ("备注", "回单备注", "重要提示", "温馨提示", "友情提示", "回单提示", "凭证说明", "回单说明", "处理说明", "受理说明")
RETURN_COLUMNS = {"交易附注","回单附注","交易备注","银行附注","退汇说明","冲正说明",*NOTE_PREFIXES,*STATUS}
RETURN_STATUS = {"冲正状态","冲正结果","退汇状态","退汇结果"}
THIS_TRANSFER = r"(?:本笔|该笔)(?:交易|转账|汇款|款项|付款)?"
RETURN_EVENT = r"(?:已经|已|发生)?(?:全额|部分)?(?:冲正|退汇)(?:成功|完成)?"
RECORDED_RETURN = re.compile(THIS_TRANSFER + RETURN_EVENT + r"[。.]?")
POSSIBLE_RETURN = re.compile(THIS_TRANSFER + r"(?:是否|疑似|可能|拟|待)?"+ RETURN_EVENT)
RETURN_KINDS = {"return_notice","return_pending"}
RETURN_STATES = {"return_noted","return_review"}
DETAIL = {
    "conflict": "凭证状态栏列示成功，原页同时限定其证明范围。需取得本笔实际扣款凭证后核对付款时点。",
    "limited": "该凭证载有受理或扣款限定，实际执行结果需以本笔正式回单或扣款流水复核。",
    "application": "本单列示付款申请或受理记录，需取得并关联本笔实际扣款凭证。",
    "review": "页内有待辨的申请或受理说明，请核实原页及本笔实际扣款凭证。",
    "return_noted": "回单状态栏记载成功，另有本笔冲正或退汇记录。请按交易流水号核对原扣款、返还金额和日期，并查明是否另行支付本期款项。",
    "return_review": "回单另有冲正或退汇说明，其与本笔付款的关系待核。请取得原扣款及后续处理流水，核实本期实际支付金额和日期。",
}


def normalized(text):
    return normalize("NFKC", text).strip()


def return_kind(text):
    label, sep, value = text.partition(":")
    label, value = label.strip(), value.strip()
    if sep and label in RETURN_STATUS:
        event = label[:2]
        if value.rstrip("。.") in {"成功","完成","已完成",event+"成功","已"+event,"已全额"+event,"已部分"+event}:
            return "return_notice"
        if value.rstrip("。.") in {"待核","待处理","处理中","待确认"}:
            return "return_pending"
    if sep and label not in RETURN_COLUMNS:
        return None
    body = value if sep else text
    if RECORDED_RETURN.fullmatch(body) or label in STATUS and re.fullmatch(r"(?:已|已全额|已部分)(?:冲正|退汇)[。.]?",body):
        return "return_notice"
    if POSSIBLE_RETURN.match(body):
        return "return_pending"
    return None


def kind(raw, *, heading, returns=False):
    text = normalized(raw)
    if returns and (found := return_kind(text)):
        return found
    if heading and text in REQUESTS:
        return "request"
    if heading and text in BANK_TITLES:
        return "title"
    if LIMIT.search(text):
        return "limit"
    label, sep, value = text.partition(":")
    if sep and label.strip() in STATUS:
        if value.strip() in ACCEPTED:
            return "pending_status"
        return "status"
    if sep and label.strip() in {"款项用途", "申请用途", "付款期次说明", "转账用途", "付款用途"}:
        return "purpose"
    if sep and label.strip() in {"受理时间", "申请时间", "付款申请时间", "银行受理时间"}:
        return "request_time"
    return None


def page_units(graph):
    parts = {(d["source"], d["page"]): d["id"] for d in graph.get("audit_documents", []) if "source" in d}
    for node in graph["nodes"]:
        if node["type"] == "page":
            doc, n = node["id"].rsplit("/p", 1)
            number = int(n)
            yield doc, number, parts.get((doc, number), doc), node


def bank_pages(graph):
    banks = set(graph["documents_by_kind"].get("bank_receipt", []))
    return {(doc, page) for doc, page, unit, _ in page_units(graph) if unit in banks}


def sources(graph, read_text, *, banks_only=False, version=FORMAT):
    if version not in (FIRST_FORMAT,FORMAT):
        raise ValueError("付款执行依据的程序版本不符")
    banks = set(graph["documents_by_kind"].get("bank_receipt", []))
    other = {u for k, group in graph["documents_by_kind"].items() if k != "bank_receipt" for u in group}
    observations = defaultdict(list)
    for f in graph["facts"]:
        observations[f["doc"], f["page"]].append(f)
    by_unit = defaultdict(list)
    clear_pages = set()
    partial = {(g["doc"], g["page"]) for g in graph.get("gaps", []) if g.get("quality") in ("partial", "unreadable", "section_unresolved")}
    for doc, page, unit, node in page_units(graph):
        if unit not in banks and (banks_only or unit in other):
            continue
        text = []
        if node.get("layer") == "text" and node.get("text_sha256"):
            raw = read_text(doc, page)
            if not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != node["text_sha256"]:
                raise ValueError("付款凭证说明与原页文字摘要不符")
            text = raw.splitlines()
            if node.get("clause_text_only") is True and (doc, page) not in partial and unit not in other:
                clear_pages.add((doc, page))
        facts = observations[doc, page]
        located = defaultdict(list)
        detached = []
        for fact in facts:
            loc = fact.get("source_line") or {}
            i = loc.get("number")
            if (type(i) is int and 0 < i <= len(text) and loc.get("rects") and loc.get("text") == text[i-1]
                    and normalized(fact["quote"]) == normalized(text[i-1])):
                located[i].append(fact)
            else:
                detached.append(fact)
        def add(role, line, quote, seen):
            place = f"{doc}/p{page}/l{line}" if line else seen[0]["id"]
            by_unit[unit].append({"id": "execution/"+place, "unit": unit, "doc": doc, "page": page,
                                  "line": line, "kind": role, "quote": quote, "facts": [f["id"] for f in seen],
                                  "disputed": any(f["status"] == "disputed" for f in seen)})
        returns = version == FORMAT
        roles = [kind(s, heading=i < 4, returns=returns) for i, s in enumerate(text)]
        # Preserve both original lines when a limiting sentence wraps inside the decisive words.
        for i in range(len(text)-1):
            a, b = normalized(text[i]), normalized(text[i+1])
            if (not roles[i] and not roles[i+1] and a and b and ":" not in b and len(a)+len(b) <= 200
                    and (a.startswith(NOTE_PREFIXES) or a.startswith(("本回单", "本回执", "本单")))
                    and LIMIT.search(a+b)):
                roles[i] = roles[i+1] = "wrapped_limit"
        for i, role in enumerate(roles, 1):
            if role:
                add(role, i, text[i-1], located[i])
        for fact in detached:
            role = kind(fact["quote"], heading=True, returns=returns)
            if role:
                add(role, None, fact["quote"], [fact])

    units, rows = [], []
    for unit, found in by_unit.items():
        requests = [r for r in found if r["kind"] == "request"]
        limits = [r for r in found if r["kind"] in ("limit", "wrapped_limit")]
        titles = [r for r in found if r["kind"] == "title"]
        if unit not in banks and not titles:
            found = [r for r in found if r["kind"] not in RETURN_KINDS]
        returns = [r for r in found if r["kind"] in RETURN_KINDS]
        if not returns and not requests and not (limits and (unit in banks or titles)):
            continue
        restrictions = requests + limits
        native = [r for r in restrictions if r["line"] and not r["disputed"]]
        explicit = {(r["doc"], r["page"]) for r in native if (r["doc"],r["page"]) in clear_pages and r["kind"] != "wrapped_limit" and
                    not any(s in normalized(r["quote"]) for s in ("如遇", "如果", "若", "当状态为", "当交易", "如交易", "如为", "如显示", "示例"))}
        success = [r for r in found if r["kind"] == "status" and r["line"] and not r["disputed"]
                   and normalized(r["quote"]).partition(":")[0].strip() in ("交易状态", "转账状态")
                   and normalized(r["quote"]).partition(":")[2].strip() in SUCCESS]
        if returns and not (limits or requests):
            # A posted debit and its subsequent return can both be genuine. Reconcile them before dating or summing settlement.
            statuses = [r for r in found if r["kind"] in ("status","pending_status")]
            paired = (unit in banks and len(statuses)==len(success)==1 and len(titles)==1 and len(returns)==1 and
                      returns[0]["kind"]=="return_notice" and returns[0]["line"] and not returns[0]["disputed"] and
                      (success[0]["doc"],success[0]["page"])==(returns[0]["doc"],returns[0]["page"]) in clear_pages)
            state = "return_noted" if paired else "return_review"
        elif unit in banks and any((r["doc"], r["page"]) in explicit for r in success):
            state = "conflict"
        elif not explicit or (unit not in banks and not any(r["line"] and not r["disputed"] for r in requests + titles)):
            state = "review"
        else:
            state = "application" if requests else "limited"
        units.append({"unit": unit, "bank": unit in banks, "state": state, "rows": [r["id"] for r in found]})
        rows.extend(found)
    return {"format": version, "units": units, "rows": rows}


def source_graph(ledger):
    nodes, edges = [], []
    for r in ledger["rows"]:
        page = f"{r['doc']}/p{r['page']}"
        nodes.append({"id": r["id"], "type": "payment_execution_line", "label": r["quote"],
                      "doc": r["doc"], "page": r["page"], "line": r["line"]})
        edges.append({"from": page, "to": r["id"], "type": "payment_execution_source", "evidence": [page, *r["facts"]]})
    return nodes, edges


def entry(graph, unit):
    return next((u for u in graph.get(KEY, {}).get("units", []) if u["unit"] == unit), None)


def refs(graph, unit):
    return list(dict.fromkeys(ref for r in graph[KEY]["rows"] if r["unit"] == unit
                              for ref in (r["id"], f"{r['doc']}/p{r['page']}", *r["facts"])))


def return_evidence(graph, findings):
    rows = graph.get(KEY, {}).get("rows", ())
    units = {r["unit"] for r in rows if r["kind"] in RETURN_KINDS}
    if not units:
        return []
    cited = {ref for f in findings if f["rule"] in ("H05","H06","B04","B05") for ref in f["evidence"]}
    return [r for r in rows if r["unit"] in units and r["id"] in cited and
            (r["kind"] in RETURN_KINDS or r["kind"] in ("status","pending_status"))]


def verify_return_originals(report, read_original):
    from payment_quality import verify_units
    rows = return_evidence(report["graph"],report["findings"])
    if not rows:
        return
    calls = {(p["doc"],p["page"]):p for p in report["calls"]["pages"]}
    located = [{**r,"rects":calls[r["doc"],r["page"]]["payment_execution_rects"][str(r["line"])]} for r in rows if r["line"]]
    verify_units(report["graph"],{r["unit"] for r in rows},read_original,"冲正或退汇凭证",extra_lines=located)


def apply(graph, findings):
    from installment_approval import recognized
    from performance import result
    seen = set()
    for finding in findings:
        if finding["rule"] != "H05":
            continue
        banks = [u for u in graph["documents_by_kind"].get("bank_receipt", []) if u in finding["scope"]]
        item = entry(graph, banks[0]) if len(banks) == 1 else None
        if item:
            seen.add(item["unit"])
            unit, state = item["unit"], item["state"]
            replacement = result("H05", "risk" if state == "conflict" else "missing", DETAIL[state],
                                 [*finding["evidence"], *refs(graph, unit)], finding["scope"], finding.get("stage"))
            # Time, amount and maturity comparisons for an executed transfer need independent execution evidence.
            finding.clear()
            finding.update(replacement, execution_basis=item)
    approvals = recognized(graph) if graph["documents_by_kind"].get("bank_receipt") else set()
    for item in graph.get(KEY, {}).get("units", []):
        if not item["bank"] and item["state"]=="application" and item["unit"] in approvals:
            continue
        if item["unit"] not in seen:
            state, unit = item["state"], item["unit"]
            finding = result("H05", "risk" if state == "conflict" else "missing", DETAIL[state], refs(graph, unit), [unit])
            findings.append({**finding, "execution_basis": item})


def verify(report, read_text, *, signing=False, read_layout=None):
    from contract_folios import line_numbers, verify_page_geometry

    graph, policy = report["graph"], report["policy"]
    marker = policy.get("payment_execution")
    nodes = [n for n in graph["nodes"] if n["type"] == "payment_execution_line"]
    edges = [e for e in graph["edges"] if e["type"] == "payment_execution_source"]
    calls = report.get("calls", {}).get("pages", [])
    version = tuple(map(int,(policy.get("version") or "0").split(".")))
    if not marker:
        if (KEY in graph or nodes or edges or "payment_execution.py" in policy.get("code_sha256", {})
                or version >= SINCE
                or any("execution_basis" in f for f in report["findings"]) or any("payment_execution_rects" in c for c in calls)):
            raise ValueError("底稿缺少付款凭证证明范围的程序")
        if signing and any(f["rule"] in ("H04","H05","H06","B04","B05") for f in report["findings"]):
            if sources(graph, read_text)["units"]:
                raise ValueError("旧版付款材料含申请或受理限定，请重审实际扣款凭证后签收。")
        return
    if marker != (FORMAT if version >= RETURN_SINCE else FIRST_FORMAT) or ("code_sha256" in policy and "payment_execution.py" not in policy["code_sha256"]):
        raise ValueError("付款执行依据的程序版本不符")
    ledger = sources(graph, read_text, version=marker)
    if graph.get(KEY) != ledger or (nodes, edges) != source_graph(ledger):
        raise ValueError("付款状态、受理限定原行或物理页归属不符")
    if signing and marker == FIRST_FORMAT:
        exposed = {u for f in report["findings"] if f["rule"] in ("H05","H06","B04","B05") for u in f.get("scope",())}
        if exposed.intersection(graph["documents_by_kind"].get("bank_receipt",())) and any(
                r["kind"] in RETURN_KINDS and r["unit"] in exposed for r in sources(graph,read_text,banks_only=True)["rows"]):
            raise ValueError("旧版未核实本笔冲正或退汇记录，请核对扣款、返还流水并重审后签收。")
    from config import BANK
    if policy.get("profile") == BANK and any(u["bank"] for u in ledger["units"]):
        checks = [f for f in report["findings"] if f["rule"] in ("B04", "B05")]
        if {f["rule"] for f in checks} != {"B04", "B05"} or any(f["status"] not in ("missing", "risk") or f.get("calculations") for f in checks):
            raise ValueError("实际扣款依据不足，银行结论或差额与原件不符")
        if any(f["rule"] == "B01" and f["status"] == "ok" for f in report["findings"]):
            bank, = graph["documents_by_kind"]["bank_receipt"]
            state = entry(graph, bank)["state"]
            expected = {"B04": "missing", "B05": "risk" if state == "conflict" else "missing"}
            required = set(refs(graph, bank))
            if len(checks) != 2 or any(f["status"] != expected[f["rule"]] or not required.issubset(f["evidence"]) for f in checks):
                raise ValueError("银行结论与受理限定所据原行不符")
    if "calls" in report:
        facts = {f["id"]: f for f in graph["facts"]}
        observed = defaultdict(dict)
        for row in ledger["rows"]:
            for ref in row["facts"]:
                loc = facts[ref].get("source_line") or {}
                if row["line"] and loc.get("number") == row["line"] and loc.get("text") == row["quote"] and loc.get("rects"):
                    observed[row["doc"],row["page"]][str(row["line"])] = loc["rects"]
        verify_page_geometry(calls, line_numbers(ledger["rows"]), observed, "payment_execution_rects", "付款凭证说明", read_layout)
    rows = return_evidence(graph,report["findings"])
    expert = report.get("calls",{}).get("expert",{})
    if marker==FORMAT and ("input" in expert or expert.get("request_format")):
        packet = expert.get("input")
        expected = [(f["rule"],f["execution_basis"]) for f in report["findings"] if f.get("execution_basis")]
        if (not isinstance(packet,dict) or packet.get("payment_return_sources")!=(rows or None) or expected!=[
                (f["rule"],f["execution_basis"]) for f in packet.get("procedures",()) if f.get("execution_basis")]):
            raise ValueError("专家输入与底稿所据付款凭证或冲正、退汇原行不符")
    if rows and (calls or policy.get("archived_methods")):
        by_page = {(p["doc"],p["page"]):p for p in calls}
        pages = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
        for r in rows:
            call = by_page.get((r["doc"],r["page"]),{})
            second = (call.get("check") or {}).get("response_id")
            if (not second or not call.get("response_id") or second==call["response_id"] or
                    call.get("page_sha256")!=pages[f"{r['doc']}/p{r['page']}"]["sha256"]):
                raise ValueError("冲正或退汇说明缺少当版原页及独立核读记录")
