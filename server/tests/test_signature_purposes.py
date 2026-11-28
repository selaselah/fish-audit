from copy import deepcopy
from hashlib import sha256
import unittest

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
