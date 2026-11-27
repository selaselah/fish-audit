"""Publish five pinned, watermarked release reviews with their cited physical pages."""

import argparse
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import ProxyHandler, build_opener
from zipfile import ZipFile

from config import PERFORMANCE
from documents import prepare
from generate import WATERMARK
from publish_batch_version import PROJECT, digest, publish, require, supports
from rule_replay import replay_from_git
from verify import verify


COMMIT = "b801906a8d91d2f6ea97eccc2de0705e1cedcf38"
RULE = "2026.11.27.11"
INDEX = "assets/release-examples.json"
PINS = {
    "late": ("2bf163a2b272462d9e535e6f1d3e25fe", 9, "47ab853299d9b82fdb17b74154f51cadacfa1ef57cbe63706817b5f4447305b7", "typeset"),
    "current": ("048b4638bed4493b8d8bbbf5435db836", 6, "64ad93abe06585cdf9b3c3b45ef6d97b10a1227fb9f6a4e801c2c6e9388d8507", "current"),
    "earlier": ("dfad83fbd0a84c5180b1c5b70564425a", 5, "cb15e378f8996ece13b83cb57660d3e77227d3f2486e7e71f65d633d113664a8", "earlier"),
    "comment": ("5e244752f2ec40378100499f4214263a", 6, "1838f91cd383cef7bd35c6939595aa36685ce0bffac809d85525a9a70f092985", "word_review"),
    "scan": ("4c35692e8b554723b5abf085d8ef8e94", 6, "7c8b69784730be7b998026015f886e7ebcfebd2aed6e748be6476ca89fa0f711", "photo"),
}


