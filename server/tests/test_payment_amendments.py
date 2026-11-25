import copy
import unittest

from config import PERFORMANCE
from contract_changes import verify_sources
from controls import VERSION, execute
from performance import verify_findings
from test_contract_changes import CHANGE
from test_invoice_conditions import ACK, INVOICE
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


OLD = "第二期：最终验收合格后支付60%"
NEW = "第二期：最终验收合格且买方收到本合同对应的发票后支付60%"
AMENDMENT = [
    *CHANGE[:6], ("change_scope","变更范围","仅新增第二期验收款收票前提，其余条款不变"),
    ("previous_payment_stage","原付款条款",OLD), ("revised_payment_stage","变更后付款条款",NEW),
    ("change_timing","变更适用时点","仅适用于本协议生效后支付的第二期验收款"),
    ("change_effect_clause","协议生效条款","本协议自双方盖章之日起生效"),
    ("buyer_sealed_on","甲方盖章日期","2026-09-16"), ("seller_sealed_on","乙方盖章日期","2026-09-18"),
    *CONTRACT[8:10]]
DATED_ACK = [(k,l,"2026-09-22" if k=="invoice_received_on" else v) for k,l,v in ACK]


def fixture(*, ack=DATED_ACK, amendment=AMENDMENT, edit=None, extra=(), omit=(), bank=BANK_DOC, pages=()):
    groups=[CONTRACT,amendment,[*RECEIPT,*ack],WARRANTY,bank,INVOICE,*extra]
    att={f"d03/p1/f{len(RECEIPT)+3}":{"decision":"confirm","source_check":{"fixture":True}}} if ack else {}
    g=material(groups,edit=edit,omissions=omit,attestations=att,extra_pages=pages)
    return g,execute(g,PERFORMANCE)


def by_rule(findings,rule):
    return [f for f in findings if f["rule"]==rule]


