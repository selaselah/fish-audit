"""Watermarked procurement exercises for the exact equipment model received."""

import argparse
import hashlib
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pypdfium2 as pdfium

from contract_milestones import PROFILE, confirm_printed_records, documents
from delivery_batches import FIELD_LABELS, TITLES, batch_documents
from generate import ROOT, embedded_font, pdf, word
from quality_addenda import pdf_with_note
from quality_reinspection import reconcile_training_pages
from run import BASE, get, post, submit, wait
from warranty_release import check_training_watermark


CASES = {
    "match": "合同及终验单型号一致且履约资料齐备",
    "disputed": "验收单型号末位有核图异议后重新确认",
    "batch_disputed": "两批独立付款仅第二批的实收型号有异议",
    "wrong": "四台柜温合格但终验实收另一型号",
    "absent": "合同指定型号而终验单只有品名",
    "masked": "终验型号末位遮盖",
    "substitute": "型号不同且另有同等型号替代说明",
    "image": "同型号终验单另附影像中的换型说明",
    "approval": "所验型号相符但缺董事会生效批准",
    "quality": "所验型号相符但实测温度超限",
    "foreign": "不同合同号的验收单载有另一型号",
    "batches": "两批独立验收第二批实收型号不同",
    "camera": "Word合同及影像验收单的设备型号待核图",
}
REVIEW_SCENARIOS = {"disputed": ("验收报告", "YL-C4", "match"),
                    "batch_disputed": ("第二批验收报告", "YL-C2", "batches")}


def mixed_originals(folder, records, font):
    with tempfile.TemporaryDirectory() as temp:
        docx = Path(temp) / "合同.docx"
        word(docx, "采购合同", records["采购合同"])
        # Fixed ZIP member dates keep repeated submissions of this watermarked fixture byte-identical.
        with ZipFile(docx) as src, ZipFile(folder / "采购合同.docx", "w") as dest:
            for name in sorted(src.namelist()):
                dest.writestr(ZipInfo(name), src.read(name), compress_type=ZIP_DEFLATED)
        page = Path(temp) / "验收.pdf"
        pdf(page, "验收报告", records["验收报告"], font=font, spacing=27)
        with pdfium.PdfDocument(page) as document:
            document[0].render(scale=2).to_pil().convert("RGB").save(folder / "验收报告.jpg", quality=89)
    for name in ("银行付款回单", "质保期满确认单"):
        pdf(folder / (name + ".pdf"), name, records[name], font=font, spacing=27)


def generate(seed, mode):
    code = hashlib.sha256((seed + '-' + mode).encode()).hexdigest()[:8].upper()
    if mode in REVIEW_SCENARIOS:
        mode = REVIEW_SCENARIOS[mode][2]
    records = batch_documents(code, "complete") if mode == "batches" else documents(code, "complete")
    contract = records["采购合同"]
    receipt = records["第二批验收报告" if mode == "batches" else "验收报告"]
    contract.append(("约定设备型号", "YL-C4"))
    received = {"wrong": "YL-C2", "masked": "YL-C*", "substitute": "YL-C2", "foreign": "YL-C2", "batches": "YL-C2", "camera": "YL-C2"}.get(mode, "YL-C4")
    if mode == "batches":
        records["第一批验收报告"].append(("实收设备型号", "YL-C4"))
    if mode != "absent":
        receipt.append(("实收设备型号", received))
    if mode == "substitute":
        contract.append(("替代型号约定", "经甲方书面同意可换同等型号"))
    if mode == "approval":
        contract[:] = [(k, "本合同自双方盖章并经甲方董事会批准后生效" if k == "生效条款" else v) for k, v in contract]
    if mode == "quality":
        receipt[:] = [(k, "柜温8℃" if k == "实测结果" else v) for k, v in receipt]
    if mode == "foreign":
        receipt[0] = ("合同编号", "YL-LY-" + code + "-B")
    folder = ROOT / "41-合同型号与实收型号" / code
    folder.mkdir(parents=True, exist_ok=True)
    font = embedded_font("EquipmentModelCJK")
    if mode == "camera":
        mixed_originals(folder, records, font)
        return folder, records
    for name, rows in records.items():
        target = folder / (name + ".pdf")
        if mode == "image" and name == "验收报告":
            pdf_with_note(target, name, rows, font, "换型说明：另交替代型号，书面同意待补", spacing=27)
        else:
            pdf(target, TITLES.get(name, name), rows, font=font, spacing=27)
    return folder, records


def settle(cid, folder, records, *, exact_model=False):
    if (folder / "验收报告.jpg").is_file():
        report = wait(cid)
        originals = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
        assert {d["name"]: d["sha256"] for d in report["graph"]["documents"]} == originals
        return report
    labels = {**FIELD_LABELS, "约定设备型号": "equipment_model", "实收设备型号": "equipment_model", "替代型号约定": "other"}
    exact = ("payment_stage", "delivery_batch", "delivered_serials") + (("equipment_model",) if exact_model else ())
    reconcile_training_pages(cid, folder, records, case_titles=CASES.values(), field_labels=labels, row_spacing=27,
                             printed_titles=TITLES, exact_fields=exact)
    report = confirm_printed_records(cid, folder, records)
    return check_training_watermark(cid, folder, records, report)


