"""Generate and inspect four watermarked procurement cases with a first-payment guarantee."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib.request import urlopen
from zipfile import ZipFile

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from contract_milestones import PROFILE, documents
from generate import BUYER, WATERMARK, draw_pdf_page, embedded_font
from run import BASE, get, post, submit

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "server"))
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
from documents import render
from protocol import canonical
from verify import verify_request

SCRATCH = Path("/tmp/fish-advance-guarantee-27")
SEED = "synthetic-advance-guarantees-20261127-v1"
BASELINE = "2026.11.27.04"
FORMAT = "advance-payment-guarantee-v1"
CASES = {
    "only": "已开立预付款保函，未附采购方签收单",
    "late": "采购方在首期预付款支付后签收同号保函",
    "early": "采购方在首期预付款支付前签收同号保函",
    "wrong_beneficiary": "签收同号保函，受益人与合同明定的采购方不同",
}
CONTRACT = "采购合同"
BANK = "银行付款回单"
GUARANTEE = "预付款保函"
RECEIPT = "预付款保函签收单"
TERM = "采购方收到本合同项下的预付款保函后方可支付第一期预付款"
NAMED_TERM = "采购方收到以采购方为受益人的本合同项下预付款保函后方可支付第一期预付款"
ISSUER = "云岫演练担保中心"
OTHER_BENEFICIARY = "栖湾演练档案中心"


def digest(data):
    return sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as staged:
        staged.write(data)
    Path(staged.name).replace(path)


def run_folder(seed):
    return SCRATCH / ("run-" + digest(seed.encode())[:12])


def materials(seed, mode):
    code = digest((seed + "/" + mode).encode())[:12].upper()
    base = documents(code, "complete")
    contract_id = dict(base[CONTRACT])["合同编号"]
    number = "YL-BH-" + code
    contract = [*base[CONTRACT], ("预付款支付前提", NAMED_TERM if mode == "wrong_beneficiary" else TERM)]
    bank = {"付款金额": "30,000.00", "款项用途": "第一期", "付款日期": "2026年9月5日"}
    forms = {CONTRACT: contract, GUARANTEE: [
        ("合同编号", contract_id), ("保函编号", number),
        ("受益人", OTHER_BENEFICIARY if mode == "wrong_beneficiary" else BUYER),
        ("开立日期", "2026年9月2日"), ("开立机构", ISSUER)]}
    if mode != "only":
        forms[RECEIPT] = [("合同编号", contract_id), ("签收保函编号", number), ("签收单位", BUYER),
                          ("签收日期", "2026年9月8日" if mode == "late" else "2026年9月3日")]
    forms[BANK] = [(k, bank.get(k, v)) for k, v in base[BANK]] + [
        ("交易流水号", "YL-LS-" + code), ("银行附言", "本合同第一期预付款"), ("币种", "人民币"), ("金额单位", "元")]
    return forms


def write_form(path, title, rows, font):
    # Keep the long beneficiary condition on one physical line, with the original labels intact.
    form = canvas.Canvas(str(path), pagesize=(595, 842), invariant=1)
    form.setTitle(title)
    draw_pdf_page(form, title, [], font=font)
    for offset, (label, value) in enumerate(rows):
        line = label + "：" + value
        size = min(15, 500 / pdfmetrics.stringWidth(line, font, 1))
        form.setFont(font, size)
        form.drawString(48, 649 - 29 * offset, line)
    form.save()


def generate(seed, mode):
    folder = run_folder(seed) / mode
    folder.mkdir(parents=True, exist_ok=True)
    forms = materials(seed, mode)
    font = embedded_font("AdvanceGuaranteeSampleCJK")
    sources = {}
    for title, rows in forms.items():
        name = title + ".pdf"
        path = folder / name
        with tempfile.TemporaryDirectory(dir=folder) as temp:
            directory = Path(temp)
            new = directory / name
            write_form(new, title, rows, font)
            render(new, directory, 1)
            page, = json.loads((directory / "manifest.json").read_bytes())
            lines = page["text"].splitlines()
            require(lines == [WATERMARK, title, *(k + "：" + v for k, v in rows)], name + " 实页原文不完整")
            rects = page["layer"]["lines"]
            require(all(rects.get(str(i)) and all(0 < x < right < 1 and 0 < y < bottom < 1
                        for x, y, right, bottom in rects[str(i)]) for i in range(1, len(lines) + 1)), name + " 原行定位")
            original = new.read_bytes()
            if path.exists():
                require(path.read_bytes() == original, name + " 与此 seed 的原件不同")
            else:
                new.replace(path)
            sources[name] = {"original_sha256": digest(original), "page_sha256": page["sha256"],
                             "text_sha256": digest(page["text"].encode()),
                             "lines": [{"line": i, "text": line, "rects": rects[str(i)]} for i, line in enumerate(lines, 1)]}
    save_json(folder / "sources.json", sources)
    return folder, sources


def case_title(mode):
    return "合成演练 · " + CASES[mode]


def scoped_case(cid, mode, sources):
    case = get("/api/cases/" + cid)
    require(case["id"] == cid and case["title"] == case_title(mode) and case["profile"] == PROFILE
            and not case["decisions"] and not case.get("referrals")
            and {d["name"]: d["sha256"] for d in case["documents"]} ==
            {name: s["original_sha256"] for name, s in sources.items()}, "案件题名、原件、范围或人工验收记录不符")
    return case


def create_cases(seed):
    audit = get("/api/health")["audit"]
    controls = get("/api/controls")
    require(audit["provider"] == "openai" and audit["configured"] and get("/api/ready")["status"] == "ready"
            and (controls["version"] == BASELINE or controls.get("advance_guarantee") == FORMAT),
            "需要运行中的 .04 或含预付款保函专项规则的本地模型服务")
    root = run_folder(seed)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "cases.json"
    ids = json.loads(path.read_bytes()) if path.exists() else {}
    for mode in CASES:
        folder, sources = generate(seed, mode)
        if mode not in ids:
            key = "advance-guarantee-" + digest((seed + mode + "".join(s["original_sha256"] for s in sources.values())).encode())
            ids[mode] = submit(case_title(mode), [folder / name for name in sources], key, PROFILE)
            save_json(path, ids)
        scoped_case(ids[mode], mode, sources)
        print(mode, ids[mode], flush=True)
    return ids


def model_record(call, instructions, image=None):
    require(call["request_format"] == "responses-json-v1" and call["model"]
            and call["request_id"].startswith("req_") and call["response_id"].startswith("resp_")
            and min(call["usage"]["input_tokens"], call["usage"]["output_tokens"]) > 0, "模型调用缺少原始回执")
    verify_request(call, instructions, image)
    return {k: call[k] for k in ("model", "request_id", "response_id", "request_sha256")}


def inspect_version(folder, sources, cid, mode, rev, version, archive):
    with ZipFile(BytesIO(archive)) as bundle:
        raw = bundle.read("report.json")
        manifest = json.loads(bundle.read("manifest.json"))
        require(manifest["case_id"] == cid and manifest["revision"] == version["rev"] == rev and
                digest(raw) == manifest["report_sha256"] == version["sha256"] and
                raw == canonical(version["report"]).encode(), "固定底稿或版本摘要不符")
        members = manifest["files"]
        names = {m["path"] for m in members}
        require(names | {"manifest.json"} == set(bundle.namelist()) and
                len(names) == len(members) == len(bundle.namelist()) - 1, "证据包目录")
        for member in members:
            data = bundle.read(member["path"])
            require(len(data) == member["bytes"] and digest(data) == member["sha256"], member["path"])
        journal_raw = bundle.read("journal.json")
        journal = json.loads(journal_raw)
        require(journal["id"] == cid and journal["title"] == case_title(mode) and not journal["decisions"]
                and not journal["referrals"] and any(v["rev"] == rev and v["hash"] == digest(raw)
                for v in journal["revisions"]), "人工日志或原版题名不符")
        report = version["report"]
        graph, calls = report["graph"], report["calls"]
        pages = {n["id"]: n for n in graph["nodes"] if n["type"] == "page"}
        extracts = {(p["doc"], p["page"]): p for p in calls["pages"]}
        docs = graph["documents"]
        require(report["case_id"] == cid and {d["name"] for d in docs} == set(sources) and
                len(extracts) == len(calls["pages"]) == len(docs) == len(sources), "底稿原件或多模态分页清单")
        observed = {}
        for doc in docs:
            unit, name = doc["id"], doc["name"]
            source = sources[name]
            original = bundle.read("originals/" + unit + ".pdf")
            image = bundle.read(f"pages/{unit}/1.jpg")
            text = bundle.read(f"pages/{unit}/1.txt")
            page = pages[unit + "/p1"]
            call = extracts[unit, 1]
            require(doc["ext"] == ".pdf" and doc["pages"] == 1 and original == (folder / name).read_bytes()
                    and digest(original) == doc["sha256"] == source["original_sha256"]
                    and digest(image) == page["sha256"] == call["page_sha256"] == source["page_sha256"]
                    and digest(text) == page["text_sha256"] == source["text_sha256"], name + " 原件、页图或文字层摘要")
            lines = source["lines"]
            require(text.decode().splitlines() == [r["text"] for r in lines] and
                    lines[0]["text"] == WATERMARK and lines[1]["text"] == Path(name).stem, name + " 原行、水印或题名")
            observations = []
            for fact in (f for f in graph["facts"] if f["doc"] == unit and f.get("source_line")):
                loc = fact["source_line"]
                line = lines[loc["number"] - 1]
                require(fact["page"] == 1 and fact["source_sha256"] == doc["sha256"]
                        and fact["page_sha256"] == page["sha256"] and loc["text"] == line["text"]
                        and loc["rects"] == line["rects"], name + " 模型引文未能回到原件")
                observations.append({"ref": fact["id"], "line": line["line"], "field": fact["field"],
                                     "status": fact["status"], "value": fact["value"]})
            observed[name] = {"doc": unit, "original_sha256": doc["sha256"], "page_sha256": page["sha256"],
                              "read": model_record(call, calls["instructions"], image),
                              "check": model_record(call["check"], calls["instructions"], image),
                              "observations": observations}
        expert = model_record(calls["expert"], calls["instructions"])
    stages = [f for f in report["findings"] if f["rule"] == "H04"]
    bank, = [f for f in report["findings"] if f["rule"] == "H05"]
    require([f["stage"]["share"] for f in stages] == ["30", "60", "10"] and
            (bank.get("stage") or {}).get("name") == "第一期", "三期约定或首款回单归属待核")
    flags = {name: len(journal[name]) for name in ("amendments", "attestations", "referrals", "decisions")}
    summary = {"case_id": cid, "rev": rev, "report_sha256": digest(raw), "version": report["policy"]["version"],
               "bundle_sha256": digest(archive), "journal": flags, "documents": observed, "expert": expert,
               "findings": [{"id": f["id"], "stage": (f.get("stage") or {}).get("name"),
                             "status": f["status"], "detail": f["detail"]} for f in [*stages, bank]]}
    return summary, raw, journal_raw


def freeze(folder, sources, cid, mode, revision):
    api = f"/api/cases/{cid}/reports/{revision}"
    version = get(api)
    target = folder / f"R{revision}"
    target.mkdir(exist_ok=True)
    bundle_file = target / "bundle.zip"
    if bundle_file.exists():
        archive = bundle_file.read_bytes()
    else:
        with urlopen(BASE + api + "/bundle", timeout=60) as response:
            archive = response.read()
    summary, raw, journal = inspect_version(folder, sources, cid, mode, revision, version, archive)
    for path, content in [(bundle_file, archive), (target / "report.json", raw), (target / "journal.json", journal)]:
        if path.exists():
            require(path.read_bytes() == content, str(path) + " 归档内容已变化")
        else:
            with tempfile.NamedTemporaryFile(dir=target, delete=False) as staged:
                staged.write(content)
            Path(staged.name).replace(path)
    save_json(target / "verification.json", summary)
    return summary, version["report"]


def await_version(cid, mode, sources, rev, folder):
    previous = None
    until = time.monotonic() + 1800
    while time.monotonic() < until:
        case = scoped_case(cid, mode, sources)
        status = {k: case[k] for k in ("status", "stage", "rev", "error", "page_progress")}
        if status != previous:
            with (folder / f"R{rev}-checkpoints.jsonl").open("a", encoding="utf-8") as out:
                out.write(json.dumps(status, ensure_ascii=False) + "\n")
            previous = status
        if case["rev"] >= rev:
            return case
        if case["status"] == "failed":
            raise RuntimeError(f"{mode} 真实服务失败 · {case['error']}")
        time.sleep(3)
    raise TimeoutError(f"{mode} 等待 R{rev} 超时")


def first_versions(seed, *, baseline_only):
    root = run_folder(seed)
    assigned = json.loads((root / "cases.json").read_bytes())
    results, errors = {}, []
    for mode in CASES:
        try:
            folder, sources = generate(seed, mode)
            cid = assigned[mode]
            await_version(cid, mode, sources, 1, folder)
            summary, report = freeze(folder, sources, cid, mode, 1)
            if report["policy"]["version"] != BASELINE:
                require(not baseline_only, "R1 不是 .04 基线")
                check_guarantee(report, mode, sources)
            results[mode] = {k: summary[k] for k in ("case_id", "rev", "report_sha256", "version", "bundle_sha256")}
            print(mode, cid, "R1", summary["report_sha256"], flush=True)
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            errors.append(f"{mode} · {error}")
    if errors:
        raise RuntimeError("\n".join(errors))
    filename = "baseline.json" if all(r["version"] == BASELINE for r in results.values()) else "issued.json"
    save_json(root / filename, results)


def guarantee_checks(report):
    return [f for f in report["findings"] if f.get("advance_guarantee")]


def check_guarantee(report, mode, sources):
    ledger = report["graph"]["advance_guarantee_sources"]
    require(ledger["format"] == FORMAT and FORMAT in report["policy"].values(), "专项账本版本不符")
    expected = {"only": ("missing", "missing"), "late": ("recorded", "before_receipt"),
                "early": ("recorded", "after_receipt"), "wrong_beneficiary": ("mismatch", "mismatch")}
    checks = guarantee_checks(report)
    require([(f["rule"], f["stage"]["name"]) for f in checks] == [("H04", "第一期"), ("H05", "第一期")],
            "专项判断的期次或银行回单归属不符")
    require(tuple(f["advance_guarantee"]["state"] for f in checks) == expected[mode], mode + " 专项结论与原件不符")
    names = {d["id"]: d["name"] for d in report["graph"]["documents"]}
    facts = {f["id"]: f for f in report["graph"]["facts"]}
    titles = {"clause": CONTRACT, "contract": CONTRACT, "guarantee": GUARANTEE, "receipt": RECEIPT, "payment": BANK}
    rows = {r["id"]: r for r in ledger["rows"]}
    for f in checks:
        proof = f["advance_guarantee"]
        status = "risk" if proof["state"] in ("mismatch", "before_receipt") else "missing"
        require(proof["status"] == status and f["status"] in (("risk", "issue") if status == "risk" else ("missing", "risk", "issue"))
                and set(proof["evidence"]) <= set(f["evidence"]), f["id"] + " 专项结论或证据未传递")
        for row in proof["sources"]:
            source = sources[names[row["doc"]]]
            require(names[row["doc"]] == titles[row["role"]] + ".pdf" and row == rows[row["id"]]
                    and row["id"] in proof["evidence"] and row["page"] == 1
                    and row["original_sha256"] == source["original_sha256"] and row["page_sha256"] == source["page_sha256"],
                    row["id"] + " 来源摘要")
            if row["line"] is None:
                # A model can mistake the title for a contract number. Preserve its held observation.
                require(row["field"] == "title" and row["rects"] == [] and row["quote"] == source["lines"][1]["text"]
                        and any(facts[ref].get("visual_check") in ("conflict", "unreadable") for ref in row["facts"]),
                        row["id"] + " 待核题名或伪定位")
                continue
            require(1 <= row["line"] <= len(source["lines"]), row["id"] + " 原行号")
            original = source["lines"][row["line"] - 1]
            require(row["quote"] == original["text"] and row["rects"] == original["rects"], row["id"] + " 原行与矩形")
        require(proof["issued_on"] == "2026-09-02", "保函开立日期")
        if mode in ("early", "late"):
            require(proof["received_on"] == ("2026-09-08" if mode == "late" else "2026-09-03"), "保函签收日期")
            if f["rule"] == "H05":
                require(proof["paid_on"] == "2026-09-05", "成功扣款日期")


def rerun_event(case, base_rev):
    message = f"基于 R{base_rev} 的已保存提取记录重新建图并审计。"
    return sum(e["message"] == message for e in case["events"])


def request_rerun(folder, sources, mode, base):
    cid, rev = base["case_id"], base["rev"]
    case = scoped_case(cid, mode, sources)
    require(any(v["rev"] == rev and v["hash"] == base["report_sha256"] for v in case["revisions"]), "原基线已变化")
    events = rerun_event(case, rev)
    if events:
        require(events == 1 and case["rev"] in (rev, rev + 1), "重审日志与原基线不符")
        return
    require(case["status"] == "ready" and case["rev"] == rev, "只可对已冻结且待验收的演练底稿发起重审")
    counts = case["page_progress"]["counts"]
    require(all(counts[k] == len(sources) for k in ("prepared", "read", "checked")), "既有逐页模型检查点未齐")
    save_json(folder / "rerun-request.json", {"case_id": cid, "base_rev": rev, "report_sha256": base["report_sha256"],
                                              "page_progress": case["page_progress"]})
    result = post(f"/api/cases/{cid}/rerun", {"rev": rev})
    require(result["id"] == cid, "重审返回的案件编号不符")


def compare_calls(old, new):
    require(old["documents"].keys() == new["documents"].keys(), "文件清单变化")
    pages = []
    for name, source in old["documents"].items():
        current = new["documents"][name]
        require(all(source[k] == current[k] for k in ("doc", "original_sha256", "page_sha256")), name + " 原件或页图变化")
        entry = {"doc": current["doc"], "page": 1, "name": name}
        for step in ("read", "check"):
            entry[step] = {"reused": source[step] == current[step], "before": source[step]["response_id"],
                           "after": current[step]["response_id"]}
        pages.append(entry)
    expert = {"before": old["expert"], "after": new["expert"],
              "fresh": all(old["expert"][k] != new["expert"][k] for k in ("request_id", "response_id"))}
    return {"pages": pages, "expert": expert}


def rerun(seed):
    require(get("/api/controls").get("advance_guarantee") == FORMAT, "运行中服务尚未提供预付款保函专项规则")
    root = run_folder(seed)
    bases = json.loads((root / "baseline.json").read_bytes())
    submitted = json.loads((root / "cases.json").read_bytes())
    require(set(bases) == set(CASES) and {mode: b["case_id"] for mode, b in bases.items()} == submitted
            and len(set(submitted.values())) == len(CASES), "四个基线须匹配原提交回执")
    pending, results, errors = [], {}, []
    for mode in CASES:
        try:
            base = bases[mode]
            folder, sources = generate(seed, mode)
            request_rerun(folder, sources, mode, base)
            pending.append((mode, base, folder, sources))
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            errors.append(f"{mode} · {error}")
    for mode, base, folder, sources in pending:
        try:
            cid, old_rev = base["case_id"], base["rev"]
            rev = old_rev + 1
            case = await_version(cid, mode, sources, rev, folder)
            require(case["rev"] == rev and case["status"] == "ready" and rerun_event(case, old_rev) == 1,
                    "重审次数或待人工验收状态不符")
            summary, report = freeze(folder, sources, cid, mode, rev)
            checks = guarantee_checks(report)
            previous = json.loads((folder / f"R{old_rev}" / "verification.json").read_bytes())
            comparison = compare_calls(previous, summary)
            results[mode] = {**{k: summary[k] for k in ("case_id", "rev", "report_sha256", "version", "journal")},
                             "reruns": rerun_event(case, old_rev), "checkpoints": case["page_progress"]["counts"],
                             "calls": comparison, "findings": summary["findings"],
                             "checks": [{"id": f["id"], "stage": f["stage"]["name"], "status": f["status"],
                                         "proof": f["advance_guarantee"]["state"], "proof_status": f["advance_guarantee"]["status"]}
                                        for f in checks]}
            require(all(p[s]["reused"] for p in comparison["pages"] for s in ("read", "check")),
                    "本次重审有分页提取或复检检查点变化")
            require(previous["journal"] == summary["journal"] and comparison["expert"]["fresh"],
                    "人工操作日志或本轮专家调用不符")
            check_guarantee(report, mode, sources)
            print(mode, cid, f"R{rev}", results[mode]["checks"], flush=True)
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            errors.append(f"{mode} · {error}")
    save_json(root / "rechecked.json", {"cases": results, "errors": errors})
    if errors:
        raise RuntimeError("\n".join(errors))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=SEED)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--submit", action="store_true", help="通过正常本地上传入口提交四案")
    action.add_argument("--baseline", action="store_true", help="只读核对并冻结四案 .04 的初次出具版")
    action.add_argument("--run", action="store_true", help="上传并核验初次出具版，可用同一 seed 接续")
    action.add_argument("--rerun", action="store_true", help="按四案已冻结的 .04 基线各重审一次，并核对主体、编号与日期")
    args = parser.parse_args()
    if args.submit or args.run:
        create_cases(args.run_id)
    if args.baseline or args.run:
        first_versions(args.run_id, baseline_only=args.baseline)
    if args.rerun:
        rerun(args.run_id)
    if not (args.submit or args.run or args.baseline or args.rerun):
        for case_mode in CASES:
            print(case_mode, generate(args.run_id, case_mode)[0])
