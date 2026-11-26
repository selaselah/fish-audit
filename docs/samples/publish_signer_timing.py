"""Publish the three original pages from the verified watermarked 'before' exercise."""

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile

from PIL import Image
from acceptance_signers import generate
from contract_milestones import normalize
from generate import WATERMARK


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "server"))
from documents import render


def publish(archive, seed):
    folder, records = generate(seed, "before")
    with ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        raw = bundle.read("report.json")
        report = json.loads(raw)
        digest = hashlib.sha256(raw).hexdigest()
        assert manifest["case_id"] == report["case_id"] and digest == manifest["report_sha256"]
        rev = manifest["revision"]
        graph = report["graph"]
        finding, = [f for f in report["findings"] if f.get("signer_timing")]
        timing = finding["signer_timing"]
        assert (timing["state"], timing["days"], timing["format"]) == ("before", -3, "named-acceptance-signatures-v4")
        assert {d["name"]: d["sha256"] for d in graph["documents"]} == {
            title+".pdf": hashlib.sha256((folder/(title+".pdf")).read_bytes()).hexdigest() for title in records}
        facts = {f["id"]: f for f in graph["facts"]}
        nodes = {n["id"]: n for n in graph["nodes"]}
        dates = {r["id"]: r for r in graph["acceptance_authority_sources"]["dates"]}
        rows = [dates[i] for i in timing["rows"]]
        def field(doc, name, label=None):
            fact, = [f for f in facts.values() if f["doc"] == doc and f["field"] == name
                     and (not label or f["quote"].startswith(label+"："))]
            return fact["id"]
        preview_refs = {timing["paid_ref"], *timing["rows"]}
        def page(doc, slug, selection):
            item = next(d for d in graph["documents"] if d["id"] == doc)
            source = folder/item["name"]
            assert bundle.read("originals/"+doc+".pdf") == source.read_bytes()
            text = bundle.read("pages/"+doc+"/1.txt").decode()
            assert normalize(text.splitlines()[0]) == normalize(WATERMARK)
            image = bundle.read("pages/"+doc+"/1.jpg")
            image_digest = hashlib.sha256(image).hexdigest()
            with tempfile.TemporaryDirectory() as tmp:
                render(source, Path(tmp), 1)
                stored, = json.loads((Path(tmp)/"manifest.json").read_text())
            assert stored["text"] == text and stored["sha256"] == nodes[doc+"/p1"]["sha256"] == image_digest
            lines = []
            for ref in selection:
                obj = dates.get(ref) or facts[ref]
                line = obj["line"] if ref in dates else obj["source_line"]["number"]
                quote = text.splitlines()[line-1]
                assert obj["doc"] == doc and obj["page"] == 1 and quote == obj["quote"]
                rects = stored["layer"]["lines"][str(line)]
                label, value = quote.split("：",1)
                lines.append({"ref":ref, "line":line, "label":label, "value":value, "quote":quote,
                              "rects":rects, "rect":",".join(map(str,rects[0]))})
                if ref in preview_refs:
                    with Image.open(BytesIO(image)) as sheet:
                        w,h = sheet.size
                        left = max(0, int((min(r[0] for r in rects)-.012)*w))
                        top = max(0, int((min(r[1] for r in rects)-.006)*h))
                        right = min(w, int((max(r[2] for r in rects)+.012)*w)+1)
                        bottom = min(h, int((max(r[3] for r in rects)+.006)*h)+1)
                        crop = f"{slug}-l{line}.webp"
                        sheet.crop((left,top,right,bottom)).save(PROJECT/"frontend/assets"/crop,lossless=True)
                        lines[-1]["crop"] = "/assets/"+crop
            (PROJECT/"frontend/showcase"/(slug+".pdf")).write_bytes(source.read_bytes())
            (PROJECT/"frontend/assets"/(slug+".jpg")).write_bytes(image)
            return {"title":source.stem,"version":f"合成采购 · R{rev}","page":1,"pdf":"/showcase/"+slug+".pdf",
                    "image":"/assets/"+slug+".jpg","source_sha256":item["sha256"],"page_sha256":image_digest,"lines":lines}
        bank, receipt = timing["bank"], timing["receipt"]
        contract, = graph["documents_by_kind"]["contract"]
        pages = [
            page(contract,"joint-signing-contract",[timing["clause_ref"],timing["stage_ref"],field(contract,"contract_id")]),
            page(bank,"joint-signing-transfer",[timing["paid_ref"],field(bank,"payment_designation"),field(bank,"transfer_amount")]),
            page(receipt,"joint-signing-acceptance",[field(receipt,"accepted_on","验收日期"), *timing["rows"]])]
        events = [{"label":r["name"]+"签认","kind":"signer","day":r["day"],"ref":r["id"]} for r in rows]
        events.append({"label":"回单付款","kind":"payment","day":timing["paid_on"],"ref":timing["paid_ref"]})
        data = {"case_id":report["case_id"],"rev":rev,"report_sha256":digest,"documents":pages,
                "payment":{"key":finding["id"],"stage":finding["stage"]["name"],"state":timing["state"],"days":timing["days"],
                           "clause":timing["clause_ref"],"term":timing["stage_ref"],"events":events}}
        (PROJECT/"frontend/assets/joint-signing.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--seed", required=True)
    args = parser.parse_args()
    publish(args.archive, args.seed)
