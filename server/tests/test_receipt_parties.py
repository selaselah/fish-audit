from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from config import CaseError, PERFORMANCE
from controls import VERSION, execute
from graph import build_graph, link_procedures
from model import FIELDS
import receipt_parties as roles
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


def example(changes, *, correct=(), extra=(), banks=1):
    cid="a"*32
    calls, texts, layouts = {},{},{}
    def build(docs,pages,decisions):
        edits=[]
        for doc,p in zip(docs,pages):
            doc.update(ext=".pdf",pages=1,sha256=sha256(doc["id"].encode()).hexdigest())
            unit=doc["id"]
            p["sha256"]=sha256(p["text"].encode()).hexdigest()
            trace=p["extraction"]
            trace.update(model="fixture",response_id="read-"+unit)
            check={"model":"fixture","response_id":"check-"+unit,"input":[],"output":{"checks":[]}}
            trace["check"]=check
            for i,f in enumerate(trace["output"]["facts"],1):
                expected=f["field"]
                if expected in changes and unit=="d04":
                    f["field"]=changes[expected]
                    if expected in correct:
                        ref=f"{unit}/p1/f{i}"
                        checkup={"format":"field-source-v1","case_id":cid,"rev":2,"report_hash":"c"*64,"operation":"correct",
                                 "doc":unit,"page":1,"page_sha256":p["sha256"],"original_sha256":doc["sha256"]}
                        edits.append({**f,"field":expected,"target":ref,"doc":unit,"page":1,"page_hash":p["sha256"],"source_check":checkup,"rev":2})
                        decisions[ref]={"decision":"confirm","fact":ref,"source_check":checkup,"rev":2}
                check["input"].append({"index":str(i),"field":FIELDS[f["field"]],"value":f["value"],"quote":f["quote"]})
                check["output"]["checks"].append({"index":str(i),"support":"clear"})
            calls[unit,1]={"doc":unit,"page":1,"page_sha256":p["sha256"],**trace}
            texts[unit,1],layouts[unit,1]=p["text"],p["layer"]
        return build_graph(docs,pages,decisions,edits)
    with patch("test_performance.build_graph",build):
        graph=material([CONTRACT,RECEIPT,WARRANTY,*[BANK_DOC]*banks],omissions=extra)
    findings=execute(graph,PERFORMANCE)
    rows=graph.get(roles.KEY,{}).get("rows",[])
    procedures=[]
    for f in findings:
        if cited:=roles.cited(f,rows):
            p={k:deepcopy(f[k]) for k in ("rule","status","evidence","stage") if k in f}
            procedures.append({**p,"observation":f["detail"],roles.KEY:deepcopy(cited)})
    archive={"pages":list(calls.values()),"expert":{"model":"fixture","response_id":"review","input":{"procedures":procedures}}}
    link_procedures(graph,findings,archive)
    policy={**VERSION,"profile":PERFORMANCE}
    if rows:
        policy[roles.KEY]=roles.FORMAT
    paper={"case_id":cid,"policy":policy,"graph":graph,"calls":archive,"findings":findings}
    return paper,lambda doc,n:texts[doc,n],lambda doc,n:layouts[doc,n]


