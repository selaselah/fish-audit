import copy
import unittest
from datetime import date

from cn_workdays import SOURCE_KEY, after_workdays, working_date
from controls import VERSION, execute
from graph import link_procedures
from payment_windows import edges, sources, spec, verify
from performance import compute, verify_findings
from performance_versions import WARRANTY_FORMAT
from policy import link_sources
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


RELATIVE="终验合格后5个自然日内支付，届满日不顺延"
WORK="最终验收合格后3个工作日内支付60%（按国家调休日历）"


def audit(label="验收款付款期限",value=RELATIVE,*,inline=False,paid="2026-09-23",
          accepted="2026-09-20",phase="第二期",extra=(),omissions=(),alter=None,bank=True):
    contract=list(CONTRACT)
    if inline:
        contract=[(f,l,value if l==phase else v) for f,l,v in contract]
    elif value is not None:
        contract.append(("payment_deadline",label,value))
    def edit(i,key,label,old):
        raw={"accepted_on":accepted,"paid_on":paid,"payment_designation":phase}.get(key,old)
        return alter(i,key,label,raw) if alter else raw
    return material([contract+list(extra),RECEIPT,WARRANTY]+([BANK_DOC] if bank else []),edit,omissions=omissions)


def findings(graph,version=None):
    items=compute(graph,version) if version else compute(graph)
    stages=[f for f in items if f["rule"]=="H04"]
    return stages,next((f for f in items if f["rule"]=="H05"),None)


def texts(graph):
    return {d["id"]:"\n".join(f["quote"] for f in graph["facts"] if f["doc"]==d["id"]) for d in graph["documents"]}