def edition(key, path, files):
    case, revision, expected, state = PINS[key]
    require(verify(path, render_addenda=True)[:2] == (case, revision), "离线完整核验")
    with ZipFile(path) as z:
        raw = z.read("report.json")
        paper, journal = json.loads(raw), json.loads(z.read("journal.json"))
        require(digest(raw) == expected and paper["case_id"] == journal["id"] == case and journal["title"].startswith("合成演练 · ")
                and not journal["decisions"] and not journal["referrals"] and paper["policy"]["profile"] == PERFORMANCE
                and paper["policy"]["version"] == RULE, "固定水印底稿")
        require(replay_from_git(paper, ref=COMMIT, repo=PROJECT, pinned=COMMIT)["commit"] == COMMIT, "同版规则复算")
        graph = paper["graph"]
        links = {(e["from"],e["to"]) for e in graph["edges"] if e["type"]=="supports_result" and e["evidence"]==[e["from"]]}
        stage, = [f for f in paper["findings"] if f["rule"]=="H04" and f.get("payment_opinion",{}).get("release")]
        release = stage["payment_opinion"]["release"]
        record, = graph["release_pdf_sources"]["records"] + graph["release_original_sources"]["records"]
        require(record["state"] == state and stage["status"]=="missing" and release["signature_records"]==[record["id"]]
                and release["state"] in ("scope_pending","signature_pending"), "放行单、期次和核验状态")
        supports(stage, [record["id"],record["doc"],*record["fields"],*(p["ref"] for p in record["pages"])], links)
        banks = [f for f in paper["findings"] if f["rule"]=="H05" and f.get("stage",{}).get("clause_ref")==stage["stage"]["clause_ref"]
                 and record["id"] in f.get("payment_opinion",{}).get("release",{}).get("signature_records",())]
        require(len(banks)<=1, "本演练的一笔已关联回单")
        bank = banks[0] if banks else None
        at_bank = bank["payment_opinion"]["release"] if bank else {}
        facts = {f["id"]:f for f in graph["facts"]}
        docs, pages, rows = {}, {}, {}

        def add_doc(unit):
            if unit in docs:
                return docs[unit]
            source, = [d for d in graph["documents"] if d["id"]==unit]
            require(source["pages"]==1 and source["ext"] in (".pdf",".docx",".jpg"), "单页演练原件")
            original = z.read("originals/"+unit+source["ext"])
            jpg = z.read(f"pages/{unit}/1.jpg")
            with TemporaryDirectory() as tmp:
                file = Path(tmp)/("original"+source["ext"])
                file.write_bytes(original)
                page, = prepare(file,1,save_images=False)
            physical, = [n for n in graph["nodes"] if n["id"]==unit+"/p1"]
            require(digest(original)==source["sha256"] and digest(jpg)==physical["sha256"]==page["sha256"], "原件和生成页一致")
            if source["ext"]==".jpg":
                require(key=="scan" and unit==record["doc"] and digest(original)==
                        "b426133b3726204697549c381b1d0ef3352048a5fc78cef449593699cb4b26c9", "指定带水印母本的扫描页")
            else:
                require(page["text"].splitlines()[0]==WATERMARK, "可读演练水印")
            original_name = "showcase/release-"+digest(original)[:14]+source["ext"]
            image_name = "assets/release-"+digest(jpg)[:14]+".jpg"
            files[original_name],files[image_name] = original,jpg
            pages[unit] = page
            doc = {"id":unit,"name":source["name"],"title":Path(source["name"]).stem,"page":1,"version":"合成演练 · R"+str(revision),
                   "media":{".pdf":"pdf",".docx":"word",".jpg":"image"}[source["ext"]],"image":"/"+image_name,
                   "page_sha256":digest(jpg),"source_sha256":source["sha256"],"size":source["size"],"lines":[],
                   "pdf" if source["ext"]==".pdf" else "original":"/"+original_name}
            docs[unit] = doc
            return doc

        def add_row(name,label,finding,unit,number,quote,value,refs):
            owner = stage["payment_opinion"] if name=="hold" else release if finding is stage else at_bank
            page_ref = unit+"/p1"
            require(all(ref in owner["evidence"] for ref in refs), "放行核对所用引文")
            supports(finding,refs,links)
            if page_ref in owner["evidence"]:
                supports(finding,[page_ref],links)
            else:
                require(refs and all(any(e["from"]==page_ref and e["to"]==ref and e["type"]=="records"
                            and e["evidence"]==[ref] for e in graph["edges"]) for ref in refs), "所引字段对应的物理页")
            doc = add_doc(unit)
            require(all(facts[ref]["doc"]==unit and facts[ref]["page"]==1 and facts[ref]["page_sha256"]==doc["page_sha256"]
                        and facts[ref]["source_sha256"]==doc["source_sha256"] for ref in refs), "字段来源摘要")
            row = {"doc":unit,"ref":None,"value":value,"line":number}
            if number is not None:
                page = pages[unit]
                require(number>=1 and page["text"].splitlines()[number-1]==quote, "原页行文")
                rects = page["layer"]["lines"][str(number)]
                require(rects and all(0<=x<r<=1 and 0<=y<b<=1 for x,y,r,b in rects), "原页框选位置")
                row["ref"]=unit+"/p1/l"+str(number)
                if not any(l["ref"]==row["ref"] for l in doc["lines"]):
                    doc["lines"].append({"ref":row["ref"],"label":label,"value":quote,"line":number,"rects":rects})
            rows[name]=row

        title = add_doc(record["doc"])
        for name,role,label in (("authority","authority","合同授权"),("date","date","所列签字日")):
            entries = [s for s in release["sources"] if s["role"]==role and s["line"]]
            if entries:
                s, = entries
                value = release["required"] if role=="authority" else s["quote"].partition("：")[2]
                require(value and value in s["quote"], "栏内取值")
                add_row(name,label,stage,s["doc"],s["line"],s["quote"],value,s["facts"])
        signer, = (facts[f] for f in record["fields"])
        require(signer["status"]=="confirmed" and signer["attestation"]["source_check"] and signer["doc"]==record["doc"], "合成签认栏核字回执")
        loc = signer.get("source_line") or {}
        require(loc.get("number") or title["media"]=="image", "签认栏原行或整张扫描")
        add_row("signer","签认栏",stage,signer["doc"],loc.get("number"),signer["quote"],signer["value"],[signer["id"]])
        note, = stage["payment_opinion"]["notes"]
        supports(stage,[note["doc"]+"/p1",*note["facts"]],links)
        # The hold is sourced by the opinion, outside its nested release.
        require(note["stance"]=="hold" and note["index"]==2 and stage["stage"]["name"]=="第二期", "验收单暂缓原文及期次")
        add_row("hold","验收单意见",stage,note["doc"],note["line"],note["quote"],note["quote"],note["facts"])
        if bank and at_bank.get("paid_ref"):
            paid = facts[at_bank["paid_ref"]]
            add_row("paid","回单付款日",bank,paid["doc"],paid["source_line"]["number"],paid["quote"],paid["value"],[paid["id"]])
        notes = []
        for word in graph["release_original_sources"]["documents"]:
            for n in word["notes"]:
                require(n["id"] in record["notes"] and n["location"] and not n["shortened"], "放行单批注对应原文")
                supports(stage,[word["id"],n["id"]],links)
                loc=n["location"]
                add_row("annotation","批注锚点",stage,record["doc"],loc["line"],n["anchor"]["quote"],n["anchor"]["selected"],loc["facts"])
                notes.append({"text":n["text"],"author":n["author"],"anchor":n["anchor"]["selected"]})
        timing=at_bank.get("written_timing")
        if key=="late":
            require(timing=="before" and bank["status"]=="risk" and at_bank["timing"]=="unknown", "银行付款早于单上日期")
        return {"key":key,"rev":revision,"report_sha256":expected,"stage":stage["id"],"status":release["state"],"record":record,
                "docs":docs,"rows":rows,"notes":notes,"timing":timing,"dates":{"paid":at_bank.get("paid_on"),"signed":at_bank.get("signed_on")},
                "bank_status":bank["status"] if bank else None}


def build(archives):
    files = {}
    entries = []
    for key,(case,rev,_,_) in PINS.items():
        with TemporaryDirectory() as tmp:
            path = (archives or Path(tmp))/f"{key}-R{rev}.zip"
            if not archives:
                url=f"http://127.0.0.1:8000/api/cases/{case}/reports/{rev}/bundle"
                with build_opener(ProxyHandler({})).open(url, timeout=90) as result:
                    path.write_bytes(result.read())
            entries.append(edition(key,path,files))
    files[INDEX]=(json.dumps({"rule":RULE,"editions":entries},ensure_ascii=False,indent=2)+"\n").encode()
    return files


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives",type=Path)
    parser.add_argument("--check",action="store_true")
    opts=parser.parse_args()
    files=build(opts.archives)
    publish(files,PROJECT/"frontend",opts.check)
    print(INDEX,"sha256-"+base64.b64encode(bytes.fromhex(digest(files[INDEX]))).decode())
