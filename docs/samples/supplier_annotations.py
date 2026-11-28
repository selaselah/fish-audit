"""Exercise supplier comments, mismatched seller names and the scope stated on a signed PDF."""

import argparse
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import mkdtemp

from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

NOTE = "实际供货单位另附送货单，请核对与合同供应方的关系。"
THIRD = "山岚演练交付中心"
REASON = "仅确认到货数量，实际供货单位及终验质量仍待核对。"
CASES = {"comment": "签后批注要求核对实际供货方", "different": "签名控件与不同的终验供货方",
         "reason": "电子签名原因仅确认到货数量", "receipt_reason": "验收报告电子签名仅确认到货数量"}


def check_quantity_scope(report, mode):
    contract = mode == "reason"
    row, = report["graph"]["signature_purposes"]["rows"]
    doc = next(d for d in report["graph"]["documents"] if d["id"] == row["doc"])
    assert (doc["name"], row["original_sha256"]) == ("采购合同.pdf" if contract else "验收报告.pdf", doc["sha256"])
    assert (row["role"], row["scope"], row["reason"]) == ("contract" if contract else "acceptance", "quantity_only", REASON)
    owner = "H01" if contract else "H02"
    stages = {"第一期", "第二期", "第三期"} if contract else {"第二期", "第三期"}
    cited = [f for f in report["findings"] if "signature_purposes" in f]
    assert all(f["signature_purposes"] == [row["id"]] and row["id"] in f["evidence"] for f in cited)
    assert [(f["rule"], f["status"]) for f in cited if f["rule"] in ("H01", "H02")] == [(owner, "risk")]
    assert {f["stage"]["name"] for f in cited if f["rule"] == "H04"} == stages
    assert [(f["stage"]["name"], f["status"]) for f in cited if f["rule"] == "H05"] == [("第二期", "missing")]


def with_comment(raw, page=0):
    """Add a normal, visible review note to a watermarked test contract."""
    writer = IncrementalPdfFileWriter(BytesIO(raw))
    ref, _ = writer.find_page_for_modification(page)
    note = generic.DictionaryObject({
        generic.pdf_name("/Type"): generic.pdf_name("/Annot"),
        generic.pdf_name("/Subtype"): generic.pdf_name("/Text"),
        generic.pdf_name("/Rect"): generic.ArrayObject(map(generic.NumberObject, [38, 478, 62, 502])),
        generic.pdf_name("/Name"): generic.pdf_name("/Comment"),
        generic.pdf_name("/T"): generic.pdf_string("合成演练核验"),
        generic.pdf_name("/Contents"): generic.pdf_string(NOTE),
        generic.pdf_name("/P"): ref,
    })
    writer.register_annotation(ref, writer.add_object(note))
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def run(seed, upload, modes):
    from contract_milestones import PROFILE, documents
    from generate import ROOT, WATERMARK, embedded_font, pdf
    from pdf_signing import signed_copy
    from printed_dates import read_back
    from reinspection_register import prepare
    from run import get, submit, wait

    code = sha256(seed.encode()).hexdigest()[:8].upper()
    root = ROOT / "PDF供方核对"
    root.mkdir(parents=True, exist_ok=True)
    base = Path(mkdtemp(prefix=code + "-", dir=root))
    print(base, flush=True)
    records = documents(code, "complete")
    font = embedded_font("SupplierAnnotationFixture")
    raw = base / "采购合同.pdf"
    pdf(raw, "采购合同", records["采购合同"], font=font)
    signed = signed_copy(raw.read_bytes())
    submitted = []
    for mode in modes:
        title = CASES[mode]
        folder = base / mode
        folder.mkdir()
        paths, originals = [], {}
        for name, fields in records.items():
            path = folder / (name + ".pdf")
            if name == "采购合同":
                content = raw.read_bytes() if mode == "receipt_reason" else signed
                if mode == "reason":
                    content = signed_copy(raw.read_bytes(), reason=REASON)
                path.write_bytes(with_comment(content) if mode == "comment" else content)
            else:
                if mode == "different" and name == "验收报告":
                    fields = [(k, THIRD if k == "供应方" else v) for k, v in fields]
                pdf(path, name, fields, font=font)
                if mode == "receipt_reason" and name == "验收报告":
                    path.write_bytes(signed_copy(path.read_bytes(), reason=REASON))
            page, = prepare(path, 1, save_images=False)
            lines = page["text"].splitlines()
            assert lines[0] == WATERMARK and all(k + "：" + v in lines for k, v in fields)
            paths.append(path)
            originals[path.name] = (sha256(path.read_bytes()).hexdigest(), page)
        if upload:
            title = "合成演练 · " + title
            cid = submit(title, paths, seed + mode + originals["采购合同.pdf"][0][:16], PROFILE)
            print(mode, cid, flush=True)
            submitted.append((mode, title, cid, originals))
    for mode, title, cid, originals in submitted:
        report = read_back(cid, title, originals, wait(cid))
        acceptance = next(f for f in report["findings"] if f["rule"] == "H02")
        supplier = acceptance["acceptance_reservations"]["supplier"]
        page, = report["graph"]["supplier_page_sources"]["pages"]
        assert supplier["page_inspections"] == [page["id"]] and page["id"] in acceptance["evidence"]
        if mode == "comment":
            assert page["state"] == "annotations" and NOTE in [n["note"] for n in page["annotations"]]
            assert supplier["status"] == "missing"
        elif mode in ("reason", "receipt_reason"):
            assert page["state"] == "annotations" and REASON in [n.get("signing_reason") for n in page["annotations"]]
            assert page["role"] == ("receipt" if mode == "receipt_reason" else "contract")
            assert supplier["status"] == "missing"
            check_quantity_scope(report, mode)
        else:
            assert page["state"] == "same_print" and THIRD in supplier["names"].values() and supplier["status"] == "risk"
        assert all(f["status"] != "ok" for f in report["findings"] if f["rule"] in ("H01", "H04", "H05"))
        print(mode, cid, "R" + str(get("/api/cases/" + cid)["rev"]), page["state"], acceptance["status"], supplier["status"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--case", nargs="+", choices=CASES, default=list(CASES))
    opts = parser.parse_args()
    run(opts.seed, opts.run, opts.case)
