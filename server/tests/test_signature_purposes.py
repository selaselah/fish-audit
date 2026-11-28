from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import signature_purposes as purposes
from pdf_execution import inspect_original
from test_acceptance_execution import printed
from test_pdf_execution import later_copy, signed_copy
from test_performance import CONTRACT, RECEIPT, material


REASON = "仅确认到货数量，实际供货单位及终验质量仍待核对。"


class SignaturePurposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.surface = printed(material([CONTRACT,RECEIPT]),"d01")
        cls.limited = signed_copy(cls.surface,reason=REASON)
        cls.neutral = signed_copy(cls.surface,reason="并非仅确认到货数量")

    def paper(self, raw, role):
        digest = sha256(raw).hexdigest()
        state,sigs = inspect_original(raw)
        doc = {"id":"d01","ext":".pdf","sha256":digest}
        source = ("pdf-execution/" if role=="contract" else "acceptance-pdf/")+"d01"
        proof = {"id":source,"doc":"d01","unit":"d01","state":state,"signatures":sigs,"original_sha256":digest}
        graph = {"documents":[doc],"documents_by_kind":{role:["d01"]},"nodes":[],"edges":[]}
        if role=="contract":
            graph["pdf_execution_sources"]={"documents":[proof]}
        else:
            graph["acceptance_pdf_sources"]={"records":[proof]}
        read = lambda doc:raw
        rows = purposes.sources(graph,read)
        findings = []
        for rule,stage,refs in (("H01",None,[source]),("H02",None,[source]),("H04","第一期",[]),
                                ("H04","第二期",[source]),("H05","第二期",[source]),("H05",None,[source])):
            f = {"id":rule+"-"+str(len(findings)+1),"rule":rule,"status":"missing","detail":"演练待核","evidence":refs,"scope":["d01"]}
            if stage:
                f["stage"]={"name":stage}
            findings.append(f)
        report = {"graph":graph,"policy":{"version":"2026.11.28.26"},"findings":findings}
        if rows:
            graph[purposes.KEY]={"format":purposes.FORMAT,"rows":rows}
            report["policy"][purposes.KEY]=purposes.FORMAT
            graph["nodes"],graph["edges"]=purposes.source_graph(rows)
        purposes.apply(graph,findings)
        procedures=[]
        for f in findings:
            graph["edges"].extend({"from":ref,"to":"finding/"+f["id"],"type":"supports_result","evidence":[ref]} for ref in f["evidence"])
            if f.get(purposes.KEY):
                proc={k:f[k] for k in ("rule","stage","evidence","status") if k in f}
                procedures.append({**proc,"observation":f["detail"],purposes.KEY:deepcopy(rows)})
        report["calls"]={"expert":{"response_id":"fixture","input":{"procedures":procedures}}}
        return report,read

    def test_contract_and_receipt_have_distinct_owners_and_relevant_stages(self):
        for role,owner in (("contract","H01"),("acceptance","H02"),("reinspection","H02")):
            report,read=self.paper(self.limited,role)
            row,=report["graph"][purposes.KEY]["rows"]
            self.assertEqual((row["reason"],row["role"],row["scope"]),(REASON,role,"quantity_only"))
            used=[f for f in report["findings"] if purposes.KEY in f]
            self.assertEqual([(f["rule"],f["status"]) for f in used],[(owner,"risk"),("H04","missing"),("H05","missing")])
            purposes.verify(report,read)
            envelope=deepcopy(report)
            envelope["calls"]["expert"]["input"]["procedures"].append({purposes.KEY:[row]})
            with self.assertRaises(ValueError):purposes.verify(envelope,read)
            with self.assertRaises(ValueError):purposes.verify(report,lambda doc:self.neutral)

    def test_unrelated_words_earlier_editions_and_combined_filings(self):
        report,read=self.paper(self.neutral,"acceptance")
        self.assertEqual(report["graph"][purposes.KEY]["rows"][0]["scope"],"as_stated")
        self.assertTrue(all(f["status"]=="missing" for f in report["findings"]))
        purposes.verify(report,read)
        report["graph"]["audit_documents"]=[{"source":"d01","id":"unit/d01/p1"},{"source":"d01","id":"unit/d01/p2"}]
        self.assertFalse(purposes.sources(report["graph"],read))
        for raw in (later_copy(self.limited),self.surface,signed_copy(self.surface),signed_copy(self.surface,reason="仅确认到货数量"+"。" * 520)):
            report,read=self.paper(raw,"contract")
            self.assertNotIn(purposes.KEY,report["graph"])
            purposes.verify(report,read)

    def test_prior_edition_replays_but_unreviewed_scope_requires_reissue_at_signoff(self):
        for raw,hold in ((self.limited,True),(self.neutral,False)):
            report,read=self.paper(raw,"contract")
            graph=report["graph"]
            graph.pop(purposes.KEY)
            graph["nodes"]=[]; graph["edges"]=[]
            report["policy"]={"version":"2026.11.28.25"}
            report["findings"]=[{"id":"H01-2","rule":"H01","status":"missing","scope":["d01"],"evidence":["pdf-execution/d01"]}]
            report.pop("calls")
            purposes.verify(report,read)
            if hold:
                with self.assertRaisesRegex(ValueError,"重新审计"):purposes.verify(report,read,signing=True)
            else:
                purposes.verify(report,read,signing=True)

    def test_replay_compares_scope_to_the_signed_file_before_returning_a_receipt(self):
        from config import PERFORMANCE
        from main import create_app
        from storage import Store

        paper,_=self.paper(self.limited,"contract")
        doc=paper["graph"]["documents"][0]
        doc.update(name="演练合同.pdf",size=len(self.limited))
        cid="a"*32
        with TemporaryDirectory() as temp:
            store=Store(Path(temp))
            store.create(cid,"签名范围复算",[doc],cid,cid,PERFORMANCE)
            folder=store.files/cid/doc["id"]
            folder.mkdir(parents=True)
            client=create_app(store,None).test_client()
            archive={"report":paper,"sha256":"0"*64}
            with patch.object(store,"report",return_value=archive),patch("main.replay_from_git") as rules:
                path=f"/api/cases/{cid}/reports/1/replay"
                self.assertEqual(client.post(path,json={}).json["state"],"unavailable")
                (folder/"original.pdf").write_bytes(self.limited)
                paper["graph"].pop(purposes.KEY)
                result=client.post(path,json={}).json
                self.assertEqual(result["state"],"mismatch")
                self.assertIn("签名原因",result["message"])
                rules.assert_not_called()

    def test_worker_checks_the_signed_contract_before_issuing_a_report(self):
        from config import PERFORMANCE
        from graph import build_graph
        from jobs import Worker
        from model import FIELDS
        from storage import Store

        template=material([CONTRACT,RECEIPT])
        original=next(d for d in template["documents"] if d["id"]=="d01")
        doc={**original,"name":"水印测试合同.pdf","ext":".pdf","size":len(self.limited),"sha256":sha256(self.limited).hexdigest()}
        facts=[{k:f[k] for k in ("field","quote","value","region")} for f in template["facts"] if f["doc"]==doc["id"]]
        def extract(path):
            result={"quality":"readable","facts":facts}
            inputs=[{"index":str(i),"field":FIELDS[f["field"]],"quote":f["quote"],"value":f["value"]} for i,f in enumerate(facts,1)]
            check={"model":"fixture","response_id":"check","input":inputs,"output":{"checks":[{"index":i["index"],"support":"clear"} for i in inputs]}}
            return result,{"model":"fixture","response_id":"read","output":result,"check":check}
        def incomplete_graph(*args,**kwargs):
            graph=build_graph(*args,**kwargs)
            graph.pop(purposes.KEY,None)
            graph["nodes"]=[n for n in graph["nodes"] if n["type"]!="pdf_signature_purpose"]
            graph["edges"]=[e for e in graph["edges"] if e["type"]!="declares_signature_purpose"]
            return graph
        for omit in (True,False):
            with self.subTest(omit=omit),TemporaryDirectory() as temp:
                store=Store(Path(temp)); cid="b"*32
                folder=store.files/cid/doc["id"];folder.mkdir(parents=True)
                (folder/"original.pdf").write_bytes(self.limited)
                store.create(cid,"签署范围演练",[doc],cid,cid,PERFORMANCE)
                response={"followups":[]}
                with patch("jobs.build_graph",incomplete_graph if omit else build_graph),patch("model.structured",return_value=(
                        response,{"model":"fixture","response_id":"expert","output":response})):
                    worker=Worker(store,extract)
                    if omit:
                        with self.assertRaisesRegex(ValueError,"签名原因"):worker.run(store.claim())
                        self.assertEqual(store.detail(cid)["rev"],0)
                    else:
                        worker.run(store.claim())
                        paper=store.report(cid,1)["report"]
                        signer=next(f for f in paper["findings"] if f["rule"]=="H01")
                        self.assertEqual((signer["status"],signer[purposes.KEY]),("risk",["signature-purpose/d01"]))