class PaymentAmendmentTests(unittest.TestCase):
    def test_prospective_versions(self):
        for seal,ack,condition,timing,edition in [("18",DATED_ACK,"ok","risk","amended"),("22",[],"missing","ok","original"),
                                                   ("21",DATED_ACK,"ok","missing","same_day")]:
            with self.subTest(seal=seal):
                g,fs=fixture(ack=ack,edit=lambda i,k,l,v:"2026-09-"+seal if i==2 and k=="seller_sealed_on" else v)
                self.assertEqual([f["status"] for f in fs if f["rule"] in ("H01","H02","H03")],["ok"]*3)
                stages=by_rule(fs,"H04"); pay,=by_rule(fs,"H05")
                self.assertEqual([f["status"] for f in stages],["ok",condition,"ok"])
                self.assertEqual(pay["status"],timing)
                change=stages[1]["payment_change"]
                self.assertTrue(change["scope_clear"])
                self.assertEqual(change["effective_on"],"2026-09-"+seal)
                self.assertEqual(pay["payment_change"]["applies"],edition)
                self.assertEqual(pay["payment_change"]["paid_on"],"2026-09-21")
                for key in ("original_ref","previous_ref","revised_ref","scope_ref","timing_ref","buyer_date_ref","seller_date_ref"):
                    self.assertIn(change[key],stages[1]["evidence"])
                    self.assertIn(change[key],pay["evidence"])
                self.assertNotIn("payment_change",stages[0])
                self.assertNotIn("payment_change",stages[2])
                if edition!="amended":
                    self.assertNotIn("invoice_receipt",pay)

    def test_unsigned_or_undated_only_holds_this_installment(self):
        for field,value in (("seller_signature","待盖章"),("seller_sealed_on","2026-09-1 8"),("buyer_sealed_on",None)):
            g,fs=fixture(edit=lambda i,k,l,v:value if i==2 and k==field else v)
            self.assertEqual([f["status"] for f in by_rule(fs,"H04")],["ok","missing","ok"])
            self.assertEqual(by_rule(fs,"H02")[0]["status"],"ok")
            self.assertEqual(by_rule(fs,"H05")[0]["payment_change"]["applies"],"pending")
            self.assertNotIn("invoice_receipt",by_rule(fs,"H05")[0])

    def test_unclear_scope_and_source_identity_keep_unrelated_claims_open(self):
        for options in (
            {"edit":lambda i,k,l,v:"YL-999" if i==2 and k=="base_contract_ref" else v},
            {"edit":lambda i,k,l,v:"合同成立之日起适用" if i==2 and k=="change_timing" else v},
            {"edit":lambda i,k,l,v:NEW.replace("60%","65%") if i==2 and k=="revised_payment_stage" else v},
            {"edit":lambda i,k,l,v:OLD.replace("最终","") if i==2 and k=="previous_payment_stage" else v},
            {"omit":[(2,"备注：另行提高终验质量标准")]}, {"extra":[AMENDMENT]},
            {"omit":[(1,"验收款支付前提：买方收到供应方就本合同开具的发票")]},
            {"omit":[(2,"甲方盖章日期：2026-09-25"),(2,"原付款条款："+OLD)]}):
            with self.subTest(options=options):
                _,fs=fixture(**options)
                self.assertEqual(by_rule(fs,"H03")[0]["status"],"missing")
                self.assertFalse(by_rule(fs,"H03")[0]["payment_change"]["scope_clear"])
                self.assertNotEqual(by_rule(fs,"H05")[0]["status"],"ok")

    def test_original_clause_does_not_clear_an_independent_acceptance_failure(self):
        def edit(i,k,l,v):
            if i==2 and k=="seller_sealed_on": return "2026-09-22"
            return "柜温8℃" if k=="measured_result" else v
        _,fs=fixture(ack=[],edit=edit)
        self.assertEqual(by_rule(fs,"H02")[0]["status"],"issue")
        pay=by_rule(fs,"H05")[0]
        self.assertEqual(pay["payment_change"]["applies"],"original")
        self.assertNotEqual(pay["status"],"ok")

    def test_image_only_continuation_prevents_a_definitive_version(self):
        page={"doc":"d02","number":2,"sha256":"scan","text":"","layer":{"type":"image","clause_text_only":False,"lines":{}},
              "extraction":{"output":{"quality":"readable","facts":[{"field":"other","value":"另见附件","quote":"另见附件","region":"top"}]}}}
        _,fs=fixture(pages=[page])
        self.assertFalse(by_rule(fs,"H03")[0]["payment_change"]["scope_clear"])
        self.assertEqual(by_rule(fs,"H05")[0]["status"],"missing")

    def test_each_receipt_uses_its_own_date(self):
        later=[(k,l,"2026-09-24" if k=="paid_on" else v) for k,l,v in BANK_DOC]
        _,fs=fixture(ack=[],edit=lambda i,k,l,v:"2026-09-22" if i==2 and k=="seller_sealed_on" else v,extra=[later])
        self.assertEqual([(p["payment_change"]["applies"],p["status"]) for p in by_rule(fs,"H05")],
                         [("original","ok"),("amended","missing")])

    def test_preserve_disputed_or_ambiguous_bank_records(self):
        g,fs=fixture(omit=[(5,"回单备注：交易已撤销")])
        self.assertNotEqual(by_rule(fs,"H05")[0]["status"],"ok")
        g,fs=fixture(edit=lambda i,k,l,v:"2026-09-2 1" if i==5 and k=="paid_on" else v)
        self.assertEqual(by_rule(fs,"H05")[0]["status"],"missing")

    def test_reconstruct_native_sources_and_decision(self):
        g,fs=fixture()
        report={"graph":g,"findings":fs,"policy":{**VERSION,"profile":PERFORMANCE}}
        source=[CONTRACT,AMENDMENT,[*RECEIPT,*DATED_ACK],WARRANTY,BANK_DOC,INVOICE]
        texts={f"d{i:02d}":"\n".join(l+"："+v if l else v for _,l,v in group) for i,group in enumerate(source,1)}
        read=lambda doc,p:texts[doc]
        verify_sources(report,read);verify_findings(report)
        altered=copy.deepcopy(report)
        by_rule(altered["findings"],"H05")[0]["payment_change"]["applies"]="original"
        with self.assertRaises(ValueError): verify_findings(altered)
        altered=copy.deepcopy(report);altered["graph"]["quality_addenda"]["payments"]["lines"].pop()
        with self.assertRaises(ValueError): verify_sources(altered,read)
        altered=copy.deepcopy(report)
        altered["graph"]["edges"].remove(next(e for e in altered["graph"]["edges"] if e["type"]=="payment_amendment_basis"))
        with self.assertRaises(ValueError): verify_sources(altered,read)
