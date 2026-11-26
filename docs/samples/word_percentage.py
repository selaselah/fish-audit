"""Exercise a percentage printed with a space between its digits in a synthetic Word contract."""

import argparse
import hashlib
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from contract_milestones import PROFILE, documents, normalize
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from generate import ROOT, WATERMARK, embedded_font, pdf
from run import get, submit, wait

TITLE = "合成演练 · Word 合同验收款的两个数字之间留有空格"


def contract_file(path, rows):
    document = Document()
    document.core_properties.author = "Fish Audit 合成演练"
    document.core_properties.last_modified_by = document.core_properties.author
    style = document.styles["Normal"]
    style.font.name = "Songti SC"
    style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Songti SC")
    style.font.size = Pt(12)
    style.paragraph_format.space_after = Pt(5)
    document.add_paragraph(WATERMARK).runs[0].font.color.rgb = RGBColor.from_string("555555")
    title = document.add_paragraph("采购合同", style="Title")
    title.runs[0].font.color.rgb = RGBColor.from_string("101010")
    title.runs[0].font.size = Pt(21)
    properties = document.styles["Title"].element.get_or_add_pPr()
    for border in properties.findall(qn("w:pBdr")):
        properties.remove(border)
    for label, value in rows:
        document.add_paragraph(label + "：" + value)
    buffer = BytesIO()
    document.save(buffer)
    with ZipFile(buffer) as package, ZipFile(path, "w") as output:
        for name in sorted(package.namelist()):
            entry = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            output.writestr(entry, package.read(name), compress_type=ZIP_DEFLATED)


def materials(seed, *, split=True):
    code = hashlib.sha256(seed.encode()).hexdigest()[:8].upper()
    folder = ROOT / ("Word期款数字" if split else "Word签署凭证") / code
    folder.mkdir(parents=True, exist_ok=True)
    records = documents(code, "complete")
    rows = [(k, "最终验收合格后支付6 0%" if split and k == "第二期" else v) for k, v in records.pop("采购合同")]
    contract = folder / "演练采购合同.docx"
    contract_file(contract, rows)
    font = embedded_font("WordPercentageCJK")
    paths = [contract]
    for title, rows in records.items():
        source = folder / (title + ".pdf")
        pdf(source, title, rows, font=font, spacing=30)
        paths.append(source)
    return paths


def check_pages(paths):
    from reinspection_register import prepare

    for path in paths:
        page, = prepare(path, 1, save_images=False)
        assert normalize(WATERMARK) == normalize(page["text"].splitlines()[0])
        if path.suffix == ".docx":
            assert any("6 0%" in line and "第二期" in line for line in page["text"].splitlines())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="word-percentage-20261126")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    paths = materials(args.run_id)
    if args.run:
        check_pages(paths)
        cid = submit(TITLE, paths, args.run_id, PROFILE)
        print(cid, flush=True)
        report = wait(cid)
        detail = get("/api/cases/" + cid)
        assert detail["title"] == TITLE and {d["name"]: d["sha256"] for d in detail["documents"]} == {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        }
        plan, = [f for f in report["findings"] if f["rule"] == "H03"]
        assert plan["contract_folios"]["state"] == "numeral" and plan["status"] == "missing"
        held = [f for f in report["findings"] if f.get("stage", {}).get("name") == "第二期"]
        assert held and all(not f["stage"]["share"] and f["status"] != "ok" for f in held)
        print(f"R{detail['rev']} · 原页断字，验收款比例待核", flush=True)
    else:
        print(paths[0])
