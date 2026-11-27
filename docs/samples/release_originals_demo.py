"""Make four fictional approval slips from one published, watermarked procurement packet."""

import argparse
import json
import re
from pathlib import Path
from zipfile import ZipFile

from docx import Document

from contract_milestones import normalize
from generate import WATERMARK
from publish_batch_version import digest, require
from pdf_signing import later_copy, signed_copy
from run import get, post, submit, wait
from word_percentage import save_document, word_file


MASTER = ("5ded713a74244105a171a77fb0a51557", 6, "ae37a4cb130ff6fcc165acd0c0acafa2db07c59117dd879acb09888266694122")
TITLE = "付款放行单"
COMMENT = "本单为待签草稿，须经财务负责人会签后执行。"
CASES = {"current": "放行单 · 测试签名覆盖本版", "earlier": "放行单 · 签后另存新版",
         "comment": "放行单 · Word 草稿会签批注", "scan": "放行单 · 扫描签认栏"}


def materials(archive, target, *, master=MASTER, title=TITLE, decision=("放行决定","解除第二期验收款暂缓"),
              comment=COMMENT, signature_field="SyntheticRelease"):
    case, rev, expected = master
    with ZipFile(archive) as package:
        content = package.read("report.json")
        manifest, journal = (json.loads(package.read(k+".json")) for k in ("manifest","journal"))
        report = json.loads(content)
        require(manifest["revision"] == rev and digest(content) == manifest["report_sha256"] == expected
                and report["case_id"] == journal["id"] == case and journal["title"].startswith("合成演练 · ")
                and not journal["decisions"] and not journal["referrals"], f"虚构采购的已签发 R{rev}")
        documents = {}
        for doc in report["graph"]["documents"]:
            unit = doc["id"]
            lines = package.read(f"pages/{unit}/1.txt").decode().splitlines()
            raw = package.read(f"originals/{unit}.pdf")
            require(doc["ext"] == ".pdf" and doc["pages"] == 1 and lines[0] == WATERMARK
                    and digest(raw) == doc["sha256"], "原件和水印")
            if doc["name"] == title+".pdf":
                require(lines[1] == title, title+"标题")
                rows = [line.split("：",1) for line in lines[2:]]
                image = package.read(f"pages/{unit}/1.jpg")
                page, = [n for n in report["graph"]["nodes"] if n["id"] == unit+"/p1"]
                require(digest(image) == page["sha256"] and all(len(row) == 2 for row in rows), "原件页图与字段")
            documents[doc["name"]] = raw
    signed = signed_copy(documents[title+".pdf"], signature_field)
    carriers = {"current": (".pdf",signed), "earlier": (".pdf",later_copy(signed)), "scan": (".jpg",image)}
    groups = {}
    for key in CASES:
        folder = target/key
        folder.mkdir(parents=True,exist_ok=True)
        files = []
        for name, data in documents.items():
            path = folder/name
            if name == title+".pdf" and key == "comment":
                path = path.with_suffix(".docx")
                word_file(path,rows,title)
                word = Document(path)
                paragraph, = [p for p in word.paragraphs if p.text.startswith(decision[0]+"：")]
                left, right = paragraph.text.split(decision[1])
                paragraph.clear()
                paragraph.add_run(left)
                selected = paragraph.add_run(decision[1])
                paragraph.add_run(right)
                word.add_comment(selected,comment,author="演练财务复核员",initials="CW")
                save_document(word,path)
            else:
                if name == title+".pdf":
                    ext,data = carriers[key]
                    path = path.with_suffix(ext)
                path.write_bytes(data)
            files.append(path)
        groups[key] = files
    return report["policy"]["profile"], groups


