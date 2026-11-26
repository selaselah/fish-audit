"""Generate marked two-page purchase contracts with different payment-page evidence."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents, normalize
from generate import ROOT, WATERMARK, draw_pdf_page, embedded_font
from quality_reinspection import reconcile_training_pages
from reinspection_register import prepare
from reportlab.pdfgen import canvas
from run import get, post, submit, wait

CASES = {
    "continued": "付款续页与合同正文编号一致",
    "discussion": "付款续页明确仅供讨论",
    "foreign": "付款续页引用另一份协议",
    "standalone": "首款独立执行，其余两期仍在讨论",
}
FIELDS = {
    "含税总额": "total",
    "签约日期": "signed_on",
    "实际生效日期": "effect_on",
    "生效条款": "effect_clause",
    "约定交付数量": "quantity_agreed",
    "约定验收标准": "acceptance_criteria",
    "付款条款": "payment_term",
    **dict.fromkeys(("第一期", "第二期", "第三期"), "payment_stage"),
    "付款户名": "payer",
    "收款户名": "payee",
    "付款金额": "transfer_amount",
    "付款日期": "paid_on",
    "交易状态": "transfer_status",
    "关联协议编号": "other",
    "续页说明": "other",
    "首款约定": "other",
}


def materials(seed, mode):
    code = hashlib.sha256((seed + "-" + mode).encode()).hexdigest()[:8].upper()
    folder = ROOT / "合同付款续页" / code
    folder.mkdir(parents=True, exist_ok=True)
    records = documents(code, "complete")
    layout = {title: [title] for title in records}
    layout["采购合同"].append("付款条款续页")
    contract = records["采购合同"]
    number = "YL-OTHER-" + code if mode == "foreign" else contract[0][1]
    records["付款条款续页"] = [("关联协议编号", number)]
    if mode in ("discussion", "standalone"):
        records["付款条款续页"].append(("续页说明", "本页付款安排仅供讨论，双方未确认"))
    records["付款条款续页"].extend(
        item for item in contract if item[0] in ("第二期", "第三期")
    )
    records["采购合同"] = [
        item for item in contract if item[0] not in ("第二期", "第三期")
    ]
    if mode == "standalone":
        records["采购合同"].append(
            ("首款约定", "首笔款项按合同正文独立执行，续页修改不影响首笔款项")
        )
    font = embedded_font("ContractFoliosCJK")
    for filename, titles in layout.items():
        source = folder / (filename + ".pdf")
        output = canvas.Canvas(str(source), pagesize=(595, 842), invariant=1)
        output.setTitle(filename)
        for title in titles:
            draw_pdf_page(output, title, records[title], font=font, spacing=28)
            output.showPage()
        output.save()
        pages = prepare(source, len(titles), save_images=False)
        assert len(pages) == len(titles)
        for page, title in zip(pages, titles):
            actual = [normalize(raw) for raw in page["text"].splitlines()]
            assert actual == [
                normalize(WATERMARK),
                normalize(title),
                *[normalize(k + "：" + v) for k, v in records[title]],
            ]
    return folder, records, layout


def check_sources(cid, mode, folder, layout):
    detail = get("/api/cases/" + cid)
    assert detail["title"] == "合成演练 · " + CASES[mode] and not detail["decisions"]
    report = wait(cid)
    nodes = {n["id"]: n for n in report["graph"]["nodes"] if n["type"] == "page"}
    assert {d["name"] for d in detail["documents"]} == {k + ".pdf" for k in layout}
    for doc in detail["documents"]:
        source = folder / doc["name"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == doc["sha256"]
        for page in prepare(source, len(layout[source.stem]), save_images=False):
            assert nodes[f"{doc['id']}/p{page['number']}"]["sha256"] == page["sha256"]
            assert normalize(page["text"].splitlines()[0]) == normalize(WATERMARK)
    return report


def review(cid, mode, folder, records, layout):
    check_sources(cid, mode, folder, layout)
    reconcile_training_pages(
        cid,
        folder,
        records,
        case_titles=[CASES[mode]],
        layout=layout,
        row_spacing=28,
        field_labels=FIELDS,
        document_types={"付款条款续页": "other"},
    )
    report = confirm_printed_records(cid, folder, records, layout=layout)
    path = "/api/cases/" + cid
    markers = [
        f["id"]
        for f in report["graph"]["facts"]
        if f["field"] == "other"
        and f["status"] == "visual"
        and normalize(f["quote"]) == normalize(WATERMARK)
        and (f.get("source_line") or {}).get("number") == 1
        and normalize(f["source_line"]["text"]) == normalize(WATERMARK)
    ]
    if markers:
        post(
            path + "/attest",
            {
                "rev": get(path)["rev"],
                "reviewer": "水印演练校验",
                "decision": "confirm",
                "facts": markers,
                "note": "已逐页核对生成件及页图摘要，确认第一行测试水印。",
            },
        )
        report = wait(cid)
    return report


def verify_sample(report, mode):
    findings = report["findings"]
    (plan,) = [f for f in findings if f["rule"] == "H03"]
    check = plan["contract_folios"]
    state = {
        "continued": "continued",
        "discussion": "provisional",
        "foreign": "foreign",
        "standalone": "provisional",
    }[mode]
    assert (
        check["state"] == state
        and plan["status"]
        == {"continued": "ok", "foreign": "risk", "provisional": "missing"}[state]
    )
    assert all(f["status"] == "ok" for f in findings if f["rule"] in ("H01", "H02"))
    stages = [f for f in findings if f["rule"] == "H04"]
    assert [f["stage"]["share"] for f in stages] == ["30", "60", "10"]
    expected = (
        ["ok"] * 3
        if mode == "continued"
        else ["ok" if mode == "standalone" else "missing", "missing", "missing"]
    )
    assert [f["status"] for f in stages] == expected
    assert [f["status"] for f in findings if f["rule"] == "H05"] == [
        "ok" if mode == "continued" else "missing"
    ]
    assert [p["stages"] for p in check["pages"]] == [["第一期"], ["第二期", "第三期"]]
    assert all(set(check["evidence"]) <= set(f["evidence"]) for f in [plan, *stages])
    assert bool(check["standalone"]) == (mode == "standalone")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-id", default="watermarked-folios-v1")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    args = parser.parse_args()
    queued = []
    for mode in args.cases:
        folder, records, layout = materials(args.run_id, mode)
        if args.run:
            cid = submit(
                "合成演练 · " + CASES[mode],
                sorted(folder.glob("*.pdf")),
                args.run_id + "-" + mode,
                PROFILE,
            )
            print(mode, cid, flush=True)
            queued.append((cid, mode, folder, records, layout))
        else:
            print(folder)
    for item in queued:
        report = review(*item)
        verify_sample(report, item[1])
        print(
            item[1],
            get("/api/cases/" + item[0])["rev"],
            report["policy"]["version"],
            [
                (f["rule"], f["status"])
                for f in report["findings"]
                if f["rule"].startswith("H")
            ],
            flush=True,
        )
