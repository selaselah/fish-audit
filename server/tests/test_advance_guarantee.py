import copy
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

import advance_guarantee as guarantee
from config import CaseError, PERFORMANCE
from contract_folios import line_numbers
from controls import VERSION, conclusion, execute
from graph import link_procedures
from performance import verify_findings
from storage import Store, encode
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


RIDER = "预付款支付前提：采购方收到本合同项下的预付款保函后方可支付第一期预付款"
EXPLICIT = RIDER.replace("收到", "收到以采购方为受益人的")
INLINE = "合同生效且采购方收到本合同项下的预付款保函后支付30%"
LETTER = ("预付款保函", "合同编号：YL-121", "保函编号：BH-12", "受益人：演练甲", "开立日期：2026年9月2日")
ACK = ("预付款保函签收单", "合同编号：YL-121", "签收保函编号：BH-12", "签收单位：演练甲", "签收日期：2026年9月12日")
BANK = [(f, l, "第一期付款" if f=="payment_designation" else v) for f,l,v in BANK_DOC]


def specimen(*, rider=RIDER, inline=None, letter=LETTER, receipt=ACK, bank=BANK, extras=(), omitted=(), pages=()):
    contract = [(f,l,inline if inline and l=="第一期" else v) for f,l,v in CONTRACT]
    groups = [contract, RECEIPT, WARRANTY, bank]
    tails = [(1,rider)] if rider else []
    for source in (letter,receipt):
        if source:
            groups.append([("other","",source[0])])
            tails.extend((len(groups),line) for line in source[1:])
    groups.extend(extras)
    tails.extend(omitted)
    graph = material(groups,omissions=tails,extra_pages=pages)
    texts = {(f"d{i:02d}",1):"\n".join([*(l+"："+v if l else v for _,l,v in g),*(s for d,s in tails if d==i)])
             for i,g in enumerate(groups,1)}
    texts.update({(p["doc"],p["number"]):p["text"] for p in pages})
    return graph, texts


def layout(text):
    return {"type":"text","clause_text_only":True,"lines":{str(i):[[0,.1,.9,.2]] for i,_ in enumerate(text.splitlines(),1)}}


def issued(graph):
    findings = execute(graph,PERFORMANCE)
    coordinates = line_numbers(graph[guarantee.KEY]["rows"])
    calls = {"expert":{"model":"fixture","output":{"followups":[]}},"pages":[]}
    for node in graph["nodes"]:
        if node["type"] != "page":
            continue
        doc,suffix = node["id"].rsplit("/p",1)
        page = int(suffix)
        call = {"doc":doc,"page":page,"page_sha256":node["sha256"],"model":"fixture"}
        if (doc,page) in coordinates:
            call[guarantee.RECTS] = {i:[[0,.1,.9,.2]] for i in coordinates[doc,page]}
        calls["pages"].append(call)
    link_procedures(graph,findings,calls)
    return {"graph":graph,"policy":{**VERSION,"profile":PERFORMANCE},"calls":calls,"findings":findings,"result":conclusion(findings)}


def results(graph, rule):
    return [f for f in execute(graph,PERFORMANCE) if f["rule"]==rule]


def bank_day(day):
    return [(f,l,day if f=="paid_on" else v) for f,l,v in BANK]


