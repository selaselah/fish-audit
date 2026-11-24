from decimal import Decimal
import unittest

from calculations import CalculationEvidence
from config import BANK
from controls import conclusion, execute
from graph import build_graph


def receipt_material(*, reference_note=None, reference_quote=None, **overrides):
    accounts = "000000000000000081"
    shared = [("currency","币种","人民币"),("unit","金额单位","元"),("contract_id","合同编号","YL-081")]
    rows = [
        [("contract","","采购合同"),("buyer","采购方","演练甲"),("seller","供应方","演练乙"),
         ("contract_account","约定收款账号",accounts),("payment_term","结算条款","一次性全额结算"),
         ("signed_on","签约日期","2026-10-12"),("total","含税总额","8,400.00"),*shared],
        [("bank_receipt","","银行付款回单"),("payer","付款户名","演练甲"),("payee","收款户名","演练乙"),
         ("payee_account","收款账号",accounts),("transfer_amount","付款金额","8,400.00"),
         ("paid_on","付款日期","2026-10-19"),("transfer_status","交易状态","交易成功"),
         ("transfer_ref","交易流水号","YL-081-A"),*shared]]
    docs,pages=[],[]
    for n,plain in enumerate(rows,1):
        doc=f"d{n:02d}"; facts=[]
        for field,label,value in plain:
            value=overrides.get(field,value)
            if value is not None:
                facts.append({"field":field,"value":value,"quote":label+"："+value if label else value,"region":"top"})
        if n==2 and reference_quote:
            next(f for f in facts if f["field"]=="transfer_ref")["quote"] = reference_quote
        lines = [f["quote"] for f in facts]
        if n==2 and reference_note:
            lines.append(reference_note)
        docs.append({"id":doc,"name":doc,"sha256":"synthetic"})
        pages.append({"doc":doc,"number":1,"sha256":"page","text":"\n".join(lines),
                      "layer":{"type":"text","lines":{str(i):[[0,.1,.9,.12]] for i in range(1,len(lines)+1)}},
                      "extraction":{"output":{"quality":"readable","facts":facts}}})
    return docs, pages


class ReceiptControls(unittest.TestCase):
    def evaluate(self, **overrides):
        docs, pages = receipt_material(**overrides)
        self.graph = build_graph(docs, pages, {})
        self.graph["profile"] = BANK
        findings = execute(self.graph, BANK)
        CalculationEvidence(self.graph).verify(findings)
        return findings

    def test_settled_receipt_and_mismatched_accounts(self):
        self.assertEqual(conclusion(self.evaluate())["verdict"],"pass")
        # Same last four digits do not prove that the full beneficiary account is the same.
        findings=self.evaluate(payee_account="000100000000000081",transfer_amount="8,550.00")
        self.assertEqual(conclusion(findings)["verdict"],"reject")
        self.assertIn(("B03","risk"),[(r["rule"],r["status"]) for r in findings])
        formula=next(r for r in findings if r["rule"]=="B04")["calculations"][0]
        self.assertEqual(Decimal(formula["result"]),150)
        self.assertEqual([op["field"] for op in formula["operands"]],["transfer_amount","total"])

    def test_strict_replay_checks_observation_and_overall_verdict(self):
        from jobs import CODE_DIGESTS
        from controls import VERSION
        from verify import replay_rules
        findings = self.evaluate()
        report = {"graph":self.graph, "policy":{**VERSION,"profile":BANK,"code_sha256":CODE_DIGESTS},
                  "findings":findings, "result":conclusion(findings), "calls":{"expert":{"output":{"followups":[]}}}}
        replay_rules(report)
        with self.assertRaises(ValueError):
            replay_rules({**report, "result":{**report["result"],"verdict":"reject"}})
        with self.assertRaises(ValueError):
            replay_rules({**report, "findings":[*findings[:-1],{**findings[-1],"detail":"无依据的结论"}]})
        for name in ("capacity.py","protocol.py"):
            changed = {**report["policy"],"code_sha256":{**CODE_DIGESTS,name:"0"*64}}
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,name):
                replay_rules({**report,"policy":changed})

    def test_masked_pending_changes_and_noncomparable_currency(self):
        for field,value in (("transfer_status","已受理"),("payee","另一供应方"),("paid_on","2026-10-01"),
                            ("currency","美元"),("unit","万元"),("transfer_ref",None),("payment_term","分期付款")):
            with self.subTest(field=field):
                findings=self.evaluate(**{field:value})
                self.assertFalse(any(r.get("calculations") for r in findings))
                self.assertEqual(conclusion(findings)["verdict"],"review")
        masked=self.evaluate(payee_account="****0081")
        self.assertIn(("B03","missing"),[(r["rule"],r["status"]) for r in masked])
        self.assertEqual(conclusion(masked)["verdict"],"review")

    def test_visible_masks_and_field_specific_printed_notes(self):
        rows = (
            ("26XX0042",None,None,True),
            ("0042","交易流水号（尾号）：0042",None,True),
            ("0042","交易流水号：0042（仅显示后四位）",None,True),
            ("0042",None,"银行流水号说明：仅显示后4位",True),
            ("0042",None,"本回单仅显示交易流水号后四位。",True),
            ("0042",None,"收款账户仅显示后四位。",False),
            ("TX-XX-0042",None,None,False),
            ("00000042",None,None,False),
        )
        for ref,quote,note,partial in rows:
            with self.subTest(ref=ref,quote=quote,note=note):
                findings=self.evaluate(transfer_ref=ref,reference_quote=quote,reference_note=note)
                fact=next(f for f in self.graph["facts"] if f["field"]=="transfer_ref")
                self.assertEqual(fact["status"],"anchored")
                self.assertEqual(fact["value"],ref)
                marked=self.graph["transfer_references"]["facts"]
                self.assertEqual(bool(marked),partial)
                if partial:
                    self.assertEqual(marked[0]["fact"],fact["id"])
                    if note:
                        self.assertEqual(marked[0]["lines"][-1]["text"],note)
                edge=next(e for e in self.graph["edges"] if e["from"]=="d02" and e["evidence"]==[fact["id"]])
                self.assertEqual(edge["type"],"incomplete_transfer_ref" if partial else "transfer_ref")
                self.assertEqual([(f["rule"],f["status"]) for f in findings if f["rule"] in {"B05","B04"}],
                                 [("B05","missing"),("B04","missing")] if partial else [("B05","ok"),("B04","ok")])

    def test_confirmed_photo_keeps_visible_tail_and_ignores_another_pages_note(self):
        docs,pages=receipt_material(transfer_ref="0042",reference_quote="交易流水号：尾号0042")
        photo=pages[1]
        photo.update(text="",layer={"type":"image","lines":{}})
        attestations={f"d02/p1/f{i}":{"decision":"confirm"} for i in range(1,len(photo["extraction"]["output"]["facts"])+1)}
        graph=build_graph(docs,pages,attestations)
        marked=graph["transfer_references"]["facts"]
        self.assertEqual([(r["value"],r["lines"]) for r in marked],[("0042",[])])
        findings=execute(graph,BANK)
        self.assertEqual(next(f for f in findings if f["rule"]=="B05")["status"],"missing")
        docs,pages=receipt_material(transfer_ref="0042")
        pages[0]["text"]+="\n回单交易流水号说明：仅显示后四位"
        self.assertEqual(build_graph(docs,pages,{})["transfer_references"]["facts"],[])
