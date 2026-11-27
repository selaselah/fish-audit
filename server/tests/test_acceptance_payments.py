import copy
import unittest

from acceptance_payments import classify
from acceptance_reservations import SUPPLIER, sources, verify
from config import PERFORMANCE
from controls import VERSION, execute
from performance import compute, verify_findings
from test_delivery_batches import sample as batch_case
from test_payment_amendments import AMENDMENT, DATED_ACK, INVOICE
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


ALL="付款意见：本合同项下全部付款暂缓"
HOLD="付款意见：第二期验收款暂缓支付"
ASSENT="付款备注：同意支付第二期验收款"


def paper(*notes, edit=None, extra=(), groups=None):
    g=material(groups or [CONTRACT,RECEIPT,WARRANTY,BANK_DOC],edit=edit,omissions=[(2,s) for s in notes],extra_pages=extra)
    texts={d["id"]:"\n".join(f["quote"] for f in g["facts"] if f["doc"]==d["id"]) for d in g["documents"]}
    if notes:
        texts["d02"]+="\n"+"\n".join(notes)
    return g,lambda doc,n:texts[doc]


class FinalPaymentOpinionTests(unittest.TestCase):
    def test_native_hold_can_be_absent_from_model_facts(self):
        for note,expected in ((ALL,["missing"]*3),(HOLD,["ok","missing","ok"])):
            g,read=paper(note)
            fs=compute(g)
            self.assertEqual([f["status"] for f in fs[:3]],["ok"]*3)
            phases=[f for f in fs if f["rule"]=="H04"]
            self.assertEqual([f["status"] for f in phases],expected)
            self.assertNotIn("payment_window",phases[1])
            for f in [phases[1],fs[-1]]:
                bit=f["payment_opinion"]; self.assertEqual(bit["state"],"hold")
                row,=bit["notes"]; self.assertEqual((row["quote"],row["facts"]),(note,[]))
                self.assertEqual(read(row["doc"],row["page"]).splitlines()[row["line"]-1],note)
                self.assertIn(row["doc"]+"/p1",f["evidence"])
                self.assertEqual(bit["record_dates"][0]["date"],"2026-09-20")
            self.assertEqual(fs[-1]["status"],"missing")

    def test_opposing_rows_remain_visible_and_agreement_cannot_cure_a_defect(self):
        g,_=paper(HOLD,ASSENT)
        fs=compute(g); self.assertEqual([f["status"] for f in fs],["ok","ok","ok","ok","risk","ok","missing"])
        note=fs[4]["payment_opinion"]
        self.assertEqual((note["state"],[s["quote"] for s in note["notes"]]),("conflict",[HOLD,ASSENT]))
        g,_=paper(ASSENT,edit=lambda i,k,l,v:"柜温8℃" if k=="measured_result" else v)
        fs=compute(g); self.assertEqual((fs[1]["status"],fs[4]["status"],fs[-1]["status"]),("issue","risk","risk"))
        self.assertEqual(fs[-1]["payment_quality"]["measure"]["observed"],"8")
        self.assertEqual(fs[4]["payment_opinion"]["state"],"assent")
        g,_=paper(HOLD,edit=lambda i,k,l,v:"2026-09-12" if k=="paid_on" else v)
        self.assertEqual(compute(g)[-1]["status"],"risk")

    def test_uncertain_targets_and_extra_riders_never_clear_another_phase(self):
        for notes in [(HOLD,"并包括原合同其他未付价款"),("付款意见：第 2 期验收款暂缓支付",),
                      ("付款意见：第3期验收款暂缓支付",),("付款意见：第二二期验收款暂缓支付",),
                      ("付款意见：第二期验收款暂缓支付，另扣留首期预付款",),("付款意见：详见附页影像批注",)]:
            with self.subTest(notes=notes):
                g,_=paper(*notes); fs=compute(g)
                self.assertTrue(all(f["payment_opinion"]["state"]=="unresolved" and f["status"]!="ok" for f in fs[3:]))
        self.assertIsNone(classify("验收日期：2026年9月20日"))
        self.assertIsNone(classify("付款意见：无"))

    def test_unbound_mixed_and_disputed_notes_are_not_established_scope(self):
        for field,value in (("contract_id","YL-999"),("buyer","演练丙"),("seller","同合同")):
            g,_=paper(HOLD,edit=lambda i,k,l,v:value if i==2 and k==field else v)
            self.assertTrue(all(f["payment_opinion"]["state"]=="unresolved" for f in compute(g)[3:]))
        g,read=paper(HOLD)
        next(n for n in g["nodes"] if n["id"]=="d02/p1")["clause_text_only"]=False
        g["acceptance_reservation_sources"]=sources(g,read)
        self.assertEqual(compute(g)[4]["payment_opinion"]["state"],"unresolved")
        g,_=paper(groups=[CONTRACT,[*RECEIPT,("other","付款意见","第二期验收款暂缓支付")],WARRANTY,BANK_DOC])
        next(f for f in g["facts"] if f["field"]=="other")["status"]="disputed"
        self.assertEqual(compute(g)[4]["payment_opinion"]["state"],"unresolved")

    def test_same_contract_with_bank_receipts_for_different_stages(self):
        pre=[(f,l,"第一期" if f=="payment_designation" else v) for f,l,v in BANK_DOC]
        g,_=paper(HOLD,groups=[CONTRACT,RECEIPT,WARRANTY,BANK_DOC,pre])
        payments=[f for f in compute(g) if f["rule"]=="H05"]
        self.assertEqual([f["status"] for f in payments],["missing","ok"])
        self.assertNotIn("payment_opinion",payments[1])
        g=batch_case(omissions=[(3,"付款意见：第三期验收款暂缓支付")])
        phases=[f for f in compute(g) if f["rule"]=="H04"]
        self.assertEqual([bool(f.get("payment_opinion")) for f in phases],[False,False,True,False])

    def test_before_addendum_payment_still_checks_separate_opinion(self):
        late=[(f,l,"2026-09-22" if f=="seller_sealed_on" else v) for f,l,v in AMENDMENT]
        g=material([CONTRACT,late,[*RECEIPT,*DATED_ACK],WARRANTY,BANK_DOC,INVOICE],omissions=[(3,HOLD)])
        f=next(f for f in compute(g) if f["rule"]=="H05")
        self.assertEqual((f["payment_change"]["applies"],f["payment_opinion"]["state"],f["status"]),("original","hold","missing"))

    def test_frozen_legacy_results_and_current_provenance(self):
        g,read=paper(ALL)
        report={"graph":g,"policy":{**VERSION,"profile":PERFORMANCE},"findings":execute(g,PERFORMANCE)}
        verify(report,read);verify_findings(report)
        for item in ("row","edge","finding"):
            changed=copy.deepcopy(report)
            if item=="row":changed["graph"]["acceptance_reservation_sources"]["payment_opinions"][0]["quote"]=ASSENT
            if item=="edge":next(e for e in changed["graph"]["edges"] if e["type"]=="acceptance_payment_opinion")["line"]+=1
            if item=="finding":next(f for f in changed["findings"] if f.get("payment_opinion"))["payment_opinion"]["state"]="assent"
            with self.assertRaises(ValueError):
                verify_findings(changed) if item=="finding" else verify(changed,read)
        g["acceptance_reservation_sources"]=sources(g,read,SUPPLIER)
        g["edges"]=[e for e in g["edges"] if e["type"]!="acceptance_payment_opinion"]
        old={"graph":g,"policy":{**report["policy"],"version":"2026.11.25.24","acceptance_reservations":SUPPLIER},"findings":compute(g)}
        self.assertTrue(all(f["status"]=="ok" for f in old["findings"]))
        verify(old,read)
        with self.assertRaisesRegex(ValueError,"旧版列为相符"):
            verify(old,read,signing=True)
