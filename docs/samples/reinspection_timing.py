"""Watermarked examples of an express contractual wait between repair completion and the start of reinspection."""

import argparse
import hashlib

from contract_milestones import PROFILE
from generate import ROOT, embedded_font, pdf
from quality_reinspection import reinspection_records
from reinspection_register import review_printed
from run import BASE, get, submit


CASES = {
    "report_early": "复验单次日签认但合同要求等待48小时",
    "elapsed": "复验明确开始于整改完成49小时15分后",
    "early": "实际开始复验比合同约定早一小时",
    "boundary": "只有整改和复验开始日期，48小时临界待核",
    "signed_only": "复验报告四天后签认但未列起始时点",
    "operation": "复验间隔足够但缺连续试运行依据",
}
TERM = "整改完成后至少间隔48小时方可开始复验"
OPERATION = "整改完成后须连续试运行48小时无异常方可开始复验"


def materials(seed, mode):
    code = hashlib.sha256((seed + "-" + mode).encode()).hexdigest()[:8].upper()
    records = reinspection_records(code, "closed")
    records["采购合同"].append(("整改复验条件", OPERATION if mode == "operation" else TERM))
    final = records["复验报告"]
    if mode == "report_early":
        records["复验报告"] = [(k, "2026年9月17日" if k == "复验日期" else v) for k, v in final]
    if mode in ("elapsed", "early", "operation"):
        records["整改记录单"].append(
            ("整改完成时刻", "2026-09-16 15:00" if mode == "early" else "2026-09-16 09:00")
        )
        final.append(("复验开始时刻", "2026-09-18 14:00" if mode == "early" else "2026-09-18 10:15"))
    elif mode == "boundary":
        final.append(("复验开始日期", "2026年9月18日"))
    folder = ROOT / "合同复验间隔" / code
    folder.mkdir(parents=True, exist_ok=True)
    font = embedded_font("ReinspectionTimingCJK")
    for title, rows in records.items():
        pdf(folder / (title + ".pdf"), title, rows, font=font, spacing=25)
    return folder, records


def verify_sample(report, mode):
    (f,) = [f for f in report["findings"] if f["rule"] == "H02"]
    t = f["reinspection"]["timing"]
    state, status, lower, upper = {
        "report_early": ("report_early", "risk", None, 172800),
        "elapsed": ("met", "ok", 177240, 177360),
        "early": ("early", "risk", 169140, 169260),
        "boundary": ("boundary", "missing", 86400, 259200),
        "signed_only": ("start_missing", "missing", None, 432000),
        "operation": ("operation_pending", "missing", 177240, 177360),
    }[mode]
    assert (t["state"], f["status"], t["above_seconds"], t["below_seconds"]) == (
        state,
        status,
        lower,
        upper,
    ), (mode, t)
    assert t["required_hours"] == 48 and set(t["sources"]) <= set(f["evidence"])
    assert (f["reinspection"]["state"] == "closed") == (mode == "elapsed")
    ledger = report["graph"]["reinspection_wait_sources"]
    edges = [e for e in report["graph"]["edges"] if e["type"] == "reinspection_time_basis"]
    for src in t["sources"]:
        (row,) = [r for r in ledger["lines"] if r["id"] == src]
        assert row["line"] and any(
            e["from"] == f"{row['doc']}/p{row['page']}" and e["to"] == src for e in edges
        )
    stages = [f for f in report["findings"] if f["rule"] == "H04"]
    assert [p["status"] for p in stages] == ["ok", status, status]
    assert t["term_ref"] not in stages[0]["evidence"]
    assert all(t["term_ref"] in p["evidence"] for p in stages[1:])
    (paid,) = [f for f in report["findings"] if f["rule"] == "H05"]
    assert paid["status"] == ("ok" if mode == "elapsed" else "missing")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-id", default="synthetic-reinspection-timing-v1")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    args = parser.parse_args()
    queue = []
    for mode in args.cases:
        folder, records = materials(args.run_id, mode)
        if not args.run:
            print(folder)
            continue
        cid = submit(
            "合成演练 · " + CASES[mode], sorted(folder.glob("*.pdf")), args.run_id + "-" + mode, PROFILE
        )
        queue.append((cid, mode, folder, records))
        print(mode, cid, flush=True)
    for cid, mode, folder, records in queue:
        report = review_printed(
            cid,
            folder,
            records,
            CASES[mode],
            {key: "other" for key in ("整改复验条件", "整改完成时刻", "复验开始日期", "复验开始时刻")},
        )
        verify_sample(report, mode)
        h02 = next(f for f in report["findings"] if f["rule"] == "H02")
        print(
            mode,
            BASE + "/workpaper/" + cid + "?rev=" + str(get("/api/cases/" + cid)["rev"]),
            report["policy"]["version"],
            h02["status"],
            h02["reinspection"]["state"],
            flush=True,
        )
