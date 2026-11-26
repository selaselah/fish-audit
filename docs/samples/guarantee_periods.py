"""Watermarked first-payment guarantee cases with four different expiry clauses."""

import argparse
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile

import advance_guarantees as advance
from advance_guarantees import BANK, CONTRACT, GUARANTEE, PROFILE, RECEIPT, digest, require, save_json
from documents import prepare
from generate import WATERMARK, embedded_font
from protocol import canonical
from rule_replay import replay_from_git
from run import BASE, get, post, submit, wait
from verify import verify

SCRATCH = Path("/tmp/fish-guarantee-period-27")
SEED = "synthetic-guarantee-periods-20261127-v1"
BASELINE = "2026.11.27.05"
FORMAT = "advance-payment-guarantee-v2"
CASES = {
    "expired": "首期付款日晚于保函所写的含当日到期日",
    "inclusive-end": "首期付款日为保函明确含当日的到期日",
    "end-unspecified": "首期付款与保函到期同日，末日是否计入未写明",
    "extension-request": "首期付款日晚于原保函期限，仅附待确认的展期申请",
}
REQUIREMENT = "第一期预付款的付款日须在本合同项下预付款保函的有效期内"
EXTENSION = "延期申请已提交，尚待开立机构确认"


def run_folder(seed):
    return SCRATCH / ("run-" + digest(seed.encode())[:12])


def title(mode):
    return "合成演练 · " + CASES[mode]


def materials(seed, mode):
    forms = advance.materials("guarantee-period/" + seed + "/" + mode, "early")
    forms[CONTRACT].append(("保函有效期要求", REQUIREMENT))
    end = "2026年9月4日" if mode in ("expired", "extension-request") else "2026年9月5日"
    label = "保函有效期至" if mode == "end-unspecified" else "保函有效期至（含当日）"
    forms[GUARANTEE].extend([("保函有效期自", "2026年9月2日"), (label, end)])
    if mode == "extension-request":
        forms[GUARANTEE].append(("展期说明", EXTENSION))
    return forms


def generate(seed, mode, *, folder=None):
    folder = run_folder(seed) / mode if folder is None else folder
    folder.mkdir(parents=True, exist_ok=True)
    sources = {}
    font = embedded_font("GuaranteePeriodSampleCJK")
    for heading, rows in materials(seed, mode).items():
        name = heading + ".pdf"
        with tempfile.TemporaryDirectory(dir=folder) as temp:
            pdf = Path(temp) / name
            advance.write_form(pdf, heading, rows, font)
            page, = prepare(pdf, 1, save_images=False)
            text = page["text"].splitlines()
            geometry = page["layer"]["lines"]
            require(text == [WATERMARK, heading, *(k + "：" + v for k, v in rows)], name + " 水印、题名或原行不全")
            lines = []
            for number, quote in enumerate(text, 1):
                rects = geometry[str(number)]
                require(rects and all(0 < x < right < 1 and 0 < y < bottom < 1 for x, y, right, bottom in rects),
                        f"{name} 第 {number} 行未能在实页定位")
                lines.append({"line": number, "text": quote, "rects": rects})
            content = pdf.read_bytes()
            original = folder / name
            if original.exists():
                require(original.read_bytes() == content, name + " 与此种子的冻结原件不同")
            else:
                pdf.replace(original)
        sources[name] = {"original_sha256": digest(content), "page_sha256": page["sha256"],
                         "text_sha256": digest(page["text"].encode()), "lines": lines}
    save_json(folder / "sources.json", sources)
    return folder, sources


def scoped_case(cid, mode, sources):
    case = get("/api/cases/" + cid)
    require(case["id"] == cid and case["title"] == title(mode) and case["profile"] == PROFILE
            and not (case["decisions"] or case["referrals"]) and
            {d["name"]: d["sha256"] for d in case["documents"]} == {n: s["original_sha256"] for n, s in sources.items()},
            mode + " 案号、题名、人工记录或原件清单不符")
    return case


def upload(seed):
    audit = get("/api/health")["audit"]
    require(audit["provider"] == "openai" and audit["configured"] and get("/api/ready")["status"] == "ready",
            "本地模型服务或 worker 未就绪")
    root = run_folder(seed)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "cases.json"
    cases = json.loads(path.read_bytes()) if path.exists() else {}
    for mode in CASES:
        folder, sources = generate(seed, mode)
        if mode not in cases:
            key = digest((seed + mode + "".join(s["original_sha256"] for s in sources.values())).encode())
            cases[mode] = submit(title(mode), [folder / name for name in sources], "guarantee-period-" + key, PROFILE)
            save_json(path, cases)
        scoped_case(cases[mode], mode, sources)
        print(mode, cases[mode], flush=True)
    return cases