class ReceiptPartyTests(unittest.TestCase):
    def test_pending_payer_original_is_guarded_until_the_signature_is_written(self):
        from jobs import Worker
        from storage import Store
        from test_acceptance_execution import printed

        original_graph = material([CONTRACT, RECEIPT, WARRANTY, BANK_DOC])
        def extract(path):
            unit = path.parent.name
            facts = [{k:f[k] for k in ("field","value","quote","region")}
                     for f in original_graph["facts"] if f["doc"]==unit]
            for fact in facts:
                if fact["field"]=="payer":
                    fact["field"]="buyer"
            output = {"quality":"readable","facts":facts}
            inputs = [{"index":str(i),"field":FIELDS[f["field"]],"quote":f["quote"],"value":f["value"]}
                      for i,f in enumerate(facts,1)]
            check = {"model":"fixture","response_id":"check-"+unit,"input":inputs,
                     "output":{"checks":[{"index":i["index"],"support":"clear"} for i in inputs]}}
            return output, {"model":"fixture","response_id":"read-"+unit,"output":output,"check":check}

        with TemporaryDirectory() as temp:
            store = Store(Path(temp))
            case_id = "c"*32
            docs = []
            for doc in original_graph["documents"]:
                unit = doc["id"]
                raw = printed(original_graph,unit)
                folder = store.files/case_id/unit
                folder.mkdir(parents=True)
                (folder/"original.pdf").write_bytes(raw)
                docs.append({"id":unit,"name":doc["name"]+".pdf","ext":".pdf","size":len(raw),"sha256":sha256(raw).hexdigest()})
            store.create(case_id,"合成户名核对",docs,case_id,case_id,PERFORMANCE)
            expert = {"followups":[]}
            with patch("model.structured",return_value=(expert,{"model":"fixture","response_id":"expert","output":expert})):
                Worker(store,extract).run(store.claim())
            report = store.report(case_id,1)["report"]
            [row] = report["graph"][roles.KEY]["rows"]
            self.assertEqual((row["state"],row["printed_role"]),("pending","payer"))
            source = store.files/case_id/row["doc"]/"original.pdf"
            pinned = store.approval_sources(case_id,1,None)
            self.assertIn(source,pinned[0][0].files)
            with store.connect(True) as db:
                store.recheck_approval(db,case_id,1,{},payment_sources=pinned)
            source.write_bytes(source.read_bytes()+b"\n% changed after preflight")
            with self.assertRaises(CaseError),store.connect(True) as db:
                store.recheck_approval(db,case_id,1,{},payment_sources=pinned)

    def test_model_roles_do_not_assign_an_installment_until_the_originals_are_corrected(self):
        for current,expected_stage in [((),"pending"),(("payer","payee"),"corrected")]:
            paper,read,layout=example({"payer":"payee","payee":"payer"},correct=current,banks=2)
            ledger=paper["graph"][roles.KEY]["rows"]
            self.assertEqual([(r["printed_role"],r["model_role"],r["state"]) for r in ledger],
                             [("payer","payee",expected_stage),("payee","payer",expected_stage)])
            affected,other=[f for f in paper["findings"] if f["rule"]=="H05"]
            self.assertEqual(affected[roles.KEY],[r["id"] for r in ledger])
            self.assertNotIn(roles.KEY,other)
            if current:
                self.assertEqual(affected["stage"]["name"],"第二期")
            else:
                self.assertNotIn("stage",affected)
                self.assertEqual(affected["status"],"missing")
            roles.verify(paper,read,layout)

    def test_partial_review_still_holds_and_requires_a_single_printed_row(self):
        paper,_,_=example({"payer":"buyer","payee":"seller"},correct=("payer",))
        self.assertEqual([r["state"] for r in paper["graph"][roles.KEY]["rows"]],["corrected","pending"])
        self.assertNotIn("stage",next(f for f in paper["findings"] if f["rule"]=="H05"))
        for changes, extra in (({},()),({"payer":"buyer"},((4,"付款户名：另一演练单位"),))):
            paper,read,layout=example(changes,extra=extra)
            self.assertNotIn(roles.KEY,paper["graph"]); roles.verify(paper,read,layout)

    def test_issued_classification_requires_the_same_original_readings_graph_and_expert_basis(self):
        paper,read,layout=example({"payer":"buyer"},correct=("payer",))
        row,=paper["graph"][roles.KEY]["rows"]
        def bank(p):
            return next(c for c in p["calls"]["pages"] if c["doc"]==row["doc"])
        def fact(p):
            return next(f for f in p["graph"]["facts"] if f["id"]==row["fact"])
        mutations=[
            lambda p:bank(p)["check"].update(response_id=bank(p)["response_id"]),
            lambda p:bank(p).update(page_sha256="0"*64),
            lambda p:p["graph"].update(edges=[e for e in p["graph"]["edges"] if
                     not (e["from"]==row["id"] and e["type"]=="supports_result")]),
            lambda p:fact(p)["amendment"]["source_check"].update(case_id="b"*32),
            lambda p:p["calls"]["expert"]["input"].update(procedures=[]),
            lambda p:p["policy"].pop(roles.KEY),
        ]
        for mutation in mutations:
            altered=deepcopy(paper);mutation(altered)
            with self.assertRaises(ValueError):
                roles.verify(altered,read,layout)
        with self.assertRaises(ValueError):
            roles.verify(paper,lambda d,n:read(d,n)+"改",layout)
        with self.assertRaises(ValueError):
            roles.verify(paper,read,lambda d,n:{"lines":{}})
