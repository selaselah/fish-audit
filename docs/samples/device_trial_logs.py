"""Exercise single-device trial logs printed and signed on a final reinspection form."""

import argparse
import hashlib

from contract_milestones import PROFILE, normalize
from generate import ROOT, WATERMARK, embedded_font, pdf
from quality_reinspection import reinspection_records
from reinspection_register import prepare, review_printed
from reinspection_timing import OPERATION
from run import BASE, get, post, submit, wait

CASES = {
    "covered": "单台冷藏柜连续试运行48小时30分",
    "gap": "两班试运行记录之间有30分钟空档",
    "fault": "复验合格但运行记录载有30分钟故障停机",
    "other_device": "运行时长充足但记录属于另一台冷藏柜",
}
EXTRA = {
    **{
        k: "other"
        for k in (
            "整改复验条件",
            "整改完成时刻",
            "复验开始时刻",
            "试运行设备",
            "日志口径",
            "日志签认范围",
            "运行记录",
        )
    },
    "约定交付数量": "quantity_agreed",
}


def materials(seed, mode):
    code = hashlib.sha256((seed + "-" + mode).encode()).hexdigest()[:8].upper()
    serial = "SN-FR-7" + code
    subject = "四门冷藏柜（序列号 " + serial + "）"
    replacements = {"约定交付数量": "1台", "实际验收数量": "1台", "采购标的": subject}
    records = {
        k: [(label, replacements.get(label, value)) for label, value in rows]
        for k, rows in reinspection_records(code, "closed").items()
    }
    records["采购合同"].append(("整改复验条件", OPERATION))
    records["整改记录单"].append(("整改完成时刻", "2026-09-16 09:00"))
    logs = [
        ("复验开始时刻", "2026-09-18 10:15"),
        ("试运行设备", "SN-FR-800001" if mode == "other_device" else serial),
        ("日志口径", "北京时间，区间含起不含止，边界为整分"),
        ("日志签认范围", "本页复验签认涵盖全部试运行记录"),
        ("运行记录", "2026-09-16 09:15 至 2026-09-17 09:15 | 连续无异常"),
    ]
    if mode == "fault":
        logs.append(("运行记录", "2026-09-17 09:15 至 2026-09-17 09:45 | 故障停机"))
    shift = "09:45" if mode in ("gap", "fault") else "09:15"
    logs.append(("运行记录", f"2026-09-17 {shift} 至 2026-09-18 09:45 | 连续无异常"))
    records["复验报告"].extend(logs)
    folder = ROOT / "设备试运行日志" / code
    folder.mkdir(parents=True, exist_ok=True)
    font = embedded_font("TrialRunCJK")
    for title, rows in records.items():
        pdf(folder / (title + ".pdf"), title, rows, font=font, spacing=25)
    return folder, records


def verify_sample(report, mode):
    (finding,) = [f for f in report["findings"] if f["rule"] == "H02"]
    timing = finding["reinspection"]["timing"]
    run = timing["operation"]
    state, status = {
        "covered": ("run_met", "ok"),
        "gap": ("run_gap", "missing"),
        "fault": ("run_fault", "risk"),
        "other_device": ("run_device", "missing"),
    }[mode]
    assert (timing["state"], finding["status"]) == (state, status), (mode, finding["detail"], timing)
    stages = [f for f in report["findings"] if f["rule"] == "H04"]
    assert [f["status"] for f in stages] == ["ok", status, status]
    assert set(run["sources"]).issubset(finding["evidence"])
    assert all(set(run["sources"]).issubset(f["evidence"]) for f in stages[1:])
    assert timing["term_ref"] not in stages[0]["evidence"]
    assert all(i["ref"] not in stages[0]["evidence"] for i in run["intervals"])
    (paid,) = [f for f in report["findings"] if f["rule"] == "H05"]
    assert paid["status"] == ("ok" if mode == "covered" else "missing")
    if mode != "other_device":
        assert run["longest_seconds"] == (174600 if mode == "covered" else 86400)
    if mode == "gap":
        assert [g["seconds"] for g in run["gaps"]] == [1800]
    if mode == "fault":
        assert [s["seconds"] for s in run["intervals"] if s["state"] == "fault"] == [1800]


def review(cid, folder, records, mode):
    report = review_printed(cid, folder, records, CASES[mode], EXTRA, exact_fields=("subject",))
    path = "/api/cases/" + cid
    original = folder / "复验报告.pdf"
    (doc,) = [d for d in report["graph"]["documents"] if d["name"] == original.name]
    assert hashlib.sha256(original.read_bytes()).hexdigest() == doc["sha256"]
    (page,) = prepare(original, 1, save_images=False)
    physical = page["text"].splitlines()
    assert normalize(physical[0]) == normalize(WATERMARK)
    assert (
        next(n["sha256"] for n in report["graph"]["nodes"] if n["id"] == doc["id"] + "/p1") == page["sha256"]
    )
    # Locate the row by a unique printed value or both endpoints of the same signed interval.
    for index, (label, value) in enumerate(records["复验报告"]):
        if EXTRA.get(label) != "other":
            continue
        raw = label + "：" + value
        assert raw in physical
        if sum(normalize(row.partition("：")[2]) == normalize(value) for row in physical) != 1:
            continue
        for f in report["graph"]["facts"]:
            if (
                f["doc"] != doc["id"]
                or f["page"] != 1
                or f.get("amendment")
                or f.get("source_line")
                or f["status"] not in ("visual", "unsupported")
                or f["field"] != "other"
            ):
                continue
            body = f["quote"].replace("：", ":", 1).partition(":")[2]
            interval = normalize(raw).partition("|")[0] + "|"
            same_interval = (
                label == "运行记录"
                and normalize(f["quote"]).startswith(interval)
                and sum(normalize(row).startswith(interval) for row in physical) == 1
            )
            if f["quote"] in physical or not (normalize(body) == normalize(value) or same_interval):
                continue
            top = (842 - 649 + 25 * index) / 842
            post(
                path + "/amend",
                {
                    "rev": get(path)["rev"],
                    "doc": doc["id"],
                    "page": 1,
                    "target": f["id"],
                    "field": "other",
                    "value": value,
                    "quote": raw,
                    "region": "bottom" if top >= 2 / 3 else "middle" if top >= 1 / 3 else "top",
                    "reviewer": "水印演练校验",
                    "note": "逐字对照本次水印原页，按唯一对应的单元格或同一起止区间补正日志转录。",
                },
            )
            report = wait(cid)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-id", default="synthetic-device-logs-v1")
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
        print(mode, cid, flush=True)
        queue.append((cid, mode, folder, records))
    for cid, mode, folder, records in queue:
        report = review(cid, folder, records, mode)
        verify_sample(report, mode)
        print(
            mode,
            BASE + "/workpaper/" + cid + "?rev=" + str(get("/api/cases/" + cid)["rev"]),
            report["policy"]["version"],
            flush=True,
        )
