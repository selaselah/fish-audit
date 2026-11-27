"""Verify the five pinned watermarked workpapers and publish only their acceptance or reinspection page."""

import argparse
import base64
from io import BytesIO
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.request import ProxyHandler, build_opener
from zipfile import ZipFile

from publish_batch_version import PROJECT, digest, publish, require, supports
from contract_milestones import normalize
from documents import prepare
from folio_transcription import witness
from generate import WATERMARK
from rule_replay import replay_from_git
from verify import verify


RELEASE = "2bc2f7d350a5e1dedc4547f7649c5b2277e8d7b1"
RULE = "2026.11.27.10"
PINS = {
    "clean": ("42400d4c7b5d40b8965a3a2ca69121ea", 9, "36d241603806b375d777fa8c89739529b419862cc992ec778ec423f8d1a02bdc", "word_text", "missing"),
    "limited": ("84c4fa7a1a8e4dd594a03717614ed7ef", 9, "b9191dfe18b26a71c30f4e2ff8f375aa5c2c3d01b6dde42686c4922281d1e1eb", "word_review", "risk"),
    "hot": ("8f40e32a890c4812b2e2fc5e4929b501", 9, "efe81e37df5b93d2add3aa705bd03a9fc810be997a9be0024f95b3d328f224c8", "word_review", "issue"),
    "scan": ("c3975bbf83cc45df8106e6737fdd03c6", 3, "93b2994043be18d9352f3bc41d5394127ba753ee87b0ae4ecb3ab080accd6335", "photo", "missing"),
    "retest": ("7b2a051771474808a2d782d473cd6729", 3, "2a33b0f0a0b72a8aed9188391f810866340bcfdc2f30f4b6a741c14b60dab170", "word_text", "issue"),
}
INDEX = "assets/acceptance-original-samples.json"
SHARED = "assets/acceptance-review-page.jpg"
FIELDS = ("acceptance_result", "measured_result", "acceptance_signer", "defect_closure")


def line_from_page(fact, page, call):
    loc = fact["source_line"]
    number = loc["number"]
    quote = page["text"].splitlines()[number-1]
    rects = page["layer"]["lines"][str(number)]
    require(fact["status"] in ("anchored", "confirmed") and loc["text"] == quote and loc["rects"] == rects
            and rects and all(0 <= l < r <= 1 and 0 <= t < b <= 1 for l,t,r,b in rects), "物理原行及其引文位置")
    compact = quote
    if compact != fact["quote"]:
        require(fact["field"] == "measured_result" and re.fullmatch(r"实测结果[：:]柜温 -?[0-9]+(?:\.[0-9]+)?(?:℃|°C)",quote)
                and witness(fact, call), "实测栏排印空格及核图来源")
        compact = quote.replace("柜温 ", "柜温")
    require(compact == fact["quote"] and compact.partition("：")[2] == fact["value"], "本案原行字样与取值")
    label, _, value = quote.partition("：")
    left,top,right,bottom = zip(*rects)
    return dict(ref=fact["id"],field=fact["field"],label=label,value=value,quote=quote,line=number,page=1,
                rect=[min(left),min(top),max(right),max(bottom)],rects=rects)