def fixed_file(path, content):
    if path.exists():
        require(path.read_bytes() == content, str(path) + " 与已冻结字节不同")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as staged:
        staged.write(content)
    Path(staged.name).replace(path)


def physical_documents(bundle, report, folder, sources):
    calls = report["calls"]
    documents = {d["id"]: d for d in report["graph"]["documents"]}
    observed = {}
    for call in calls["pages"]:
        unit = call["doc"]
        doc = documents[unit]
        name = doc["name"]
        source = sources[name]
        image = bundle.read(f"pages/{unit}/1.jpg")
        text = bundle.read(f"pages/{unit}/1.txt")
        original = bundle.read(f"originals/{unit}.pdf")
        require(call["page"] == doc["pages"] == 1 and original == (folder / name).read_bytes()
                and digest(original) == source["original_sha256"] == doc["sha256"]
                and digest(image) == source["page_sha256"] == call["page_sha256"]
                and digest(text) == source["text_sha256"]
                and text.decode().splitlines() == [r["text"] for r in source["lines"]], name + " 原件、归档页或文字不符")
        observed[name] = {"doc": unit, "original_sha256": doc["sha256"], "page_sha256": call["page_sha256"],
                          "read": advance.model_record(call, calls["instructions"], image),
                          "check": advance.model_record(call["check"], calls["instructions"], image)}
    require(len(calls["pages"]) == len(documents) == len(observed) == 4 and set(observed) == set(sources), "四份单页原件不齐")
    return observed


def freeze(seed, mode, cid, rev):
    folder, sources = generate(seed, mode)
    case = scoped_case(cid, mode, sources)
    if case["rev"] < rev:
        wait(cid)
        case = scoped_case(cid, mode, sources)
    require(case["rev"] >= rev, "尚未出具指定版")
    path = f"/api/cases/{cid}/reports/{rev}"
    version = get(path)
    target = folder / f"R{rev}"
    target.mkdir(exist_ok=True)
    archive_path = target / "bundle.zip"
    if archive_path.exists():
        archive = archive_path.read_bytes()
    else:
        with urlopen(BASE + path + "/bundle", timeout=60) as response:
            archive = response.read()
    with ZipFile(BytesIO(archive)) as bundle:
        raw = bundle.read("report.json")
        journal_raw = bundle.read("journal.json")
        report, journal = json.loads(raw), json.loads(journal_raw)
        require(version["rev"] == rev and digest(raw) == version["sha256"] and canonical(version["report"]).encode() == raw
                and cid == report["case_id"] == journal["id"] and journal["title"] == title(mode)
                and any(v["rev"] == rev and v["hash"] == digest(raw) for v in journal["revisions"]), "固定版题名或整版摘要")
        flags = {k: len(journal[k]) for k in ("decisions", "referrals", "amendments", "attestations")}
        require(not any(flags.values()), "出现额外人工操作")
        docs = physical_documents(bundle, report, folder, sources)
    verified_id, verified_rev, entries = verify(BytesIO(archive))
    require((verified_id, verified_rev) == (cid, rev), "证据包与固定版不符")
    fixed_file(archive_path, archive)
    fixed_file(target / "report.json", raw)
    fixed_file(target / "journal.json", journal_raw)
    summary = {"case_id": cid, "rev": rev, "report_sha256": digest(raw), "bundle_sha256": digest(archive),
               "rule_version": report["policy"]["version"], "entries": entries, "documents": docs, "journal": flags,
               "expert": advance.model_record(report["calls"]["expert"], report["calls"]["instructions"]),
               "checkpoints": case["page_progress"]["counts"], "verdict": report["result"]["verdict"],
               "findings": [{"id": f["id"], "stage": (f.get("stage") or {}).get("name"), "status": f["status"],
                             "advance_guarantee": f.get("advance_guarantee", {}).get("state")}
                            for f in report["findings"] if f["rule"] in ("H04", "H05")]}
    save_json(target / "verification.json", summary)
    return summary, report


