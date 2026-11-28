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
        cls.review_reason = "已收到检测资料，终验质量结论以正式检测报告为准。"
        cls.pair = signed_copy(cls.limited,"QualityReview",reason=cls.review_reason)

    def paper(self, raw, role, *, version="2026.11.28.26"):
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
        rows = purposes.sources(graph,read,multiple=tuple(map(int,version.split(".")))>=purposes.MULTIPLE_SINCE)
        findings = []
        for rule,stage,refs in (("H01",None,[source]),("H02",None,[source]),("H04","第一期",[]),
                                ("H04","第二期",[source]),("H05","第二期",[source]),("H05",None,[source])):
            f = {"id":rule+"-"+str(len(findings)+1),"rule":rule,"status":"missing","detail":"演练待核","evidence":refs,"scope":["d01"]}
            if stage:
                f["stage"]={"name":stage}
            findings.append(f)
        report = {"graph":graph,"policy":{"version":version},"findings":findings}
        if rows:
            graph[purposes.KEY]=purposes.ledger(rows)
            report["policy"][purposes.KEY]=graph[purposes.KEY]["format"]
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

    def test_each_purpose_belongs_to_its_own_signed_bytes(self):
        paper,read=self.paper(self.pair,"acceptance",version="2026.11.28.28")
        first,last=paper["graph"][purposes.KEY]["rows"]
        self.assertEqual(paper["policy"][purposes.KEY],purposes.REVISION_FORMAT)
        self.assertNotEqual(first["certificate_sha256"],last["certificate_sha256"])
        for row,raw,revision,reason,coverage in ((first,self.limited,2,REASON,"ENTIRE_REVISION"),
                                                 (last,self.pair,3,self.review_reason,"ENTIRE_FILE")):
            self.assertEqual((row["id"],row["ends_at"],row["signed_sha256"],row["reason"],row["coverage"]),
                             (f"signature-purpose/d01/r{revision}",len(raw),sha256(raw).hexdigest(),reason,coverage))
            self.assertEqual(row["original_sha256"],sha256(self.pair).hexdigest())
        owner=next(f for f in paper["findings"] if f["rule"]=="H02")
        self.assertEqual((owner["status"],owner[purposes.KEY]),("risk",[first["id"],last["id"]]))
        self.assertIn("修订 2",owner["detail"])
        self.assertNotIn("修订 3",owner["detail"])
        purposes.verify(paper,read,signing=True)
        for key in ("field","certificate_sha256","signed_sha256","reason","coverage","id"):
            with self.subTest(key=key):
                changed=deepcopy(paper)
                changed["graph"][purposes.KEY]["rows"][0][key]=last[key]
                with self.assertRaisesRegex(ValueError,"签名原因"):purposes.verify(changed,read)
        changed=deepcopy(paper)
        parent=changed["graph"]["acceptance_pdf_sources"]["records"][0]
        parent["signatures"][0]["certificate_sha256"]=last["certificate_sha256"]
        with self.assertRaisesRegex(ValueError,"证书"):purposes.verify(changed,read)
        no_later_reason = signed_copy(self.limited,"QualityReview")
        partial,partial_read=self.paper(no_later_reason,"acceptance",version="2026.11.28.28")
        earlier_row,=partial["graph"][purposes.KEY]["rows"]
        self.assertEqual((earlier_row["id"],earlier_row["reason"],earlier_row["coverage"]),
                         ("signature-purpose/d01/r2",REASON,"ENTIRE_REVISION"))
        purposes.verify(partial,partial_read)
        old,read=self.paper(self.pair,"acceptance",version="2026.11.28.27")
        purposes.verify(old,read)
        with self.assertRaisesRegex(ValueError,"重新审计"):purposes.verify(old,read,signing=True)
        earlier,read=self.paper(later_copy(self.pair),"acceptance",version="2026.11.28.28")
        self.assertNotIn(purposes.KEY,earlier["graph"])
        purposes.verify(earlier,read)

    def test_download_returns_the_issued_signature_revision(self):
        from config import PERFORMANCE
        from main import create_app
        from storage import Store

        paper,_=self.paper(self.pair,"acceptance",version="2026.11.28.28")
        doc=paper["graph"]["documents"][0]
        doc.update(name="水印演练验收.pdf",size=len(self.pair))
        cid="c"*32
        with TemporaryDirectory() as temp:
            store=Store(Path(temp))
            store.create(cid,"验收签名修订",[doc],cid,cid,PERFORMANCE)
            folder=store.files/cid/doc["id"];folder.mkdir(parents=True)
            original=folder/"original.pdf";original.write_bytes(self.pair)
            client=create_app(store,None).test_client()
            path=f"/api/cases/{cid}/reports/1/documents/d01/signed-revisions/"
            with patch.object(store,"report",return_value={"report":paper}):
                for rev,raw in ((2,self.limited),(3,self.pair)):
                    response=client.get(path+str(rev))
                    self.assertEqual((response.status_code,response.data),(200,raw))
                    self.assertEqual(response.get_etag()[0],sha256(raw).hexdigest())
                self.assertEqual(client.get(path+"1").status_code,404)
                row=paper["graph"][purposes.KEY]["rows"][0]
                row["reason"]="其他签名所填的说明"
                self.assertEqual(client.get(path+"2").status_code,409)
                original.write_bytes(self.limited)
                self.assertEqual(client.get(path+"3").status_code,409)

    def test_feedback_distinguishes_two_signatures_on_the_same_finding(self):
        from config import PERFORMANCE
        from main import create_app
        from storage import Store, encode, stamp
        from uuid import uuid4

        paper,_=self.paper(self.pair,"acceptance",version="2026.11.28.28")
        doc=paper["graph"]["documents"][0]
        doc.update(name="水印演练验收.pdf",size=len(self.pair))
        cid="d"*32;paper["case_id"]=cid
        with TemporaryDirectory() as temp:
            store=Store(Path(temp));store.create(cid,"同份文件的两次签名",[doc],cid,cid,PERFORMANCE)
            payload=encode(paper)
            with store.connect(write=True) as db:
                db.execute("INSERT INTO reports VALUES(?,1,?,?,?)",(cid,stamp(),sha256(payload.encode()).hexdigest(),payload))
            client=create_app(store,None).test_client()
            def note(edition,stage="H05-5",**extra):
                where={"screen":"case","case_id":cid,"rev":1,"tab":"report","params":{"view":"payment-checks","stage":stage},
                       "anchor":"signature-purpose-"+stage+"-d01"+edition,**extra}
                return client.post("/api/walkthrough",json={"id":uuid4().hex,"text":"希望核对所签修订","context":where})
            for suffix in ("-r2","-r3"):
                self.assertEqual(note(suffix).status_code,201)
            self.assertEqual(note("").status_code,404)
            self.assertEqual(note("-r1").status_code,404)
            self.assertEqual(note("-r2","H04-3").status_code,404)
            self.assertEqual(note("-r2",doc="d01",page=1,line=2).status_code,400)
            anchors={n["context"]["anchor"] for n in client.get("/api/walkthrough").json["notes"]}
            self.assertEqual(anchors,{"signature-purpose-H05-5-d01-r2","signature-purpose-H05-5-d01-r3"})

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