def edition(key, folder):
    case, rev, expected, state, status = PINS[key]
    if folder:
        archive = folder / f"{key}-R{rev}.zip"
    else:
        with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:8000/api/cases/{case}/reports/{rev}/bundle", timeout=120) as r:
            archive = BytesIO(r.read())
    require(verify(archive, render_addenda=True)[:2] == (case, rev), key+" 固定版本")
    with ZipFile(archive) as bundle:
        content = bundle.read("report.json")
        report, journal = json.loads(content),json.loads(bundle.read("journal.json"))
        require(digest(content) == expected == json.loads(bundle.read("manifest.json"))["report_sha256"] and
                journal["id"] == report["case_id"] == case and journal["title"].startswith("合成演练 · ")
                and not journal["decisions"] and not journal["referrals"] and report["policy"]["version"] == RULE, "水印案件及归档摘要")
        graph = report["graph"]
        record, = graph["acceptance_original_sources"]["records"]
        doc, = [d for d in graph["documents"] if d["id"] == record["doc"]]
        unit = doc["id"]
        physical, = record["pages"]
        find, = [f for f in report["findings"] if f["rule"] == "H02"]
        require(record["state"] == state and doc["pages"] == 1 and unit == record["unit"] and unit in find["scope"]
                and physical["ref"] == unit+"/p1" and find["status"] == status and find["acceptance_originals"] == [record["id"]], "验收单归属")
        original = bundle.read("originals/"+unit+doc["ext"])
        image = bundle.read("pages/"+unit+"/1.jpg")
        require(digest(original) == doc["sha256"] == record["original_sha256"] and digest(image) == physical["sha256"], "提交原件与页图")
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / ("source"+doc["ext"]);path.write_bytes(original)
            page, = prepare(path, 1, save_images=False)
        require(page["sha256"] == physical["sha256"] and page["text"].encode() == bundle.read("pages/"+unit+"/1.txt"), "原件独立重绘")
    replay = replay_from_git(report, ref=RELEASE, repo=PROJECT, pinned=RELEASE)
    require(replay["state"] == "verified" and replay["commit"] == RELEASE, "签发程序复算")
    links = {(e["from"],e["to"]) for e in graph["edges"] if e["type"] == "supports_result" and e["evidence"] == [e["from"]]}
    supports(find,[record["id"],unit,physical["ref"],*record["fields"],*record["notes"]],links)
    call, = [c for c in report["calls"]["pages"] if c["doc"] == unit and c["page"] == 1]
    require(call["page_sha256"] == physical["sha256"] and call["response_id"] and call["check"]["response_id"], "读页与复检")
    facts = [f for f in graph["facts"] if f["doc"] == unit and f["id"] in find["evidence"] and f["field"] in FIELDS]
    lines, notes = [], []
    if key == "scan":
        require(page["layer"]["type"] == "image" and not page["text"] and not any(f.get("source_line") for f in facts)
                and not record["review"] and original == (PROJECT/"frontend"/SHARED).read_bytes(), "同一验收打印页的扫描演练")
    else:
        require(normalize(WATERMARK) in normalize(page["text"].splitlines()[0]) and doc["ext"] == ".docx", "水印 Word")
        for f in facts:
            supports(find,[f["id"]],links)
            require(f["source_sha256"] == doc["sha256"] and f["page_sha256"] == page["sha256"], "字段归属")
            lines.append(line_from_page(f,page,call))
        lines.sort(key=lambda row:row["line"])
        require([row["field"] for row in lines] == list(FIELDS if key == "retest" else FIELDS[:3]), "可定位的验收栏")
        word, = graph["acceptance_word_reviews"]["documents"]
        require(record["review"] == word["id"] and word["coverage"] == "complete" and not record["unplaced"], "原生 Word 审阅层")
        notes = word["notes"]
        require([n["id"] for n in notes] == record["notes"] and len(notes) == int(key in ("limited","hot")), "批注数")
        if notes:
            note, = notes
            require(not note["shortened"] and note["anchor"]["selected"] == "合格" and note["location"]["facts"] == [lines[0]["ref"]]
                    and note["location"]["page_sha256"] == page["sha256"] and note["location"]["line"] == lines[0]["line"], "批注与结论栏")
    if key == "retest":
        require(find["reinspection"]["state"] == "open" and any(s["unit"] == unit and s["role"] == "final" for s in find["reinspection"]["steps"]), "缺陷仍待关闭")
    original_path = SHARED if key == "scan" else ("showcase/acceptance-review.docx" if key == "limited" else "showcase/acceptance-original-"+key+".docx")
    image_path = SHARED if key in ("clean","limited") else "assets/acceptance-original-"+key+".jpg"
    assets = {original_path:original,image_path:image}
    source = dict(id=unit,title=Path(doc["name"]).stem,name=doc["name"],page=1,media=record["kind"],version=f"合成案例 · R{rev}",
                  source_sha256=doc["sha256"],page_sha256=physical["sha256"],original="/"+original_path,image="/"+image_path,lines=lines)
    return dict(key=key,case_id=case,rev=rev,report_sha256=expected,id=record["id"],state=state,status=status,doc=source,notes=notes),assets


def build(folder):
    editions, files = [], {}
    for key in PINS:
        sample, assets = edition(key,folder)
        for name, raw in assets.items():
            require(name not in files or files[name] == raw, "共享归档页逐字节一致")
            files[name] = raw
        editions.append(sample)
    files[INDEX] = (json.dumps({"rule_version":RULE,"editions":editions},ensure_ascii=False,indent=2)+"\n").encode()
    return files


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--archives",type=Path)
    args.add_argument("--check",action="store_true")
    options = args.parse_args()
    files = build(options.archives)
    publish(files,PROJECT/"frontend",options.check)
    print(INDEX,"sha256-"+base64.b64encode(bytes.fromhex(digest(files[INDEX]))).decode())
