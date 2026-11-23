"""Generate plainly marked synthetic procurement files for Fish Audit."""

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parent / "generated"
WATERMARK = "合成演练资料　仅供系统测试　无交易效力"
BUYER = "青禾演练采购中心"
SELLER = "云桥演练设备中心"


def fields(kind, contract, total, tax="1,300.00", net="10,000.00", number="YL-FP-016"):
    values = {
        "合同": [("签约日期", "2026年10月12日"), ("结算条款", "验收后一次性全额结算")],
        "发票": [("发票号码", number), ("开票日期", "2026年10月20日"),
                ("不含税合计", net), ("税额合计", tax)],
        "验收": [("验收日期", "2026年10月19日"), ("验收结论", "合格")],
    }
    return [("合同编号", contract), ("采购方", BUYER), ("供应方", SELLER),
            ("采购标的", "档案柜"), ("币种", "人民币"), ("金额单位", "元"), ("含税总额", total)] + values[kind]


def draw_pdf_page(printout, title, rows, duplicate=False):
    printout.setFont("STSong-Light", 14)
    printout.drawString(48, 780, WATERMARK)
    printout.setFont("STSong-Light", 27)
    printout.drawString(48, 709, title)
    printout.line(48, 690, 540, 690)
    printout.setFont("STSong-Light", 15)
    for index, (label, value) in enumerate(rows):
        printout.drawString(48, 649 - 34 * index, f"{label}：{value}")
    if duplicate:
        printout.drawString(48, 166, "附件为提交人整理的副本。")


def pdf(path, title, rows, duplicate=False):
    printout = canvas.Canvas(str(path), pagesize=(595, 842), invariant=1)
    printout.setTitle(title)
    draw_pdf_page(printout, title, rows, duplicate)
    printout.save()


def word(path, title, rows):
    document = Document()
    properties = document.core_properties
    properties.author = "Fish Audit 合成演练"
    properties.last_modified_by = properties.author
    style = document.styles["Normal"]
    style.font.name = "Songti SC"
    style.font.size = Pt(14)
    style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Songti SC")
    document.add_paragraph(WATERMARK)
    document.add_paragraph(title, style="Title")
    for label, value in rows:
        document.add_paragraph(f"{label}：{value}")
    document.save(path)


def scan(path, title, rows):
    font_path = Path("/System/Library/Fonts/Supplemental/Songti.ttc")
    if not font_path.is_file():
        raise SystemExit("生成扫描样本需要 CJK 字体，请修改 font_path。")
    font = ImageFont.truetype(str(font_path), 39)
    scan_image = Image.new("RGB", (1280, 1536), "#fffcf6")
    draw = ImageDraw.Draw(scan_image)
    draw.text((78, 64), WATERMARK, font=font, fill="#666666")
    draw.text((78, 182), title, font=ImageFont.truetype(str(font_path), 61), fill="#212121")
    for index, (label, value) in enumerate(rows):
        top = 332 + index * 92
        draw.text((78, top), f"{label}：{value}", font=font, fill="#222222")
        if label == "含税总额":
            box = (268, top - 4, 900, top + 65)
            scan_image.paste(scan_image.crop(box).filter(ImageFilter.GaussianBlur(23)), box)
    scan_image.save(path, quality=86)
    scan_image.save(path.with_suffix(".pdf"), "PDF", resolution=140,
                    creationDate="D:20261001000000Z", modDate="D:20261001000000Z")


def generate_split():
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    split = ROOT / "04-分票结算与跨单汇总"
    split.mkdir(exist_ok=True, parents=True)
    contract = fields("合同", "YL-HT-049", "11,300.00")
    contract[-1] = ("结算条款", "分两期付款，每期50%")
    word(split / "分期采购合同.docx", "设备采购合同", contract)
    pdf(split / "到货验收单.pdf", "到货验收单", fields("验收", "YL-HT-049", "11,300.00"))
    for index in (1, 2):
        rows = fields("发票", "YL-HT-049", "5,650.00", tax="650.00", net="5,000.00", number=f"YL-FP-049-{index}")
        pdf(split / f"第{index}期发票.pdf", "采购发票", rows)
    return split


def generate_travel():
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    folder = ROOT / "05-差旅超额与跨期"
    folder.mkdir(exist_ok=True, parents=True)
    shared = [("出差人员", "演练甲"), ("币种", "人民币"), ("金额单位", "元")]
    pdf(folder / "报销申请.pdf", "差旅报销单", [*shared, ("出差开始日期", "2026年10月12日"),
        ("出差结束日期", "2026年10月15日"), ("申请报销金额", "1,200.00"),
        ("随附发票号码", "YL-LV-051"), ("随附发票号码", "YL-LV-052")])
    for index, (total, date) in enumerate([("600.00","2026年10月13日"), ("450.00","2026年10月18日")], 1):
        pdf(folder / f"住宿票据{index}.pdf", "住宿服务发票", [*shared, ("发票号码", f"YL-LV-05{index}"),
            ("费用发生日期", date), ("开票日期", "2026年10月21日"), ("含税总额", total)])
    return folder


def generate_resubmission():
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    folder = ROOT / "06-同票补件重提"
    folder.mkdir(exist_ok=True, parents=True)
    for kind, title in (("合同", "设备采购合同"), ("发票", "采购发票"), ("验收", "到货验收单")):
        rows = fields(kind, "YL-HT-038", "11,300.00", number="YL-FP-038")
        pdf(folder / (title + ".pdf"), title, rows)
    return folder


def generate_packet():
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    folder = ROOT / "07-采购三单合订"
    folder.mkdir(exist_ok=True, parents=True)
    packet = canvas.Canvas(str(folder / "采购业务合订件.pdf"), pagesize=(595, 842), invariant=1)
    packet.setTitle("合成演练 · 采购业务合订件")
    for kind, title in (("合同", "设备采购合同"), ("发票", "采购发票"), ("验收", "到货验收单")):
        rows = fields(kind, "YL-HT-071", "11,300.00", number="YL-FP-071")
        draw_pdf_page(packet, title, rows)
        packet.showPage()
    packet.save()
    return folder


def main():
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    clean = ROOT / "01-档案柜采购"
    conflict = ROOT / "02-同号票据与金额差异"
    unclear = ROOT / "03-模糊扫描与缺件"
    for folder in (clean, conflict, unclear):
        folder.mkdir(exist_ok=True, parents=True)
    for folder, contract in ((clean, "YL-HT-016"), (conflict, "YL-HT-027")):
        word(folder / "采购合同.docx", "设备采购合同", fields("合同", contract, "11,300.00"))
        pdf(folder / "到货验收单.pdf", "到货验收单", fields("验收", contract, "11,300.00"))
        rows = fields("发票", contract, "11,300.00" if folder == clean else "13,300.00",
                      number="YL-FP-016" if folder == clean else "YL-FP-027")
        pdf(folder / "采购发票.pdf", "采购发票", rows)
        if folder == conflict:
            pdf(folder / "采购发票副本.pdf", "采购发票", rows, duplicate=True)
    scan(unclear / "现场拍照.jpg", "采购发票", fields("发票", "YL-HT-038", "11,300.00", number="YL-FP-038"))
    generate_split()
    generate_travel()
    generate_resubmission()
    generate_packet()
    print(ROOT)


if __name__ == "__main__":
    main()
