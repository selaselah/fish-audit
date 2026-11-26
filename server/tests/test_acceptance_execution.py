import copy
from hashlib import sha256
from io import BytesIO
import unittest

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

import acceptance_execution as execution
from controls import VERSION
from performance import compute
from test_delivery_batches import sample as batches
from test_pdf_execution import signed_copy, later_copy
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material
from test_reinspection import graph as repairs


def printed(graph, unit, *, mark=False):
    out = BytesIO()
    sheet = canvas.Canvas(out,pagesize=(595,842),pageCompression=0,invariant=True)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    sheet.setFont("STSong-Light",11)
    for i, row in enumerate(f for f in graph["facts"] if f["doc"]==unit):
        sheet.drawString(48,790-i*21,row["quote"])
    if mark:
        sheet.circle(220,425,20)
    sheet.save()
    return out.getvalue()


def paper(graph, files):
    for doc in graph["documents"]:
        if doc["id"] in files:
            doc.update(ext=".pdf",pages=1,sha256=sha256(files[doc["id"]]).hexdigest())
            next(n for n in graph["nodes"] if n["id"]==doc["id"])["sha256"] = doc["sha256"]
            for f in graph["facts"]:
                if f["doc"]==doc["id"]:
                    f["source_sha256"] = doc["sha256"]
    read = lambda d:files[d["id"]]
    source = execution.sources(graph,read)
    graph["acceptance_pdf_sources"] = source
    nodes, edges = execution.source_graph(source)
    graph["nodes"].extend(nodes)
    graph["edges"].extend(edges)
    return {"policy":VERSION,"graph":graph,"findings":compute(graph)}, read


def by_rule(report, rule):
    return [f for f in report["findings"] if f["rule"]==rule]


class AcceptanceExecutionTests(unittest.TestCase):
    def base(self):
        return material([CONTRACT,RECEIPT,WARRANTY,BANK_DOC])

    def test_transcription_has_no_independent_execution_evidence(self):
        graph = self.base()
        report,read = paper(graph,{"d02":printed(graph,"d02")})
        execution.verify(report,read,signing=True)
        r, = graph["acceptance_pdf_sources"]["records"]
        self.assertEqual((r["state"],r["pages"][0]["ref"]),("typeset","d02/p1"))
        acceptance, = by_rule(report,"H02")
        self.assertEqual(acceptance["status"],"missing")
        self.assertIn("排印",acceptance["detail"])
        self.assertTrue({r["id"],"d02/p1",*r["fields"]}<=set(acceptance["evidence"]))
        first, second, last = by_rule(report,"H04")
        self.assertEqual(first["status"],"ok")
        self.assertNotIn(r["id"],first["evidence"])
        for affected in (second,last,*by_rule(report,"H05")):
            self.assertNotEqual(affected["status"],"ok")
            self.assertIn(r["id"],affected["evidence"])
        changed = copy.deepcopy(report)
        changed["graph"]["acceptance_pdf_sources"]["records"][0]["state"] = "current"
        with self.assertRaises(ValueError):
            execution.verify(changed,read)
        with self.assertRaisesRegex(ValueError,"入库摘要"):
            execution.verify(report,lambda d:read(d)+b"changed",signing=True)

    def test_scan_graphics_and_signature_integrity_require_separate_review(self):
        source = printed(self.base(),"d02")
        signed = signed_copy(source)
        needle = b"/Producer (ReportLab"
        self.assertIn(needle,signed)
        changed = signed.replace(needle,b"/Producer (ReporXLab",1)
        for raw,state,status in [(printed(self.base(),"d02",mark=True),"visual","missing"),(signed,"current","missing"),
                                 (later_copy(signed),"earlier","missing"),(changed,"mismatch","risk"),(b"bad","review","missing")]:
            with self.subTest(state=state):
                report,read = paper(self.base(),{"d02":raw})
                self.assertEqual(report["graph"]["acceptance_pdf_sources"]["records"][0]["state"],state)
                self.assertEqual(by_rule(report,"H02")[0]["status"],status)
                execution.verify(report,read)

    def test_original_defect_and_separate_batch_survive(self):
        graph = repairs()
        report,_ = paper(graph,{"d04":printed(graph,"d04")})
        finding, = by_rule(report,"H02")
        self.assertEqual((finding["status"],finding["reinspection"]["state"]),("issue","open"))
        self.assertIn("不合格",finding["detail"])
        self.assertIn("acceptance-pdf/d04",finding["evidence"])
        graph = batches()
        unit = graph["documents_by_kind"]["acceptance"][1]
        report,_ = paper(graph,{unit:printed(graph,unit)})
        first, second, third, last = by_rule(report,"H04")
        self.assertEqual((first["status"],second["status"]),("ok","ok"))
        proof = "acceptance-pdf/"+unit
        self.assertNotIn(proof,second["evidence"])
        for f in (third,last):
            self.assertNotEqual(f["status"],"ok")
            self.assertIn(proof,f["evidence"])

    def test_legacy_issued_result_is_readable_and_positive_signoff_requires_rerun(self):
        graph = self.base()
        raw = printed(graph,"d02")
        graph["documents"][1].update(ext=".pdf",pages=1,sha256=sha256(raw).hexdigest())
        graph.pop("acceptance_pdf_sources")
        policy = {**VERSION,"version":"2026.11.26.26"}
        policy.pop("acceptance_pdf")
        report = {"policy":policy,"graph":graph,"findings":compute(graph)}
        execution.verify(report,lambda d:raw)
        with self.assertRaisesRegex(ValueError,"重审"):
            execution.verify(report,lambda d:raw,signing=True)
        report["findings"] = by_rule(report,"H04")[:1]
        execution.verify(report,lambda d:raw,signing=True)
        with self.assertRaisesRegex(ValueError,"缺少"):
            execution.verify({**report,"policy":{**policy,"version":"2026.11.26.27"}},lambda d:raw)

    def test_partitioned_pdf_keeps_each_acceptance_pages_and_fields(self):
        out = BytesIO()
        sheet = canvas.Canvas(out,invariant=True)
        sheet.drawString(40,500,"Synthetic acceptance A")
        sheet.showPage()
        sheet.drawString(40,500,"Synthetic acceptance B")
        sheet.circle(100,500,18)
        sheet.save()
        raw = out.getvalue()
        doc = {"id":"d01","ext":".pdf","pages":2,"sha256":sha256(raw).hexdigest()}
        graph = {"documents":[doc],"audit_documents":[],"documents_by_kind":{"acceptance":[]}, "nodes":[],"facts":[]}
        for number in (1,2):
            ref = "d01/p"+str(number)
            unit = "unit/"+ref
            graph["audit_documents"].append({"id":unit,"source":"d01","page":number})
            graph["documents_by_kind"]["acceptance"].append(unit)
            graph["nodes"].append({"type":"page","id":ref,"sha256":"page"+str(number)})
            graph["facts"].append({"id":ref+"/f1","unit":unit,"doc":"d01","page":number,"field":"acceptance_signer"})
        first,second = execution.sources(graph,lambda d:raw)["records"]
        self.assertEqual((first["state"],second["state"]),("typeset","visual"))
        for index, record in enumerate((first,second),1):
            ref = "d01/p"+str(index)
            self.assertEqual(([p["ref"] for p in record["pages"]],record["fields"]),([ref],[ref+"/f1"]))