def validate(report, mode):
    calls = report["calls"]
    assert all(c["response_id"] and c["request_id"] for c in [*calls["pages"], calls["expert"]])
    if mode == "camera":
        g = report["graph"]
        doc = next(d["id"] for d in g["documents"] if d["name"] == "验收报告.jpg")
        assert any(p["doc"] == doc and not p["native"] for p in g["equipment_model_sources"]["pages"])
        assert any(d["name"] == "采购合同.docx" for d in g["documents"])
        assert len(calls["pages"]) >= 4 and report["result"]["verdict"] == "review"
        assert not any(e["type"] == "equipment_model_comparison" for e in g["edges"])
        assert all(f["status"] != "ok" for f in report["findings"] if f["rule"] == "H02")
        return
    batch = mode in ("batches", "batch_disputed")
    assert len(calls["pages"]) == (5 if batch else 4)
    fs = report["findings"]
    effect = next(f for f in fs if f["rule"] == "H01")
    inspection = next(f for f in fs if f["rule"] == "H02")
    stages = [f for f in fs if f["rule"] == "H04"]
    models = inspection["equipment_models"]
    expected = {"match": "ok", "approval": "ok", "quality": "ok", "wrong": "issue", "batches": "issue"}
    assert models["status"] == expected.get(mode, "missing"), (mode, models["detail"])
    assert effect["status"] == ("missing" if mode == "approval" else "ok"), (mode, effect["detail"])
    assert models["ordered"]["value"] == "YL-C4"
    if batch:
        affected = "missing" if mode=="batch_disputed" else "risk"
        assert [(s["stage"]["share"],s["status"]) for s in stages] == [("20","ok"),("35","ok"),("35",affected),("10",affected)]
        assert [r["status"] for r in inspection["batch_acceptance"]["batches"]] == ["ok","missing" if mode=="batch_disputed" else "issue"]
    else:
        assert [s["stage"]["share"] for s in stages] == ["30","60","10"]
        assert (stages[0]["status"] == "ok") == (mode != "approval")
        assert all((s["status"] == "ok") == (mode == "match") for s in stages[1:])
    if mode == "approval":
        assert "董事会" in effect["detail"] and inspection["status"] == "ok"
    if mode == "quality":
        assert "8" in inspection["detail"] and inspection["status"] == "issue"
    if mode == "foreign":
        assert models["records"][0]["identity"]["matches"] is False
    if mode in REVIEW_SCENARIOS:
        row, = [r for r in models["records"] if r.get("review_holds")]
        hold, = row["review_holds"]
        ref, = hold["facts"]
        assert next(f for f in report["graph"]["facts"] if f["id"] == ref)["status"] == "disputed"
        assert row["comparison"] == "unresolved" and ref in row["evidence"]
        assert all(ref in s["evidence"] for s in stages[-2:])
        compared = [e for e in report["graph"]["edges"] if e["type"]=="equipment_model_comparison"]
        assert len(compared) == (1 if batch else 0) and all(ref not in e["evidence"] for e in compared)
        payment = next(f for f in fs if f["rule"]=="H05")
        assert (payment["status"]=="ok") == batch
        if batch:
            assert ref not in stages[1]["evidence"] and ref not in payment["evidence"]
    assert report["result"]["verdict"] == ("reject" if mode in ("wrong","batches","quality") else "pass" if mode == "match" else "review")


def exercise_model_review(cid, folder, report, mode):
    path = "/api/cases/" + cid
    name, model, baseline = REVIEW_SCENARIOS[mode]
    doc, = [d for d in report["graph"]["documents"] if d["name"] == name+".pdf"]
    source = folder / doc["name"]
    assert get(path)["title"] == "合成演练 · " + CASES[mode]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == doc["sha256"]
    quote = "实收设备型号：" + model
    with pdfium.PdfDocument(source) as pdf:
        assert pdf[0].get_textpage().get_text_bounded().splitlines().count(quote) == 1
    fact, = [f for f in report["graph"]["facts"] if f["doc"] == doc["id"] and f["page"] == 1
             and f["field"] == "equipment_model" and f["value"] == model and f["quote"] == quote
             and (f.get("source_line") or {}).get("text") == quote]
    reason = "合成演练：验收单型号栏的末位字符待复核。"
    resolved = f"合成演练：重新对照原件对应行，确认印刷型号为 {model}。"
    def mark(decision, note):
        post(path+"/attest", {"rev": get(path)["rev"], "reviewer": "水印演练核图", "decision": decision,
                              "facts": [fact["id"]], "note": note})
        return wait(cid)
    review = fact.get("attestation") or {}
    if review.get("note") == resolved and review["decision"] == "confirm":
        held_rev = review["rev"]
    else:
        if fact["status"] != "disputed":
            validate(report, baseline)
            report = mark("dispute", reason)
        validate(report, mode)
        held_rev = get(path)["rev"]
        report = mark("confirm", resolved)
    validate(report, baseline)
    held = get(path + "/reports/" + str(held_rev))["report"]
    validate(held, mode)
    assert held["calls"]["pages"] == report["calls"]["pages"]
    assert held["graph"]["documents"] == report["graph"]["documents"]
    print("型号异议", BASE + "/workpaper/" + cid + "?rev=" + str(held_rev) + "&fact=" + fact["id"], flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", choices=CASES, nargs="+", default=list(CASES))
    parser.add_argument("--run-id", default="synthetic-equipment-models-v1")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    submitted = []
    for mode in args.cases:
        folder, records = generate(args.run_id, mode)
        if not args.run:
            print(folder)
            continue
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".pdf", ".jpg", ".docx"})
        cid = submit("合成演练 · " + CASES[mode], files, args.run_id + "-" + mode, PROFILE)
        submitted.append((mode, cid, folder, records))
        print(mode, BASE + "/workpaper/" + cid, flush=True)
    for mode, cid, folder, records in submitted:
        report = settle(cid, folder, records, exact_model=mode in REVIEW_SCENARIOS)
        if mode in REVIEW_SCENARIOS:
            report = exercise_model_review(cid, folder, report, mode)
        else:
            validate(report, mode)
        print(mode, "R" + str(get("/api/cases/" + cid)["rev"]), report["result"]["verdict"], flush=True)
