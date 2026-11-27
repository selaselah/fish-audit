"""Generate three watermarked procurement packets with an incomplete installment schedule.

Pass --run-id with a fresh run identifier to submit them to the local workbench.
Reusing that identifier with the same originals retries the same submissions.
For byte-for-byte reproduction, use the same ReportLab version and CJK font.
"""

import argparse
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import pypdfium2 as pdfium

from generate import WATERMARK, embedded_font, pdf
from publish_batch_version import require
from retest_receipts import BANK, LABEL, materials as receipt_materials
from run import submit


CONTRACT = "采购合同.pdf"
DOCUMENTS = (CONTRACT, "验收报告.pdf", "整改记录单.pdf", "复验报告.pdf", BANK)
CASES = {
    "final": "四期只列三期 · 第二期回单引用已关闭的合格复验单",
    "original": "四期只列三期 · 第二期回单引用不合格初验单",
    "early": "三期仅列九成 · 第二期回单早于所引复验单",
}


def printed_rows(path):
    with pdfium.PdfDocument(path) as doc:
        require(len(doc) == 1, path.name + " 应为单页")
        with closing(doc[0]) as page, closing(page.get_textpage()) as text:
            lines = text.get_text_bounded().splitlines()
    require(lines[:2] == [WATERMARK, path.stem], path.name + " 的水印及标题")
    rows = [line.split("：", 1) for line in lines[2:]]
    require(all(len(row) == 2 for row in rows), path.name + " 的印刷行")
    return [tuple(row) for row in rows]


def replace_row(rows, label, old, new):
    require([value for key, value in rows if key == label] == [old], label + " 应有唯一的母本原行")
    return [(key, new if key == label else value) for key, value in rows]


def materials(folder, key, archive=None):
    """Start with the retest receipt fixture or its digest-pinned R8 master."""
    title = CASES[key]
    folder.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=folder) as tmp:
        _, sources, profile = receipt_materials(archive, Path(tmp), key)
        source = {p.name: p for p in sources}
        rows = printed_rows(source[CONTRACT])
        require(("含税总额", "100,000.00") in rows and rows[-4:] == [
            ("付款条款", "分三期付款"), ("第一期", "合同生效后支付30%"),
            ("第二期", "最终验收合格后支付60%"), ("第三期", "质保期满后支付10%"),
        ], "采购合同的三期母本")
        bank_rows = printed_rows(source[BANK])
        reference = "YS-92B34462" if key == "original" else "FY-92B34462"
        paid = "2026年9月17日" if key == "early" else "2026年9月21日"
        require(bank_rows[-5:] == [
            ("付款金额", "60,000.00"), ("款项用途", "第二期"), ("交易状态", "交易成功"),
            ("付款日期", paid), (LABEL, reference),
        ], "成功回单的期次、日期与完整单号")
        if key == "early":
            rows = replace_row(rows, "第二期", "最终验收合格后支付60%", "最终验收合格后支付50%")
            bank_rows = replace_row(bank_rows, "付款金额", "60,000.00", "50,000.00")
            pdf(source[BANK], Path(BANK).stem, bank_rows, font=embedded_font("RetestReference"), spacing=28)
        else:
            rows = replace_row(rows, "付款条款", "分三期付款", "分四期付款")
        pdf(source[CONTRACT], Path(CONTRACT).stem, rows, font=embedded_font("QualityReinspectionCJK"))
        require(printed_rows(source[CONTRACT]) == rows and printed_rows(source[BANK]) == bank_rows,
                "变更后的合同与回单原行")
        paths = [folder / name for name in DOCUMENTS]
        for dest in paths:
            # Publish the complete staged file in one step, including on concurrent retries.
            try:
                dest.hardlink_to(source[dest.name])
            except FileExistsError:
                require(dest.read_bytes() == source[dest.name].read_bytes(), dest.name + " 已有另一份原件")
    return title, paths, profile


def submit_packet(title, paths, profile, run_id, key):
    fingerprint = sha256(f"{run_id}\0{key}\0".encode())
    for path in paths:
        checksum = sha256(path.read_bytes()).hexdigest()
        fingerprint.update(checksum.encode("ascii") + b"\0")
    return submit("合成演练 · " + title, paths, "incomplete-schedule-" + fingerprint.hexdigest(), profile)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="输出三组独立水印原件的目录")
    parser.add_argument("--archive", type=Path, help="可选，用已核摘要的复验 R8 水印母本生成")
    parser.add_argument("--run-id", help="使用本机当前部署的规则提交；同一标识可幂等重试")
    args = parser.parse_args()
    for key in CASES:
        folder = args.folder / key
        title, paths, profile = materials(folder, key, args.archive)
        print(key, submit_packet(title, paths, profile, args.run_id, key) if args.run_id else folder, flush=True)