class PaymentWindowsTests(unittest.TestCase):
    def test_acceptance_and_actual_transfer_are_independent(self):
        for paid,status,outcome in (("2026-09-19","risk","early"),("2026-09-20","missing","same_day"),
                    ("2026-09-23","ok","within"),("2026-09-25","missing","same_day"),("2026-10-09","risk","late")):
            with self.subTest(paid=paid):
                phases,bank=findings(audit(paid=paid))
                self.assertEqual([s["status"] for s in phases],["ok"]*3)
                self.assertEqual(["payment_window" in p for p in phases],[False,True,False])
                w=bank["payment_window"]
                self.assertEqual((bank["status"],w["outcome"],w["trigger_on"],w["calendar_end"],w["paid_on"]),
                                 (status,outcome,"2026-09-20","2026-09-25",paid))
                self.assertEqual(w["days_late"],14 if outcome=="late" else None)
                self.assertTrue({w["term_ref"],w["trigger_ref"],w["paid_ref"]}<=set(bank["evidence"]))
        stages,bank=findings(audit(bank=False))
        self.assertIsNone(bank)
        self.assertNotIn("outcome",stages[1]["payment_window"])

    def test_national_calendar_includes_makeup_saturday_and_archive_source(self):
        graph=audit(value=WORK,inline=True,accepted="2026-09-30",paid="2026-10-12")
        phase,bank=findings(graph)
        w=bank["payment_window"]
        self.assertEqual(w["calendar_end"],"2026-10-10")
        self.assertEqual((w["outcome"],w["days_late"],phase[1]["status"]),("late",2,"ok"))
        self.assertEqual([r["date"] for r in w["days"] if r["counted"]],["2026-10-08","2026-10-09","2026-10-10"])
        self.assertEqual([r["kind"] for r in w["days"]],["放假"]*7+["工作日","工作日","调休上班"])
        self.assertIn("source/"+SOURCE_KEY,bank["evidence"])
        for actual in ((1,4),(2,14),(2,28),(5,9),(9,20),(10,10)):
            self.assertEqual(working_date(date(2026,*actual)),("调休上班",True))
        self.assertIsNone(after_workdays(date(2026,12,31),2)[0])
        self.assertIsNone(working_date(date(2027,1,5)))

    def test_fixed_date_and_prepayment_do_not_require_reinterpreting_other_phases(self):
        for label in ("验收款最迟付款日","第二期付款截止日"):
            _,bank=findings(audit(label,"2026年9月25日，届满日不顺延",paid="2026-10-09"))
            self.assertEqual((bank["status"],bank["payment_window"]["days_late"]),("risk",14))
        graph=audit("预付款付款期限","合同生效后5个自然日内支付，届满日不顺延",phase="第一期",paid="2026-09-03",
                    alter=lambda i,k,l,v:"不合格" if k=="acceptance_result" else v)
        stages,bank=findings(graph)
        self.assertEqual((stages[0]["status"],bank["status"],bank["payment_window"]["trigger_on"]),("ok","ok","2026-09-01"))
        self.assertNotEqual(stages[1]["status"],"ok")

    def test_unresolved_calendar_does_not_turn_into_late_payment(self):
        for value,outcome,end in (("终验合格后5个自然日内支付","extension_unknown","2026-09-25"),
                   ("终验合格后5个工作日内支付","unresolved",None),
                   ("收到合规发票后5个自然日内支付","unresolved",None),
                   ("终验合格后1 5个自然日内支付","unresolved",None)):
            _,bank=findings(audit(value=value,paid="2026-10-09"))
            self.assertEqual((bank["status"],bank["payment_window"]["outcome"],bank["payment_window"]["calendar_end"]),
                             ("missing",outcome,end))
        self.assertIsNone(spec("第二期：最终验收合格后3个工作日内支付60%（按国家调休日历"))
        _,bank=findings(audit(value=WORK,inline=True,accepted="2026-12-30",paid="2027-01-05"))
        self.assertIsNone(bank["payment_window"]["calendar_end"])
        self.assertEqual(bank["status"],"missing")

    def test_missed_or_competing_deadlines_keep_their_own_source_lines(self):
        for doc in (1,2):
            graph=audit(value=None,paid="2026-10-09",omissions=[(doc,"验收款最迟付款日：2026年9月25日")])
            self.assertEqual(findings(graph,WARRANTY_FORMAT)[1]["status"],"ok")
            stages,bank=findings(graph)
            self.assertEqual([s["status"] for s in stages],["ok","missing","ok"])
            line,=bank["payment_window"]["lines"]
            self.assertEqual((bank["status"],line["facts"],line["doc"]),("missing",[],f"d0{doc}"))
            self.assertIn(f"d0{doc}/p1",bank["evidence"])
        for raw in ("补记：验收款须以到账时点为准","验收款最迟付款日：2026年10月15日"):
            _,bank=findings(audit(omissions=[(2,raw)]))
            self.assertEqual((bank["status"],bank["payment_window"]["calendar_end"]),("missing",None))

    def test_bank_only_qualifications_and_image_layers(self):
        _,bank=findings(audit(value=None,omissions=[(4,"附注：本笔款项已退汇")]))
        self.assertEqual((bank["status"],bank["payment_window"]["state"]),("missing","unresolved"))
        for doc in ("d02","d04"):
            graph=audit()
            text=texts(graph)
            next(n for n in graph["nodes"] if n["id"]==doc+"/p1")["clause_text_only"]=False
            graph["payment_window_sources"]=sources(graph,lambda d,p:text[d])
            stages,bank=findings(graph)
            self.assertEqual(stages[0]["status"],"ok")
            self.assertEqual(stages[1]["status"],"missing" if doc=="d02" else "ok")
            self.assertEqual(bank["status"],"missing")
            self.assertIn(doc+"/p1",bank["evidence"])

    def test_strict_identity_and_multiple_or_inconsistent_periods(self):
        for field,unit in (("payer",4),("contract_id",4),("seller",2)):
            _,bank=findings(audit(alter=lambda i,k,l,v:v[:1]+" "+v[1:] if i==unit and k==field else v))
            self.assertNotEqual(bank["status"],"ok")
        stages,bank=findings(audit(label="第四期付款期限"))
        self.assertTrue(all(s["status"]!="ok" for s in stages))
        one_phase=[r for r in CONTRACT if r[0] not in ("payment_term","payment_stage")]+[
                    ("payment_stage","第一期","最终验收合格后支付100%"),("payment_deadline","第二期最迟付款日","2026年9月25日")]
        single=material([one_phase,RECEIPT])
        self.assertEqual(findings(single)[0][0]["payment_window"]["state"],"unresolved")
        stages,bank=findings(audit(label="验收款最迟付款日",value="2026年9月15日"))
        self.assertEqual((stages[1]["status"],bank["payment_window"]["state"]),("risk","conflict"))

    def test_archive_verification_including_annual_schedule_and_legacy_approval(self):
        graph=audit(value=WORK,inline=True,accepted="2026-09-30",paid="2026-10-12")
        read=texts(graph)
        report={"graph":graph,"policy":{**VERSION,"profile":graph["profile"]},"findings":execute(graph,graph["profile"])}
        link_procedures(graph,report["findings"],{"expert":{"model":"test"},"pages":[]})
        link_sources(graph)
        verify(report,lambda d,p:read[d])
        verify_findings(report)
        for part in ("markers","inputs","edges","notice","days","deadline"):
            changed=copy.deepcopy(report)
            if part=="markers": del changed["policy"]["payment_windows"]
            if part=="inputs": changed["graph"]["payment_window_sources"]["lines"]=[]
            if part=="edges": changed["graph"]["edges"].remove(edges(changed["findings"])[0])
            if part=="notice": changed["policy"]["sources"][SOURCE_KEY]["edition"]="改列日历"
            if part=="days": changed["findings"][-1]["payment_window"]["days"][0]["counted"]=True
            if part=="deadline": changed["findings"][-1]["payment_window"]["calendar_end"]="2099-01-01"
            with self.assertRaises(ValueError):
                verify_findings(changed) if part in ("days","deadline") else verify(changed,lambda d,p:read[d])
        clause="验收款最迟付款日：2026年9月25日"
        old_graph=audit(value=None,paid="2026-10-09",omissions=[(1,clause)])
        del old_graph["payment_window_sources"]
        native=texts(old_graph)
        native["d01"]+="\n"+clause
        old={"graph":old_graph,"policy":{"performance_checks":WARRANTY_FORMAT},"findings":compute(old_graph,WARRANTY_FORMAT)}
        self.assertEqual(old["findings"][-1]["status"],"ok")
        verify(old,lambda d,p:native[d])
        with self.assertRaisesRegex(ValueError,"旧版付款"):
            verify(old,lambda d,p:native[d],signing=True)
