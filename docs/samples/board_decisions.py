"""Exercise board-approval filing evidence on the same watermarked contract and transfers."""

import argparse
from shutil import copyfile
from pathlib import Path
from zipfile import ZipFile

from generate import WATERMARK, embedded_font, pdf
from publish_batch_version import digest, require
from release_originals_demo import check_fields, materials
from run import submit


MASTER = ("9c84d34e49034b2096bb2edfe14918d6", 4, "cf3e574a5e61c35e869809c4a502f7fc45b5879853334a80d5bd634b30f746da")
CASES = {"current":"董事会审批单 · 测试签名覆盖本版", "earlier":"董事会审批单 · 签后另存新版",
         "comment":"董事会审批单 · 决定栏附另行表决批注", "scan":"董事会审批单 · 扫描签认栏",
         "hot":"董事会决议待核、验收柜温超限且第二期已付款"}
COMMENT = "本次仅同意谈判。签订采购合同须另行表决，请核对最终决议。"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--check-fields", action="store_true")
    parser.add_argument("--cases", choices=CASES, nargs="+", default=list(CASES))
    args = parser.parse_args()
    if args.check_fields and not args.run:
        parser.error("--check-fields 需要 --run 提交水印演练")
    profile, groups = materials(args.archive, args.folder, master=MASTER, title="合同审批单",
                               decision=("审批决定","批准"), comment=COMMENT, signature_field="SyntheticBoardDecision")
    if "hot" in args.cases:
        target=args.folder/"hot"
        target.mkdir(exist_ok=True)
        with ZipFile(args.archive) as pack:
            lines=pack.read("pages/d05/1.txt").decode().splitlines()
        require(lines[:2]==[WATERMARK,"验收报告"] and lines.count("实测结果：柜温3℃")==1, "母本验收原行")
        rows=[line.split("：",1) for line in lines[2:]]
        groups["hot"]=[]
        for source in groups["comment"]:
            dest=target/source.name
            if source.name=="验收报告.pdf":
                pdf(dest,"验收报告",[(k,"柜温8℃" if k=="实测结果" else v) for k,v in rows],font=embedded_font("BoardAcceptance"),spacing=28)
            else:
                copyfile(source,dest)
            groups["hot"].append(dest)
    queued = {}
    for mode in args.cases:
        files=groups[mode]
        if args.run:
            key = digest("".join(digest(p.read_bytes()) for p in files).encode())
            queued[mode] = submit("合成演练 · "+CASES[mode], files, "board-decision-"+key, profile)
            print(mode, queued[mode], flush=True)
        else:
            print(mode, files[0].parent)
    if args.check_fields:
        for mode, cid in queued.items():
            check_fields(args.archive, mode, cid, args.folder/mode, case_title=CASES[mode],
                         master_hash=MASTER[2], kind="contract_approval", reviewer="董事会决议水印核字",
                         replacement=("验收报告.pdf","实测结果","柜温8℃") if mode=="hot" else None)
            print(mode, "水印页已逐行核对", flush=True)