def check_fields(archive, key, case, folder, *, case_title=None, master_hash=MASTER[2], kind="payment_release", reviewer="水印放行单演练", replacement=None, addition=None, visual_fields=(), missing_fields=()):
    """Reconcile visible sample fields against the fixed, previously reviewed originals."""
    from config import PERFORMANCE
    from documents import prepare
    api = "/api/cases/" + case
    detail = get(api)
    files = {p.name:p for p in folder.iterdir() if p.is_file()}
    require(detail["title"] == "合成演练 · " + (case_title or CASES[key]) and detail["profile"] == PERFORMANCE
            and not detail["decisions"] and not detail["referrals"]
            and {d["name"]:d["sha256"] for d in detail["documents"]} == {n:digest(p.read_bytes()) for n,p in files.items()},
            "本次水印资料及原件摘要")
    with ZipFile(archive) as bundle:
        content = bundle.read("report.json")
        require(digest(content) == master_hash, "已核对的虚构母本")
        master = json.loads(content)["graph"]
        report = wait(case)
        confirm = []
        for base in master["documents"]:
            name = base["name"]
            doc, = [d for d in detail["documents"] if Path(d["name"]).stem == Path(name).stem]
            path = files[doc["name"]]
            page, = prepare(path,1,save_images=False)
            archived_lines = bundle.read(f"pages/{base['id']}/1.txt").decode().splitlines()
            old_row = new_row = None
            printed_fields = [f for f in master["facts"] if f["doc"] == base["id"]]
            if replacement and name==replacement[0]:
                label, value = replacement[1:]
                position, = [i for i,r in enumerate(archived_lines) if r.startswith(label+"：")]
                new_row = page["text"].splitlines()[position]
                require(normalize(new_row)==normalize(label+"："+value) and re.findall(r"[0-9]+",new_row)==re.findall(r"[0-9]+",value),
                        "新水印样本的原行、日期及数字分组")
                old_row, archived_lines[position] = archived_lines[position], new_row
            if addition and name==addition[0]:
                _, field, label, value, region = addition
                last = page["text"].splitlines()[-1]
                require(last == label+"："+value and not any(r.startswith(label+"：") for r in archived_lines), "新增水印原行")
                archived_lines.append(last)
                if field:
                    printed_fields.append({"field":field,"quote":last,"value":value,"region":region,"status":"anchored"})
            require(archived_lines[0] == WATERMARK and next(n for n in report["graph"]["nodes"]
                    if n["id"] == doc["id"]+"/p1")["sha256"] == page["sha256"], "物理页及水印")
            if path.suffix == ".jpg":
                require(path.read_bytes() == bundle.read(f"pages/{base['id']}/1.jpg"), "母本扫描页")
            else:
                require(list(map(normalize, page["text"].splitlines())) == list(map(normalize, archived_lines)),
                        "载体变更后的全部打印行")
            for source in printed_fields:
                if source["quote"] == old_row:
                    source = {**source,"quote":new_row,"value":new_row.partition("：")[2]}
                quote = source["quote"]
                if quote not in archived_lines:
                    continue
                observed = [f for f in report["graph"]["facts"] if f["doc"] == doc["id"]
                            and f["page"] == 1 and normalize(f["quote"]) == normalize(quote)]
                same = [f for f in observed if f["field"] == source["field"]
                        and normalize(f["value"]) == normalize(source["value"])]
                added = addition and name==addition[0] and quote==last
                printed_missing = source["field"] in missing_fields and archived_lines.count(quote)==1 and page["text"].splitlines().count(quote)==1
                if not same and (len(observed) == 1 or not observed and (source["field"] == kind or added or printed_missing)):
                    post(api+"/amend", {"rev":get(api)["rev"], "reviewer":reviewer, "doc":doc["id"], "page":1,
                         "target":observed[0]["id"] if observed else None, "field":source["field"], "value":source["value"],
                         "quote":quote, "region":source["region"], "note":"对照水印原件的同一可见行，补正字段类别或抄录。"})
                    report = wait(case)
                    same = [f for f in report["graph"]["facts"] if f["doc"] == doc["id"] and f["field"] == source["field"]
                            and normalize(f["quote"]) == normalize(quote) and normalize(f["value"]) == normalize(source["value"])]
                physical = (source["field"] in visual_fields and page["text"].splitlines().count(quote)==1 and len(same)==1
                            and same[0]["quote"]==quote and same[0]["value"]==source["value"]
                            and same[0].get("source_line",{}).get("text")==quote and same[0]["source_line"].get("rects"))
                if len(same) == 1 and same[0]["status"] in ("anchored","visual") and (source["status"] == "confirmed"
                        or same[0]["status"] == "visual" and (source["field"] == kind or physical)):
                    confirm.append(same[0]["id"])
        if confirm:
            post(api+"/attest", {"rev":get(api)["rev"], "reviewer":reviewer, "decision":"confirm", "facts":confirm,
                 "note":"已对照同一份水印原件逐行核字。签署行为、人员身份及权限仍交人工复核。"})
            wait(case)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    parser.add_argument("folder",type=Path)
    parser.add_argument("--run",action="store_true",help="通过本机接口上传水印材料并调用模型")
    parser.add_argument("--check-fields",action="store_true",help="逐页对照水印母本，演练字段复核")
    options = parser.parse_args()
    profile, cases = materials(options.archive,options.folder)
    for key, paths in cases.items():
        if options.run:
            token = digest("".join(digest(p.read_bytes()) for p in paths).encode())
            case = submit("合成演练 · "+CASES[key],paths,"release-proof-"+token,profile)
            print(key,case,flush=True)
            if options.check_fields:
                check_fields(options.archive,key,case,options.folder/key)
        else:
            print(key,*(p.name for p in paths))
