import copy
import hashlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import payment_execution as execution
from config import BANK, PERFORMANCE, CaseError
from controls import VERSION, conclusion, execute
from graph import build_graph
from payment_history import payment_record
from payment_index import install, sync_execution
from storage import Store, encode
from performance import compute, verify_findings
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material
from test_signer_clock import example as timed
from test_stage_payments import fixture as split_payment
from test_transfers import receipt_material


NOTE = "回单提示：本单仅为付款申请受理凭证，不代表实际扣款"
ARRIVAL = "回单提示：本回单不代表收款方已到账"
APP = [("other","","付款申请单"),("contract_id","合同编号","YL-121"),("payment_designation","款项用途","第二期"),
       ("other","申请状态","审批通过"),("other","申请时间","2026年9月21日 14:00")]


def sample(bank=BANK_DOC, tail=(), extra=()):
    docs = [CONTRACT,RECEIPT,WARRANTY,bank,*extra]
    graph = material(docs, omissions=[(4,s) for s in tail])
    def read(doc, page):
        i = int(doc[1:])-1
        return "\n".join([*(label+"："+value if label else value for _,label,value in docs[i]), *(tail if i==3 else [])])
    return graph, read


class ExecutionTests(unittest.TestCase):
    def test_only_application_checks_original_and_page_again_at_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp))
            image=io.BytesIO()
            Image.new("RGB",(32,45),"white").save(image,"JPEG")
            data=image.getvalue()
            sha=hashlib.sha256(data).hexdigest()
            doc={"id":"d01","name":"合成付款申请.jpg","ext":".jpg","size":len(data),"sha256":sha}
            text=[label+"："+value if label else value for _,label,value in APP]
            layer={"type":"text","clause_text_only":True,"lines":{str(i):[[.1,.1,.6,.2]] for i in range(1,len(text)+1)}}
            facts=[{"field":field,"value":value,"quote":quote,"region":"top"} for (field,_,value),quote in zip(APP,text)]
            page={"doc":"d01","number":1,"width":32,"height":45,"sha256":sha,"layer":layer,"text":"\n".join(text),
                  "extraction":{"output":{"quality":"readable","facts":facts}}}
            case="synthetic-only-request"
            store.create(case,"合成演练 · 单独申请",[doc],case,case,PERFORMANCE)
            store.put_pages(case,"d01",[page])
            folder=store.files/case/"d01"
            folder.mkdir(parents=True,exist_ok=True)
            original,preview=folder/"original.jpg",folder/"1.jpg"
            for path in (original,preview):
                path.write_bytes(data)
            graph=build_graph([doc],[page],{})
            graph["profile"]=PERFORMANCE
            findings=execute(graph,PERFORMANCE)
            rows=graph[execution.KEY]["rows"]
            geometry={str(r["line"]):layer["lines"][str(r["line"])] for r in rows if r["line"]}
            calls={"pages":[{"doc":"d01","page":1,"page_sha256":sha,"payment_execution_rects":geometry}]}
            report={"case_id":case,"graph":graph,"findings":findings,"result":conclusion(findings),
                    "policy":{**VERSION,"profile":PERFORMANCE},"calls":calls}
            store.save_report(case,report,hashlib.sha256(encode(report).encode()).hexdigest(),{})
            pinned=store.approval_sources(case,1,None)
            self.assertEqual(set(pinned[0][0].files),{original,preview})
            with store.connect(True) as db:
                store.recheck_approval(db,case,1,{},payment_sources=pinned)
            preview.write_bytes(data+b"changed")
            with self.assertRaises(CaseError),store.connect(True) as db:
                store.recheck_approval(db,case,1,{},payment_sources=pinned)
            with self.assertRaisesRegex(CaseError,"签收前核对"):
                store.approval_sources(case,1,None)

    def test_receipt_issued_before_conclusion_checks_cannot_be_newly_approved(self):
        graph,read=sample(tail=[NOTE])
        del graph[execution.KEY]
        graph["nodes"]=[n for n in graph["nodes"] if n["type"]!="payment_execution_line"]
        graph["edges"]=[e for e in graph["edges"] if e["type"]!="payment_execution_source"]
        graph["profile"]=BANK
        legacy={"case_id":"old","policy":{"version":"2026.11.23.1","profile":BANK},"graph":graph,
                "findings":[{"rule":"B05","status":"ok"}]}
        raw=encode(legacy)
        with tempfile.TemporaryDirectory() as tmp,sqlite3.connect(":memory:") as db:
            store=Store(Path(tmp))
            db.row_factory=sqlite3.Row
            db.executescript("CREATE TABLE cases(id,created); CREATE TABLE reports(case_id,rev,content,hash); CREATE TABLE pages(case_id,doc,number,text,layer);")
            db.execute("INSERT INTO cases VALUES('old','2026-11-23')")
            db.execute("INSERT INTO reports VALUES('old',1,?,?)",(raw,hashlib.sha256(raw.encode()).hexdigest()))
            db.execute("INSERT INTO pages VALUES('old','d04',1,?,'{}')",(read("d04",1),))
            with self.assertRaisesRegex(CaseError,"旧版付款材料"):
                store.recheck_approval(db,"old",1,{})

    def test_original_qualification_stops_paid_conclusion_even_if_model_omits_footer(self):
        graph, _ = sample(tail=[NOTE])
        findings = execute(graph, graph["profile"])
        payment = next(f for f in findings if f["rule"]=="H05")
        self.assertEqual((payment["status"],payment["execution_basis"]["state"],conclusion(findings)["verdict"]),("risk","conflict","review"))
        source = next(r for r in graph[execution.KEY]["rows"] if r["kind"]=="limit")
        self.assertEqual((source["line"],source["facts"],source["quote"]),(8,[],NOTE))
        self.assertIn(source["id"], payment["evidence"])
        self.assertTrue(all(f["status"]=="ok" for f in findings if f["rule"] in ("H01","H02","H03","H04")))
        other_graph, _ = sample(tail=[ARRIVAL])
        self.assertFalse(other_graph[execution.KEY]["units"])
        self.assertEqual(conclusion(execute(other_graph,other_graph["profile"]))["verdict"], "pass")

    def test_only_its_own_receipt_is_limited_and_nominal_amount_is_never_totalled(self):
        graph, _ = sample(tail=[NOTE],extra=[BANK_DOC])
        payments=[f for f in compute(graph) if f["rule"]=="H05"]
        self.assertEqual([f.get("execution_basis",{}).get("unit") for f in payments],["d04",None])
        graph=split_payment(omissions=[(5,NOTE)])
        findings=compute(graph)
        total=next(f for f in findings if f["rule"]=="H06")["stage_payments"]
        self.assertEqual((total["state"],total["seen"],total["difference"]),("unresolved",None,None))
        self.assertTrue(any("实际扣款金额" in r for r in total["reasons"]))
        g,_=timed(bank=("实际扣款时间：13:10（北京时间）",NOTE))
        f=next(f for f in compute(g) if f["rule"]=="H05")
        self.assertIn("execution_basis",f)
        self.assertNotIn("signer_timing",f)

    def test_application_without_recognized_bank_and_conditional_or_scanned_notice(self):
        g,_=sample(bank=APP)
        f=next(f for f in compute(g) if f["rule"]=="H05")
        self.assertEqual((f["status"],f["execution_basis"]["state"],f["scope"]),("missing","application",["d04"]))
        self.assertNotIn("stage",f)
        for lines in (["备注：若交易状态为受理成功，本单仅代表银行已受理申请"],["回单提示：本单不代表实际","扣款"]):
            g,_=sample(tail=lines)
            self.assertEqual(g[execution.KEY]["units"][0]["state"],"review")
        g,read=sample(tail=[NOTE])
        page=next(n for n in g["nodes"] if n["id"]=="d04/p1")
        page["clause_text_only"]=False
        self.assertEqual(execution.sources(g,read)["units"][0]["state"],"review")
        unknown,_=sample(bank=[("other","","银行付款回单"),*BANK_DOC[1:]],tail=[NOTE])
        self.assertEqual(next(f for f in compute(unknown) if f["rule"]=="H05")["status"],"missing")
        documents,pages=receipt_material(bank_photo=True,photo_note=("other",NOTE))
        g=build_graph(documents,pages,{})
        # An unlocated visual observation can trigger review, never a statement of execution.
        self.assertTrue(any(r["line"] is None for r in g[execution.KEY]["rows"] if r["kind"]=="limit"))
        self.assertNotIn("conflict",[u["state"] for u in g[execution.KEY]["units"]])
        g,_=sample(bank=[(field,label,"已受理" if label=="交易状态" else value) for field,label,value in BANK_DOC])
        self.assertNotEqual(next(f for f in compute(g) if f["rule"]=="H05")["status"],"ok")

    def test_full_payment_and_history_never_use_an_acceptance_receipt(self):
        docs,pages=receipt_material()
        bank=pages[1]
        bank["text"]+="\n"+NOTE
        bank["layer"]["lines"][str(len(bank["text"].splitlines()))]=[[0,.81,.6,.85]]
        bank["layer"]["clause_text_only"]=True
        g=build_graph(docs,pages,{})
        findings=execute(g,BANK)
        self.assertEqual({f["rule"]:f["status"] for f in findings if f["rule"] in ("B04","B05")},{"B04":"missing","B05":"risk"})
        record=payment_record(g,findings)
        self.assertIsNone(record["reference"])
        self.assertIsNone(record["settlement"])
        self.assertIsNone(record["installment"]["key"])
        report={"graph":g,"policy":{**VERSION,"profile":BANK},"findings":findings}
        read=lambda doc,page:next(p["text"] for p in pages if p["doc"]==doc and p["number"]==page)
        execution.verify(report,read)
        next(f for f in findings if f["rule"]=="B04")["status"]="ok"
        with self.assertRaisesRegex(ValueError,"差额"): execution.verify(report,read)

    def test_archived_method_and_conclusions_can_be_replayed_but_an_old_positive_cannot_be_signed(self):
        g,read=sample(tail=[NOTE])
        issued={"graph":g,"policy":{**VERSION,"profile":g["profile"]},"findings":execute(g,g["profile"])}
        execution.verify(issued,read)
        verify_findings(issued)
        for target in ("row","edge","classification","marker","finding"):
            bad=copy.deepcopy(issued)
            if target=="row": bad["graph"][execution.KEY]["rows"][-1]["quote"]="本单已扣款"
            if target=="edge": next(e for e in bad["graph"]["edges"] if e["type"]=="payment_execution_source")["from"]="d01/p1"
            if target=="classification": bad["graph"][execution.KEY]["units"][0]["state"]="application"
            if target=="marker": del bad["policy"]["payment_execution"]
            if target=="finding":
                next(f for f in bad["findings"] if f["rule"]=="H05")["execution_basis"]={}
                with self.assertRaises(ValueError): verify_findings(bad)
            else:
                with self.assertRaises(ValueError): execution.verify(bad,read)
        old=copy.deepcopy(g)
        del old[execution.KEY]
        old["nodes"]=[n for n in old["nodes"] if n["type"]!="payment_execution_line"]
        old["edges"]=[e for e in old["edges"] if e["type"]!="payment_execution_source"]
        legacy={"policy":{"version":"2026.11.26.24"},"graph":old,"findings":execute(old,old["profile"])}
        self.assertEqual(conclusion(legacy["findings"])["verdict"],"pass")
        execution.verify(legacy,read)
        with self.assertRaisesRegex(ValueError,"旧版"): execution.verify(legacy,read,signing=True)
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE pages(case_id,doc,number,text)")
            db.execute("CREATE TABLE payment_execution_holds(case_id PRIMARY KEY,rev)")
            db.execute("INSERT INTO pages VALUES('old','d04',1,?)",(read("d04",1),))
            sync_execution(db,"old",3,legacy)
            sync_execution(db,"old",3,legacy)
            self.assertEqual(db.execute("SELECT * FROM payment_execution_holds").fetchall(),[("old",3)])

    def test_rebuilt_index_excludes_only_qualified_archive_within_workspace(self):
        old, read = sample(tail=[NOTE])
        del old[execution.KEY]
        with sqlite3.connect(":memory:") as db:
            db.row_factory = sqlite3.Row
            db.executescript("""
                CREATE TABLE cases(id PRIMARY KEY, title, workspace, profile, status, rev);
                CREATE TABLE pages(case_id,doc,number,text);
                CREATE TABLE reports(case_id,rev,hash);
                CREATE TABLE signoffs(case_id,rev,decision,time);
                CREATE TABLE payment_index(case_id,rev,payer,reference,settlement,reference_eligible);
                CREATE TABLE contract_payments(case_id,rev,contract_key);
                PRAGMA user_version=9;
            """)
            for case,workspace in (("old","east"),("clean","east"),("outside","west"),("current","east")):
                db.execute("INSERT INTO cases VALUES(?,?,?,?,?,?)",(case,case,workspace,BANK,"closed",3))
                if case=="current":
                    continue
                db.execute("INSERT INTO reports VALUES(?,3,'archive')",(case,))
                db.execute("INSERT INTO signoffs VALUES(?,3,'approve','2026-11-20')",(case,))
                db.execute("INSERT INTO payment_index VALUES(?,3,'buyer','A001','full',1)",(case,))
                db.execute("INSERT INTO contract_payments VALUES(?,3,'contract')",(case,))
            install(db,new_column=False)
            self.assertIn("old", [r[0] for r in db.execute("SELECT case_id FROM payment_index_pending")])
            db.execute("INSERT INTO pages VALUES('old','d04',1,?)",(read("d04",1),))
            sync_execution(db,"old",3,{"graph":old,"policy":{}})
            for reference,kind in (("A001","same"),("B002","full")):
                signature={"payer":"buyer","reference":reference,"settlement":"full"}
                history=Store.payment_matches(db,"current",signature,"2026-11-26")
                self.assertEqual([(r["case_id"],r["kind"]) for r in history["matches"]],[("clean",kind)])
            installments=Store.installment_matches(db,"current","contract","2026-11-26")
            self.assertEqual([r["case_id"] for r in installments["matches"]],["clean"])