def period_findings(report, mode, sources):
    expected = {"expired": "expired", "inclusive-end": "covered", "end-unspecified": "end_unspecified",
                "extension-request": "extension_review"}
    finding_list = report["findings"]
    require(report["policy"].get("advance_guarantee") == report["graph"]["advance_guarantee_sources"]["format"] == FORMAT,
            "有效期规则与已出具的来源账本不符")
    findings = advance.guarantee_checks(report)
    require([(f["rule"], f["stage"]["name"]) for f in findings] == [("H04", "第一期"), ("H05", "第一期")]
            and [f["stage"]["name"] for f in finding_list if f["rule"] == "H04"] == ["第一期", "第二期", "第三期"]
            and all(not any(ref.startswith("advance-guarantee/") for ref in f["evidence"])
                    for f in finding_list if not f.get("advance_guarantee")), "专项的付款期次不符")
    names = {d["id"]: d["name"] for d in report["graph"]["documents"]}
    ledger = {r["id"]: r for r in report["graph"]["advance_guarantee_sources"]["rows"]}
    result = []
    for f in findings:
        proof = f["advance_guarantee"]
        period = proof["period"]
        bank = f["rule"] == "H05"
        state = expected[mode] if bank or mode == "extension-request" else "stated"
        require(proof["state"] == ("after_receipt" if bank else "recorded") and proof["received_on"] == "2026-09-03"
                and period["state"] == state and period["status"] == ("risk" if state == "expired" else "missing")
                and f["status"] in (("risk", "issue") if state == "expired" else ("missing", "risk", "issue"))
                and period["valid_from"] == "2026-09-02" and period["paid_on"] == ("2026-09-05" if bank else None)
                and period["valid_until"] == ("2026-09-04" if mode in ("expired", "extension-request") else "2026-09-05")
                and period["end_inclusive"] is (None if mode == "end-unspecified" else True),
                mode + " 已出具的有效期、首款日期或结论与原件不符")
        require(set(period["evidence"]) <= set(f["evidence"]), f["id"] + " 专项证据未传递")
        for r in period["sources"]:
            source = sources[names[r["doc"]]]
            require(r == ledger[r["id"]] and r["id"] in period["evidence"] and r["page"] == 1
                    and r["original_sha256"] == source["original_sha256"] and r["page_sha256"] == source["page_sha256"],
                    r["id"] + " 原件或页图不符")
            if r["line"] is not None:
                actual = source["lines"][r["line"] - 1]
                require((actual["text"], actual["rects"]) == (r["quote"], r["rects"]), r["id"] + " 原行或矩形不符")
            else:
                require(not r["rects"], r["id"] + " 待核信号含有坐标")
        expected_fields = {"clause", "period_clause", "valid_from", "received_on",
                           "valid_until" if mode == "end-unspecified" else "valid_until_inclusive"}
        if bank:
            expected_fields.add("paid_on")
        if mode == "extension-request":
            expected_fields.add("extension_note")
        require(expected_fields <= {r["field"] for r in period["sources"] if r["line"] and r["rects"]}, "缺少专项原行")
        result.append({"finding": f["id"], "status": f["status"], "state": state, "period_status": period["status"]})
    return result


def initial(seed, *, baseline_only):
    root = run_folder(seed)
    assigned = json.loads((root / "cases.json").read_bytes())
    require(set(assigned) == set(CASES) and len(set(assigned.values())) == 4, "缺少独立提交回执")
    results, errors = {}, []
    for mode, cid in assigned.items():
        try:
            entry, report = freeze(seed, mode, cid, 1)
            if baseline_only:
                require(entry["rule_version"] == BASELINE, "初次出具版不是 .05")
            if entry["rule_version"] != BASELINE:
                sources = json.loads((root / mode / "sources.json").read_bytes())
                entry["period"] = period_findings(report, mode, sources)
            results[mode] = {k: entry[k] for k in ("case_id", "rev", "report_sha256", "bundle_sha256", "findings")}
            if "period" in entry:
                results[mode]["period"] = entry["period"]
            print(mode, cid, "R1", entry["report_sha256"], results[mode]["findings"], flush=True)
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            errors.append(f"{mode} · {error}")
    if errors:
        raise RuntimeError("\n".join(errors))
    save_json(root / ("issued.json" if any("period" in r for r in results.values()) else "baseline.json"), results)


