"""Exercise conflicting final inspection pages using watermarked, generated procurement records."""

import argparse
import hashlib
import sys
from pathlib import Path

from contract_milestones import PROFILE, confirm_printed_records, normalize
from generate import ROOT, WATERMARK, embedded_font, pdf
from quality_reinspection import reconcile_training_pages, reinspection_records
from run import BASE, get, submit, wait
from warranty_release import check_training_watermark

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from documents import prepare


CASES = {
    "open": "复验合格与门封待整改并列",
    "conditional": "复验签字栏保留连续试运行条件",
    "reported": "复验另列关闭事项但缺少该项整改记录",
    "clear": "探头整改已复验且未结项目栏明确为无",
}
ROWS = {
    "open": [("未结整改项目", "无"), ("未结整改项目", "QX-02 门封漏气，待更换门封条")],
    "conditional": [("签认附言", "待连续试运行72小时后签发最终报告")],
    "reported": [("整改明细", "QX-02 门封漏气，已关闭")],
    "clear": [("未结整改项目", "无")],
}


def materials(seed, mode):
    code = hashlib.sha256((seed + "-" + mode).encode()).hexdigest()[:8].upper()
    records = reinspection_records(code, "closed")
    records["复验报告"].extend(ROWS[mode])
    folder = ROOT / "复验逐项核对" / code
    folder.mkdir(parents=True, exist_ok=True)
    font = embedded_font("ReinspectionItemsCJK")
    for title, rows in records.items():
        pdf(folder / (title + ".pdf"), title, rows, font=font, spacing=25)
    return folder, records


def review_printed(cid, folder, records, case_title, extra_fields):
    case = get("/api/cases/" + cid)
    assert case["title"] == "合成演练 · " + case_title and not case["decisions"]
    report = wait(cid)
    nodes = {n["id"]: n for n in report["graph"]["nodes"] if n["type"] == "page"}
    for doc in case["documents"]:
        source = folder / doc["name"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == doc["sha256"]
        page, = prepare(source, 1, save_images=False)
        assert nodes[doc["id"] + "/p1"]["sha256"] == page["sha256"] and normalize(WATERMARK) in normalize(page["text"])
    # Preserve the distinct additional rows as printed observations. The procedure reads the whole page independently.
    reconcile_training_pages(cid, folder, records, case_titles=[case_title], row_spacing=25, field_labels=extra_fields)
    return check_training_watermark(cid, folder, records, confirm_printed_records(cid, folder, records))


def review(cid, mode, folder, records):
    return review_printed(cid, folder, records, CASES[mode], {label: "other" for label, _ in ROWS[mode]})


def verify_sample(report, mode):
    h02, = [f for f in report["findings"] if f["rule"] == "H02"]
    chain = h02["reinspection"]
    expected = {"open": ("risk", ["clear", "open"]), "conditional": ("risk", ["conditional"]),
                "reported": ("missing", ["reported_closed"]), "clear": ("ok", ["clear"])}
    status, kinds = expected[mode]
    lines = chain["register"]["lines"]
    assert [s["kind"] for s in lines] == kinds and h02["status"] == status, (mode, h02["detail"], lines)
    assert [s["quote"] for s in lines] == [k + "：" + v for k, v in ROWS[mode]]
    assert (chain["state"] == "closed") == (mode == "clear")
    assert all(s["page"] == 1 and s["line"] and any(e["type"] == "reinspection_register_line" and
               e["to"] == f"{s['doc']}/p1" and e["line"] == s["line"] and e["quote"] == s["quote"]
               for e in report["graph"]["edges"]) for s in lines)
    stages = [f["status"] for f in report["findings"] if f["rule"] == "H04"]
    assert stages == ["ok", status, status], (mode, stages)
    payment, = [f for f in report["findings"] if f["rule"] == "H05"]
    assert payment["status"] == ("ok" if mode == "clear" else "missing")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-id", default="synthetic-final-register-v1")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    args = parser.parse_args()
    queue = []
    for mode in args.cases:
        folder, records = materials(args.run_id, mode)
        if not args.run:
            print(folder)
            continue
        cid = submit("合成演练 · " + CASES[mode], sorted(folder.glob("*.pdf")), args.run_id + "-" + mode, PROFILE)
        print(mode, cid, flush=True)
        queue.append((cid, mode, folder, records))
    for cid, mode, folder, records in queue:
        report = review(cid, mode, folder, records)
        verify_sample(report, mode)
        h02 = next(f for f in report["findings"] if f["rule"] == "H02")
        print(mode, BASE + "/workpaper/" + cid + "?rev=" + str(get("/api/cases/" + cid)["rev"]),
              report["policy"]["version"], h02["status"], h02["reinspection"]["state"], flush=True)
