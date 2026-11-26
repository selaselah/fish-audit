"""Export just the watermarked notice from a verified local evidence bundle."""
import argparse
import hashlib
import json
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from bank_execution_notices import materials, verify_case
from contract_milestones import normalize
from generate import WATERMARK

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT / "server"))
from documents import render


def digest(data):
    return hashlib.sha256(data).hexdigest()


def publish(archive, seed):
    folder, records = materials(seed, "notice")
    with ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        raw = bundle.read("report.json")
        report = json.loads(raw)
        assert report["case_id"] == manifest["case_id"] and digest(raw) == manifest["report_sha256"]
        verify_case(report, "notice")
        graph = report["graph"]
        assert {d["name"]:d["sha256"] for d in graph["documents"]} == {
            name+".pdf":digest((folder/(name+".pdf")).read_bytes()) for name in records}
        payment, = [f for f in report["findings"] if f.get("execution_basis")]
        unit = payment["execution_basis"]["unit"]
        source = folder / "银行付款回单.pdf"
        doc, = [d for d in graph["documents"] if d["id"] == unit and d["name"] == source.name]
        original = bundle.read("originals/"+unit+".pdf")
        assert original == source.read_bytes()
        text = bundle.read("pages/"+unit+"/1.txt").decode()
        assert normalize(text.splitlines()[0]) == normalize(WATERMARK)
        image = bundle.read("pages/"+unit+"/1.jpg")
        page, = [n for n in graph["nodes"] if n["id"] == unit+"/p1"]
        with tempfile.TemporaryDirectory() as tmp:
            render(source,Path(tmp),1)
            stored, = json.loads((Path(tmp)/"manifest.json").read_text())
        assert digest(image) == page["sha256"] == stored["sha256"] and stored["text"] == text
        call, = [c for c in report["calls"]["pages"] if c["doc"] == unit and c["page"] == 1]
        rev = manifest["revision"]
        slug = "payment-execution-notice"
        assets = PROJECT / "frontend/assets"
        specimen = {"title":source.stem,"version":f"合成采购 · R{rev}","page":1,"pdf":"/showcase/"+slug+".pdf",
                    "image":"/assets/"+slug+".jpg","source_sha256":doc["sha256"],"page_sha256":page["sha256"],"lines":[]}
        for row in graph["payment_execution_sources"]["rows"]:
            assert row["unit"] == row["doc"] == unit and row["page"] == 1 and row["id"] in payment["evidence"]
            n = row["line"]
            assert text.splitlines()[n-1] == row["quote"]
            rects = stored["layer"]["lines"][str(n)]
            assert rects and rects == call["payment_execution_rects"][str(n)]
            label, sep, value = row["quote"].partition("：")
            reading = {"ref":row["id"],"line":n,"kind":row["kind"],"quote":row["quote"],"label":label if sep else "单据名称",
                       "value":value if sep else label,"rect":",".join(map(str,rects[0])),"rects":rects}
            if row["kind"] in ("status","limit"):
                with Image.open(BytesIO(image)) as sheet:
                    w,h = sheet.size
                    x0=min(r[0] for r in rects)-.012
                    y0=min(r[1] for r in rects)-.006
                    x1=max(r[2] for r in rects)+.012
                    y1=max(r[3] for r in rects)+.006
                    bounds=[max(0,int(x0*w)),max(0,int(y0*h)),min(w,int(x1*w)+1),min(h,int(y1*h)+1)]
                    crop=slug+"-"+str(n)+".webp"
                    sheet.crop(bounds).save(assets/crop,lossless=True)
                    reading.update(crop="/assets/"+crop, pixels=bounds)
            specimen["lines"].append(reading)
        assert [r["kind"] for r in specimen["lines"]].count("limit")==1
        (assets/(slug+".jpg")).write_bytes(image)
        (PROJECT/"frontend/showcase"/(slug+".pdf")).write_bytes(original)
        info={"case_id":report["case_id"],"rev":rev,"report_sha256":digest(raw),"finding":payment["id"],
              "stage":payment["stage"]["name"],"state":payment["execution_basis"]["state"],"document":specimen}
        (assets/(slug+".json")).write_text(json.dumps(info,ensure_ascii=False,indent=2)+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    parser.add_argument("--run-id",required=True)
    args=parser.parse_args()
    publish(args.archive,args.run_id)