def rerun(seed, trusted_commit):
    controls = get("/api/controls")
    require(controls["version"] == "2026.11.27.06" and controls.get("advance_guarantee") == FORMAT,
            "运行中的服务尚未载入已指定的 .06 有效期规则")
    commit = subprocess.check_output(["git", "-C", str(advance.PROJECT), "rev-parse", "--verify", "--end-of-options",
                                      trusted_commit + "^{commit}"], text=True).strip()
    require(commit == trusted_commit, "请使用已发布的完整提交摘要")
    root = run_folder(seed)
    baseline = json.loads((root / "baseline.json").read_bytes())
    assigned = json.loads((root / "cases.json").read_bytes())
    require(set(assigned) == set(CASES) and {m: r["case_id"] for m, r in baseline.items()} == assigned, "基线与提交回执不符")
    queued, results, errors = [], {}, []
    for mode, cid in assigned.items():
        try:
            folder, sources = generate(seed, mode)
            case = scoped_case(cid, mode, sources)
            previous, = [r for r in case["revisions"] if r["rev"] == 1]
            require(previous["hash"] == baseline[mode]["report_sha256"], "R1 摘要已变化")
            if not advance.rerun_event(case, 1):
                require(case["status"] == "ready" and case["rev"] == 1 and
                        all(case["page_progress"]["counts"][k] == 4 for k in ("prepared", "read", "checked")), "基线或检查点未齐")
                save_json(folder / "rerun-request.json", {"case_id": cid, "base": previous, "checkpoints": case["page_progress"]})
                require(post(f"/api/cases/{cid}/rerun", {"rev": 1})["id"] == cid, "重审回执案号不符")
            queued.append((mode, cid, sources))
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            errors.append(f"{mode} · {error}")
    for mode, cid, sources in queued:
        try:
            new, report = freeze(seed, mode, cid, 2)
            case = scoped_case(cid, mode, sources)
            require(case["status"] == "ready" and case["rev"] == 2 and advance.rerun_event(case, 1) == 1,
                    "线上重审次数或待人工验收状态不符")
            old = json.loads((root / mode / "R1/verification.json").read_bytes())
            calls = advance.compare_calls(old, new)
            result = {k: new[k] for k in ("case_id", "rev", "report_sha256", "rule_version", "journal", "findings")}
            results[mode] = {**result, "calls": calls, "reruns": advance.rerun_event(case, 1)}
            results[mode]["period"] = period_findings(report, mode, sources)
            require(calls["expert"]["fresh"] and all(p[k]["reused"] for p in calls["pages"] for k in ("read", "check")),
                    "新专家调用或逐页读图复用回执不符")
            print(mode, "R2", new["report_sha256"], results[mode]["period"], flush=True)
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            errors.append(f"{mode} · {error}")
    save_json(root / "rechecked.json", {"cases": results, "errors": errors})
    if errors:
        raise RuntimeError("\n".join(errors))
    replay(seed, trusted_commit)


def replay(seed, trusted_commit):
    root = run_folder(seed)
    for mode in CASES:
        for rev in (1, 2):
            folder = root / mode / f"R{rev}"
            archive = folder / "bundle.zip"
            with ZipFile(archive) as z:
                raw = z.read("report.json")
            require(raw == (folder / "report.json").read_bytes(), "重放底稿与固定包不符")
            verify(archive, render_addenda=True)
            result = replay_from_git(json.loads(raw), ref=trusted_commit, repo=advance.PROJECT,
                                     pinned=trusted_commit if rev == 2 else None)
            require(result["state"] == "verified", str(folder) + " 对应提交复算不符")
            save_json(folder / "git-replay.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default=SEED)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--submit", action="store_true")
    action.add_argument("--baseline", action="store_true", help="只读冻结四份 .05 R1")
    action.add_argument("--run", action="store_true", help="从新 seed 上传并核验本服务初次出具版")
    action.add_argument("--rerun", metavar="COMMIT", help="切版后按固定的四个 R1 各重审一次，按发布提交复算")
    action.add_argument("--replay", metavar="COMMIT", help="仅重放已冻结的八份证据包")
    args = parser.parse_args()
    if args.submit or args.run:
        upload(args.seed)
    if args.baseline or args.run:
        initial(args.seed, baseline_only=args.baseline)
    elif args.rerun:
        rerun(args.seed, args.rerun)
    elif args.replay:
        replay(args.seed, args.replay)
    elif not args.submit:
        for case_mode in CASES:
            print(case_mode, generate(args.seed, case_mode)[0])
