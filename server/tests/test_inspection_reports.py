from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

import config
from documents import render
import inspection_reports as inspection
from pdf_execution import inspect_original
import signature_purposes as purposes
from test_pdf_execution import signed_copy


REASON = "终验质量结论以正式检测报告（编号：JC-2026-018）为准。"


def sheet(title, *lines, graphic=False):
    data = BytesIO()
    c = canvas.Canvas(data, invariant=True)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c.setFont("STSong-Light",16)
    for i, line in enumerate(("虚构演练", title, *lines)):
        c.drawString(45, 795-i*40, line)
    if graphic:
        c.circle(260,480,13)
    c.save()
    return data.getvalue()


class InspectionReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signed = signed_copy(sheet("验收报告","合同编号：HT-100"),"QualityReview",reason=REASON)
        cls.documents = {"receipt": cls.signed}
        for name, number, contract in (("matched","JC-2026-018","HT-100"), ("different","JC-2026-081","HT-100"),
                                       ("other_contract","JC-2026-018","HT-101")):
            cls.documents[name] = sheet("检测报告","报告编号："+number,"合同编号："+contract,"检测结论：仅送检样品合格")
        cls.documents["graphic"] = sheet("检测报告","报告编号：JC-2026-018","合同编号：HT-100",graphic=True)
        cls.documents["renamed"] = sheet("随附清单","所引文件：检测报告","报告编号：JC-2026-018")
        cls.pages = {}
        import json
        with TemporaryDirectory() as folder:
            for name, raw in cls.documents.items():
                path = Path(folder) / (name+".pdf")
                path.write_bytes(raw)
                render(path,Path(folder),1)
                cls.pages[name], = json.loads((Path(folder)/"manifest.json").read_text())

    def paper(self, attachments, *, value="HT-100", version=config.RULE_VERSION):
        graph = {"documents":[], "facts":[], "documents_by_kind":{"acceptance":["d01"]}, "nodes":[], "edges":[]}
        originals = {}
        for i, name in enumerate(("receipt", *attachments),1):
            doc, page = f"d{i:02d}", self.pages[name]
            originals[doc] = raw = self.documents[name]
            digest = sha256(raw).hexdigest()
            graph["documents"].append({"id":doc,"ext":".pdf","name":"检测报告.pdf","sha256":digest,"pages":1,"size":len(raw)})
            graph["nodes"].append({"type":"page","id":doc+"/p1","sha256":page["sha256"],
                                   "text_sha256":sha256(page["text"].encode()).hexdigest(),
                                   "layer":page["layer"]["type"],"clause_text_only":page["layer"]["clause_text_only"]})
        origin = graph["documents"][0]
        state, signatures = inspect_original(self.signed)
        parent = "acceptance-pdf/d01"
        graph["acceptance_pdf_sources"] = {"records":[{"id":parent,"doc":"d01","unit":"d01","state":state,
            "signatures":signatures,"original_sha256":origin["sha256"]}]}
        graph["facts"] = [{"id":"d01/p1/f1","field":"contract_id","doc":"d01","page":1,"status":"anchored",
                           "source_sha256":origin["sha256"],"value":value,"quote":"合同编号：HT-100",
                           "source_line":{"number":3,"text":"合同编号：HT-100","rects":self.pages["receipt"]["layer"]["lines"]["3"]}}]
        read = lambda d: originals[d["id"]]
        rows = purposes.sources(graph,read)
        if tuple(map(int,version.split("."))) >= purposes.REFERENCE_SINCE:
            inspection.attach(graph,rows,read)
        graph[purposes.KEY] = purposes.ledger(rows)
        policy = {"version":version, purposes.KEY:graph[purposes.KEY]["format"],
                  "code_sha256":{"signature_purposes.py":"a"*64,"inspection_reports.py":"b"*64}}
        nodes, edges = purposes.source_graph(rows)
        graph["nodes"].extend(nodes)
        graph["edges"].extend(edges)
        findings = []
        for i, (rule, depends) in enumerate((("H01",False),("H02",True),("H04",False),("H05",True)),1):
            f = {"id":f"{rule}-{i}","rule":rule,"scope":["d01"],"status":"ok","detail":"演练核对",
                 "evidence":[parent] if depends else []}
            if rule in ("H04","H05"):
                f["stage"]={"name":"第二期" if depends else "第一期"}
            findings.append(f)
        purposes.apply(graph,findings)
        procedures = []
        for f in findings:
            graph["edges"].extend({"type":"supports_result","from":r,"to":"finding/"+f["id"],"evidence":[r]} for r in f["evidence"])
            if purposes.KEY in f:
                procedures.append({**{k:f[k] for k in ("rule","stage","status","evidence") if k in f},
                                   "observation":f["detail"],purposes.KEY:deepcopy(rows)})
        return {"policy":policy, "graph":graph, "findings":findings,
                "calls":{"expert":{"response_id":"exercise","input":{"procedures":procedures}}}}, read

    def test_number_contract_and_original_scope(self):
        for files, expected in (([], "unlocated"), (["renamed","graphic"], "unlocated"), (["different"], "different"),
                                (["matched"], "matched"), (["other_contract"], "other_contract"), (["matched","matched"], "multiple")):
            with self.subTest(files=files):
                paper, read = self.paper(files)
                purposes.verify(paper,read,signing=True)
                row, = paper["graph"][purposes.KEY]["rows"]
                ref = row["report_reference"]
                self.assertEqual(ref["state"],expected)
                self.assertEqual(ref["signed_contract"]["fact"],"d01/p1/f1")
                self.assertEqual([f["rule"] for f in paper["findings"] if ref["id"] in f["evidence"]],["H02","H05"])
                self.assertEqual([f["status"] for f in paper["findings"]][::2],["ok","ok"])
                self.assertTrue(all(f["status"]!="ok" for f in paper["findings"] if purposes.KEY in f))
                if expected=="matched":
                    original, = ref["candidates"]
                    self.assertEqual(original["conclusion"]["quote"],"检测结论：仅送检样品合格")
                    self.assertEqual(original["number"]["rects"],self.pages["matched"]["layer"]["lines"]["3"])
        moved, read = self.paper(["matched"], value="HT-999")
        purposes.verify(moved,read)
        self.assertEqual(moved["graph"][purposes.KEY]["rows"][0]["report_reference"]["state"],"uncertain")

    def test_ambiguity_and_explicit_reference(self):
        for reason in ("无需检测报告","终验质量结论不以正式检测报告为准。",REASON+"该项已撤回。"):
            self.assertIsNone(inspection.requirement({"role":"acceptance","reason":reason}))
        self.assertIsNone(inspection.requirement({"role":"contract","reason":REASON}))
        self.assertEqual(inspection.requirement({"role":"reinspection","reason":REASON.replace("JC-2026-018","018***")}),("检测报告",None))
        self.assertEqual(inspection.requirement({"role":"acceptance","reason":"已收到检测资料，终验质量结论以正式检测报告为准。"}),("检测报告",None))
        for lines in (["报告编号：JC-018","报告编号：JC-019"], ["报告编号：JC-018","报告编号说明：仅显示后三位"]):
            self.assertIsNone(inspection.one_field(lines,{"报告编号"},identifier=True))

    def test_legacy_and_modified_evidence(self):
        prior,read = self.paper(["different"],version="2026.11.28.28")
        purposes.verify(prior,read)
        with self.assertRaisesRegex(ValueError,"重新审计"):
            purposes.verify(prior,read,signing=True)
        current,read = self.paper(["matched"])
        for target in ("page","edges","scope","expert","status","geometry"):
            paper = deepcopy(current)
            ref = paper["graph"][purposes.KEY]["rows"][0]["report_reference"]
            if target=="page":
                paper["graph"]["nodes"][1]["text_sha256"]="c"*64
            elif target=="edges":
                paper["graph"]["edges"]=[e for e in paper["graph"]["edges"] if e["type"]!="inspection_attachment_page"]
            elif target=="scope":
                paper["findings"][0]["evidence"].append(ref["id"])
            elif target=="expert":
                paper["calls"]["expert"]["input"]["procedures"][0][purposes.KEY][0].pop("report_reference")
            elif target=="status":
                ref["state"]="different"
            else:
                ref["candidates"][0]["number"]["rects"]=[]
            with self.subTest(target=target), self.assertRaises(ValueError):
                purposes.verify(paper,read)
        with self.assertRaisesRegex(ValueError,"提交件摘要"):
            purposes.verify(current,lambda doc: self.documents["different"] if doc["id"]=="d02" else read(doc))
