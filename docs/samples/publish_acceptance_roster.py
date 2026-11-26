"""Publish the original lines from the watermarked, fixed R5 signer comparison."""

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

REPORT_SHA = "a6b00b153a04a724839699588df670c755397026217058b0e67d4cb351c4e9eb"
SEED = "synthetic-acceptance-signatures-20261124-27"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def publish(archive):
    output = {}
    with ZipFile(archive) as bundle:
        raw = bundle.read("report.json")
        manifest = json.loads(bundle.read("manifest.json"))
        if digest(raw) != REPORT_SHA or manifest["report_sha256"] != REPORT_SHA or manifest["revision"] != 5:
            raise ValueError("公开样本须使用指定水印演练的 R5 证据包")
        report = json.loads(raw)
        graph = report["graph"]
        folder, generated = generate(SEED, "different")
        assert {d["name"]:d["sha256"] for d in graph["documents"]} == {
            title+".pdf":digest((folder/(title+".pdf")).read_bytes()) for title in generated}
        item, = [f for f in report["findings"] if f["rule"] == "H02"]
        entry = item["acceptance_authority"]
        record, = entry["records"]
        clause, = entry["clause_evidence"]
        signed = [{"name":s["name"], "confirmed":s["confirmed"], "ref":s["fact"]} for s in record["signed"]]
        assert item["status"] == record["status"] == "risk" and record["other_names"] == ["何平"]
        assert entry["required"] == ["周宁","林岚"] and record["missing_names"] == ["林岚"]
        facts = {f["id"]:f for f in graph["facts"]}
        nodes = {n["id"]:n for n in graph["nodes"]}
        edges = {(e["type"],e["from"],e["to"],tuple(e["evidence"])) for e in graph["edges"]}

        def supports(finding, ref):
            return ref in finding["evidence"] and ("supports_result",ref,"finding/"+finding["id"],(ref,)) in edges

        primary = [clause, *(s["ref"] for s in signed)]
        assert all(supports(item, ref) for ref in primary)
        phases = [{"name":f["stage"]["name"], "status":f["status"], "ref":f["stage"]["clause_ref"]}
                  for f in report["findings"] if f["rule"] == "H04" and
                  all(supports(f, ref) for ref in [*primary,f["stage"]["clause_ref"]])]
        assert [p["name"] for p in phases] == ["第二期","第三期"]
        documents = []
        for doc_id, suffix, refs in [(facts[clause]["doc"],"contract",[clause, *(p["ref"] for p in phases)]),
                                     (record["unit"],"receipt",[s["ref"] for s in signed])]:
            doc, = [d for d in graph["documents"] if d["id"] == doc_id]
            path = folder/doc["name"]
            original = bundle.read(f"originals/{doc_id}.pdf")
            page = bundle.read(f"pages/{doc_id}/1.jpg")
            text = bundle.read(f"pages/{doc_id}/1.txt").decode()
            assert original == path.read_bytes() and normalize(text.splitlines()[0]) == normalize(WATERMARK)
            with tempfile.TemporaryDirectory() as tmp:
                render(path, Path(tmp), 1)
                physical, = json.loads((Path(tmp)/"manifest.json").read_text())
            page_id = doc_id+"/p1"
            assert text == physical["text"] and digest(page) == physical["sha256"] == nodes[page_id]["sha256"]
            slug = "acceptance-roster-"+suffix
            output["showcase/"+slug+".pdf"] = original
            output["assets/"+slug+".jpg"] = page
            with Image.open(BytesIO(page)) as sheet:
                sheet.thumbnail((128,256),Image.Resampling.LANCZOS)
                small = BytesIO()
                sheet.save(small,format="WEBP",quality=85)
                output["assets/"+slug+"-thumb.webp"] = small.getvalue()
            lines = []
            for ref in refs:
                fact = facts[ref]
                loc = fact["source_line"]
                n = loc["number"]
                rects = physical["layer"]["lines"][str(n)]
                assert (fact["doc"],fact["page"],fact["source_sha256"],fact["page_sha256"]) == (doc_id,1,digest(original),digest(page))
                assert ("records",page_id,ref,(ref,)) in edges and loc["rects"] == rects
                assert fact["quote"] == loc["text"] == text.splitlines()[n-1]
                label, value = fact["quote"].split("：",1)
                row = {"ref":ref,"line":n,"label":label,"value":value,"quote":fact["quote"],"rects":rects}
                if ref in primary:
                    with Image.open(BytesIO(page)) as sheet:
                        width, height = sheet.size
                        bounds = (max(0,int((min(r[0] for r in rects)-.012)*width)),
                                  max(0,int((min(r[1] for r in rects)-.006)*height)),
                                  min(width,int((max(r[2] for r in rects)+.012)*width)+1),
                                  min(height,int((max(r[3] for r in rects)+.006)*height)+1))
                        buffer = BytesIO()
                        sheet.crop(bounds).save(buffer, format="WEBP", lossless=True)
                        crop = f"assets/{slug}-{n}.webp"
                        output[crop] = buffer.getvalue()
                        row["crop"] = "/"+crop
                lines.append(row)
            documents.append({"title":path.stem,"version":"合成采购 · R5","page":1,"pdf":"/showcase/"+slug+".pdf",
                              "image":"/assets/"+slug+".jpg","thumb":"/assets/"+slug+"-thumb.webp",
                              "lines":lines,"source_sha256":digest(original),"page_sha256":digest(page)})
        roster = {"mode":entry["mode"],"required":entry["required"],"contract":clause,"records":[
            {"unit":record["unit"],"role":record["role"],"file":next(d["name"] for d in graph["documents"] if d["id"] == record["unit"]),
             "status":record["status"],"detail":record["detail"],"signed":signed,"phases":phases}]}
        data = {"rev":5,"case_id":report["case_id"],"report_sha256":REPORT_SHA,"documents":documents,"roster":roster}
        output["assets/acceptance-roster.json"] = (json.dumps(data,ensure_ascii=False,indent=2)+"\n").encode()
    for path, content in output.items():
        (PROJECT/"frontend"/path).write_bytes(content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    publish(parser.parse_args().archive)
