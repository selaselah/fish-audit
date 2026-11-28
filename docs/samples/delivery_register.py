"""Rebuild marked purchases with the same quantities and different equipment serial registers."""

import argparse
from hashlib import sha256
from pathlib import Path

import pypdfium2 as pdfium

from contract_milestones import PROFILE, documents
from generate import WATERMARK, embedded_font, pdf
from run import get, post, submit, wait


ORDERED = ("FA-0101", "FA-0102", "FA-0103", "FA-0104")
CASES = {
    "difference": ("同型冷藏柜的终验清单多出另一台设备", (*ORDERED[:3], "FA-0109")),
    "repeated": ("四台冷藏柜的验收清单重复抄入一个编号", (*ORDERED[:3], ORDERED[2])),
    "reordered": ("同一批四台冷藏柜的终验登记顺序不同", tuple(reversed(ORDERED))),
    "masked": ("冷藏柜验收清单末台只写了部分编号", (*ORDERED[:3], "FA-01**")),
}


def build(folder, key):
    title, received = CASES[key]
    code = sha256(("delivery-register-v1-" + key).encode()).hexdigest()[:8].upper()
    records = documents(code, "complete")
    records["采购合同"].extend([("约定设备型号", "YL-C4"), ("约定设备序列号", "、".join(ORDERED))])
    records["验收报告"].extend([("实收设备型号", "YL-C4"), ("实收设备序列号", "、".join(received))])
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for name, fields in records.items():
        destination = folder / (name + ".pdf")
        pdf(destination, name, fields, font=embedded_font("DeliveryRegister"), spacing=27)
        files.append(destination)
    return title, files


def check_fields(cid, title, files):
    """Reconcile the identity and payment fields only on the exact generated exercises."""
    api = "/api/cases/" + cid
    case = get(api)
    originals = {d["name"]: d for d in case["documents"]}
    hashes = {p.name: sha256(p.read_bytes()).hexdigest() for p in files}
    if (case["title"] != "合成演练 · " + title or case["decisions"] or case["referrals"] or
            hashes != {name: d["sha256"] for name, d in originals.items()}):
        raise ValueError("核字需要本组水印原件、原始案件和待验收底稿")
    report = wait(cid)
    parties = {"合同编号":"contract_id","采购方":"buyer","供应方":"seller","采购标的":"subject"}
    labels = {"采购合同.pdf":parties, "验收报告.pdf":{**parties,"验收范围":"acceptance_scope"},
              "银行付款回单.pdf":{"合同编号":"contract_id","款项用途":"payment_designation","付款日期":"paid_on",
                              "交易状态":"transfer_status","付款户名":"payer","收款户名":"payee"}}
    for path in files:
        if path.name not in labels:
            continue
        doc = originals[path.name]["id"]
        with pdfium.PdfDocument(path) as source:
            lines = source[0].get_textpage().get_text_bounded().splitlines()
            if len(source)!=1 or lines[0]!=WATERMARK or len(lines)!=len(set(lines)):
                raise ValueError("请核对生成件的页首水印、页数及各栏原行")
        for i, line in enumerate(lines):
            label, _, value = line.partition("：")
            field = labels[path.name].get(label)
            if not field:
                continue
            facts = [f for f in report["graph"]["facts"] if f["doc"]==doc and f["page"]==1 and f["field"]==field and
                     f["status"]!="superseded"]
            if any(f["status"] in ("anchored","confirmed") and (f.get("source_line") or {}).get("text")==line for f in facts):
                continue
            if len(facts)>1 or any(f.get("attestation") or f.get("amendment") for f in facts):
                raise ValueError("同栏已有多份抄录或人工核字记录，请在底稿核对")
            top = (842-649+27*(i-2))/842
            post(api+"/amend", {"rev":get(api)["rev"], "doc":doc, "page":1, "field":field, "value":value, "quote":line,
                 "target":facts[0]["id"] if facts else None, "region":"top" if top<1/3 else "bottom" if top>=2/3 else "middle",
                 "reviewer":"设备清单水印演练核字", "note":"已核对生成件水印、文件摘要及原页整行，按排印栏更正本次模拟抄录。"})
            report = wait(cid)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--check-fields", action="store_true", help="按水印原页逐项核对归属及回单字段")
    args = parser.parse_args()
    if args.check_fields and not args.run:
        parser.error("--check-fields 需要 --run")
    submitted = []
    for case in ([args.case] if args.case else CASES):
        title, paths = build(args.folder / case, case)
        if args.run:
            token = sha256(b"".join(sha256(p.read_bytes()).digest() for p in paths)).hexdigest()
            cid = submit("合成演练 · " + title, paths, "delivery-register-" + token, PROFILE)
            submitted.append((cid,title,paths))
            print(case, cid, flush=True)
        else:
            print(case, args.folder / case)
    if args.check_fields:
        for cid,title,paths in submitted:
            report = check_fields(cid,title,paths)
            checked = next(f for f in report["findings"] if f["rule"]=="H02")
            print(title, checked["status"], checked.get("inspection_coverage",{}).get("state"), flush=True)