class AdvanceGuaranteeTests(unittest.TestCase):
    def test_scoped_raw_rider_and_inline_leave_later_stages_independent(self):
        for rider,inline in ((RIDER,None),(None,INLINE),(None,"合同生效后支付30%，"+RIDER.split("：")[1])):
            with self.subTest(inline=inline):
                graph,_=specimen(rider=rider,inline=inline,letter=None,receipt=None)
                findings=execute(graph,PERFORMANCE)
                self.assertEqual([f["status"] for f in findings if f["rule"] in ("H01","H02","H03")],["ok"]*3)
                for rule,statuses in (("H04",["missing","ok","ok"]),("H05",["missing"])):
                    checks=[f for f in findings if f["rule"]==rule]
                    self.assertEqual([f["status"] for f in checks],statuses)
                    self.assertEqual(checks[0]["advance_guarantee"]["state"],"missing")
                    self.assertTrue(all("advance_guarantee" not in f for f in checks[1:]))
                term=guarantee.scoped(graph,"d01")
                self.assertEqual(term["quote"],rider or "第一期："+inline)
                self.assertEqual(bool(term["facts"]),bool(inline))
        graph,_=specimen(rider=None,letter=None,receipt=None,bank=[(f,l,"第一期" if f=="payment_designation" else v) for f,l,v in BANK])
        self.assertTrue(all(f["status"]=="ok" and "advance_guarantee" not in f for f in results(graph,"H04")+results(graph,"H05")))

    def test_dates_are_documentary_and_first_bank_is_bound_by_its_own_physical_rows(self):
        for day,state,status in (("2026-09-08","before_receipt","risk"),("2026-09-12","same_day","missing"),
                                 ("2026-09-21","after_receipt","missing")):
            with self.subTest(day=day):
                g,_=specimen(bank=bank_day(day),extras=[BANK_DOC])
                h4=results(g,"H04")[0]
                self.assertEqual((h4["status"],h4["advance_guarantee"]["state"]),("missing","recorded"))
                first,second=results(g,"H05")
                proof=first["advance_guarantee"]
                self.assertEqual((first["status"],proof["state"],proof["issued_on"],proof["received_on"],proof["paid_on"]),
                                 (status,state,"2026-09-02","2026-09-12",day))
                cites=[r for r in proof["sources"] if r["role"]=="payment"]
                self.assertEqual({s["doc"] for s in cites},{"d04"})
                self.assertIn("d04/p1",proof["evidence"])
                self.assertNotIn("advance_guarantee",second)
                self.assertEqual(second["status"],"ok")
                date=next(r for r in proof["sources"] if r["field"]=="received_on")
                self.assertEqual((date["quote"],date["line"],date["facts"],date["rects"]),(ACK[-1],5,[],[[0,.1,.9,.2]]))

    def test_only_explicit_beneficiary_term_supports_risk_and_raw_identity_must_be_complete(self):
        cases=[
            (EXPLICIT,(*LETTER[:3],"受益人：演练丙",LETTER[4]),ACK,"mismatch","risk"),
            (RIDER,(*LETTER[:3],"受益人：演练丙",LETTER[4]),ACK,"mismatch","missing"),
            (RIDER,(LETTER[0],"合同编号：YL-123",*LETTER[2:]),ACK,"mismatch","risk"),
            (RIDER,LETTER,(ACK[0],"合同编号：YL-122",*ACK[2:]),"mismatch","risk"),
            (RIDER,LETTER,(*ACK[:2],"签收保函编号：BH-13",*ACK[3:]),"mismatch","risk"),
            (RIDER,LETTER,(*ACK[:3],"签收单位：演练乙",ACK[-1]),"mismatch","risk"),
            (RIDER,LETTER,(*ACK[:2],"签收保函编号：BH-1 2",*ACK[3:]),"review","missing"),
            (RIDER,LETTER,(*ACK[:-1],"签收日期：2026年9月1 2日"),"review","missing"),
            (RIDER,LETTER,None,"missing","missing"),(RIDER,None,ACK,"missing","missing"),
        ]
        for rider,letter,ack,state,status in cases:
            with self.subTest(letter=letter,ack=ack,rider=rider):
                g,_=specimen(rider=rider,letter=letter,receipt=ack)
                proof=results(g,"H04")[0]["advance_guarantee"]
                self.assertEqual((proof["state"],proof["status"],proof["received_on"]),(state,status,None))
                if state=="mismatch" and status=="missing":
                    self.assertIn("核实",proof["detail"])

    def test_issuer_and_bank_memo_are_documentary_and_new_qualifications_withhold_the_claim(self):
        issuer="开立机构：云岫演练担保中心"
        memo="银行附言：本合同第一期预付款"
        for note,state in ((None,"before_receipt"),("本函核验通过后另行生效","review")):
            form=(*LETTER,issuer,*([note] if note else []))
            g,_=specimen(letter=form,bank=bank_day("2026-09-08"),omitted=[(4,memo),(4,"币种：人民币"),(4,"金额单位：元")])
            proof=results(g,"H05")[0]["advance_guarantee"]
            self.assertEqual(proof["state"],state)
            origin=next(r for r in proof["sources"] if r["field"]=="issuer")
            self.assertEqual((origin["quote"],origin["line"]),(issuer,None if note else 6))
            self.assertEqual(next(r["quote"] for r in proof["sources"] if r["field"]=="payment_note"),memo)
        for memo in ("银行附言：本合同第二期预付款","银行附言：本合同第一期预付款，尚待审批"):
            g,_=specimen(bank=bank_day("2026-09-08"),omitted=[(4,memo)])
            proof=results(g,"H05")[0]["advance_guarantee"]
            self.assertEqual((proof["state"],proof["paid_on"]),("review",None))

    def test_matching_bank_references_across_copies_and_anchored_distinct_transfers(self):
        def bank(ref,day):
            return [*bank_day(day),("transfer_ref","交易流水号",ref)]
        for ref,states in (("pay-123",["review","review"]),("PAY-456",["before_receipt","after_receipt"])):
            g,_=specimen(bank=bank("PAY-123","2026-09-08"),extras=[bank(ref,"2026-09-20")])
            self.assertEqual([f["advance_guarantee"]["state"] for f in results(g,"H05")],states)

    def test_unscoped_shadow_addendum_and_unrelated_document_cannot_free_other_conditions(self):
        for rider,omissions in ((RIDER+"且须董事会批准",()),(RIDER,((1,"第二期付款条件：另须取得项目审批"),)),
                                (RIDER,((1,"补充约定：保函另须经复核批准方生效"),)),(RIDER,((1,RIDER),))):
            with self.subTest(rider=rider,omissions=omissions):
                g,_=specimen(rider=rider,omitted=omissions)
                self.assertTrue(any(f["status"]!="ok" for f in results(g,"H04")[1:]))
        g,_=specimen(rider="质保期届满后应退还履约保函",letter=None,receipt=None)
        self.assertFalse(g[guarantee.KEY]["rows"])
        g,_=specimen(extras=[[("other","","其他未分类协议")]])
        self.assertNotEqual(results(g,"H03")[0]["status"],"ok")

    def test_ambiguous_or_unexecuted_bank_does_not_determine_payment_order(self):
        early=bank_day("2026-09-08")
        for extras,omitted in (([early],()),([],[(4,"银行附注：本笔随后已撤销")]),
                               ([],[(4,"回单提示：本单仅为付款申请受理凭证，不代表实际扣款")]),
                               ([],[(4,"付款日期：2026年9月10日")]),([],[(4,"银行付款回单")])):
            with self.subTest(extras=extras,omitted=omitted):
                g,_=specimen(bank=early,extras=extras,omitted=omitted)
                for f in results(g,"H05"):
                    proof=f.get("advance_guarantee",{})
                    self.assertIsNone(proof.get("paid_on"))
                    self.assertNotEqual(proof.get("state"),"before_receipt")
                    if "execution_basis" in f:
                        self.assertEqual(f["status"],"risk")
                        self.assertIn("限定",f["detail"])
        for field,value in (("payer","演练丙"),("transfer_status","已受理"),("payment_designation","货款")):
            g,_=specimen(bank=[(f,l,value if f==field else v) for f,l,v in early])
            self.assertNotIn("advance_guarantee",results(g,"H05")[0])
        g,_=specimen(bank=bank_day("2026-08-30"),receipt=None)
        first=results(g,"H05")[0]
        self.assertEqual(first["status"],"risk")
        self.assertIn("履约日期",first["detail"])

    def test_multisheet_and_unreadable_sources_are_page_only(self):
        extra={"doc":"d05","number":2,"sha256":"page2","text":"附加条件详见正本","layer":layout("附加条件详见正本"),
               "extraction":{"output":{"quality":"readable","facts":[]}}}
        g,texts=specimen(pages=[extra])
        rows=[r for r in g[guarantee.KEY]["rows"] if r["doc"]=="d05"]
        self.assertTrue(rows)
        self.assertTrue(all(r["line"] is None and not r["rects"] and "/hold" in r["id"] for r in rows))
        self.assertEqual(len({r["id"] for r in rows}),len(rows))
        self.assertEqual(results(g,"H04")[0]["advance_guarantee"]["state"],"review")
        g,texts=specimen()
        pg=next(n for n in g["nodes"] if n["id"]=="d06/p1")
        for layer in ("text","image"):
            pg.update(layer=layer,clause_text_only=False)
            ledger=guarantee.sources(g,lambda d,n:texts[d,n],lambda d,n:layout(texts[d,n]))
            cited=[r for r in ledger["rows"] if r["unit"]=="d06"]
            self.assertTrue(cited and all(r["line"] is None and not r["rects"] for r in cited))

    def test_replay_and_integrity_of_claims_edges_and_raw_rectangles(self):
        from jobs import CODE_DIGESTS
        from rule_replay import replay_installed
        graph,texts=specimen()
        report=issued(graph)
        report["policy"]["code_sha256"]=CODE_DIGESTS
        read=lambda d,n:texts[d,n]
        guarantee.verify(report,read)
        guarantee.verify(report,read,signing=True,read_layout=lambda d,n:layout(read(d,n)))
        verify_findings(report)
        self.assertEqual(replay_installed(report)["finding_count"],len(report["findings"]))
        for target in ("marker","method","ledger","edge","supports","finding","rect","fact","hash","added"):
            with self.subTest(target=target):
                bad=copy.deepcopy(report)
                graph=bad["graph"]
                claim=next(f for f in bad["findings"] if "advance_guarantee" in f)
                if target=="marker": del bad["policy"]["advance_guarantee"]
                if target=="method": del bad["policy"]["code_sha256"]["advance_guarantee.py"]
                if target=="ledger": graph[guarantee.KEY]["rows"][-1]["quote"]+="？"
                if target=="edge": next(e for e in graph["edges"] if e["type"]=="advance_guarantee_source")["from"]="d99/p1"
                if target=="supports":
                    graph["edges"].remove(next(e for e in graph["edges"] if e["type"]=="supports_result" and
                                               e["to"]=="finding/"+claim["id"] and e["from"] in claim["advance_guarantee"]["evidence"]))
                if target=="finding": claim["advance_guarantee"]["state"]="after_receipt"
                if target=="rect": bad["calls"]["pages"][-1][guarantee.RECTS]["5"]=[[.2,.2,.8,.3]]
                if target=="fact": graph[guarantee.KEY]["rows"][-1]["facts"]=["d01/p1/f1"]
                if target=="hash": graph["documents"][-1]["sha256"]="foreign"
                if target=="added": next(f for f in bad["findings"] if f["rule"]=="H02")["advance_guarantee"]=claim["advance_guarantee"]
                with self.assertRaises(ValueError):
                    guarantee.verify(bad,read)

    def test_actual_legacy_approval_gate_with_and_without_rider(self):
        g,texts=specimen(rider="首款条件：买方须先收到保函",letter=None,receipt=None)
        del g[guarantee.KEY]
        g["nodes"]=[n for n in g["nodes"] if n["type"]!="advance_guarantee_line"]
        g["edges"]=[e for e in g["edges"] if e["type"]!="advance_guarantee_source"]
        paper={"graph":g,"findings":[{"rule":"H04","status":"ok","stage":{"name":"第一期"}}],
               "policy":{"version":"2026.11.27.04","profile":PERFORMANCE,"payment_execution":VERSION["payment_execution"]}}
        guarantee.verify(paper,lambda d,n:texts[d,n])
        raw=encode(paper)
        with tempfile.TemporaryDirectory() as tmp,sqlite3.connect(":memory:") as db:
            store=Store(Path(tmp))
            db.row_factory=sqlite3.Row
            db.executescript("CREATE TABLE cases(id,created);CREATE TABLE reports(case_id,rev,content,hash);CREATE TABLE pages(case_id,doc,number,text,layer);")
            db.execute("INSERT INTO cases VALUES('fixture','2026-11-27')")
            db.execute("INSERT INTO reports VALUES('fixture',1,?,?)",(raw,hashlib.sha256(raw.encode()).hexdigest()))
            db.executemany("INSERT INTO pages VALUES('fixture',?,?,?,?)",[(d,n,t,encode(layout(t))) for (d,n),t in texts.items()])
            with self.assertRaisesRegex(CaseError,"旧版已通过的首期付款"):
                store.recheck_approval(db,"fixture",1,{})
        g,texts=specimen(rider=None,letter=None,receipt=None)
        del g[guarantee.KEY]
        guarantee.verify({**paper,"graph":g},lambda d,n:texts[d,n],signing=True)

    def test_balanced_legacy_h06_alone_does_not_assert_performance_or_payment_timing(self):
        graph,texts=specimen(rider=RIDER,letter=None,receipt=None)
        del graph[guarantee.KEY]
        graph["nodes"]=[n for n in graph["nodes"] if n["type"]!="advance_guarantee_line"]
        graph["edges"]=[e for e in graph["edges"] if e["type"]!="advance_guarantee_source"]
        stage={"name":"第一期","clause_ref":"d01/p1/f12"}
        findings=[{"rule":"H04","status":"missing","stage":stage},
                  {"rule":"H05","status":"risk","stage":stage},
                  {"rule":"H06","status":"ok","stage":stage,"stage_payments":{"state":"balanced","difference":"0.00"}},
                  {"rule":"H04","status":"ok","stage":{"name":"第二期","clause_ref":"d01/p1/f13"}}]
        paper={"graph":graph,"policy":{"version":"2026.11.27.04","profile":PERFORMANCE},"findings":findings}
        read=lambda d,n:texts[d,n]
        guarantee.verify(paper,read,signing=True)
        for index in (0,1):
            with self.subTest(upstream=findings[index]["rule"]):
                changed=copy.deepcopy(paper)
                changed["findings"][index]["status"]="ok"
                with self.assertRaisesRegex(ValueError,"旧版已通过的首期付款"):
                    guarantee.verify(changed,read,signing=True)
