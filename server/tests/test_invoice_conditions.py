import copy
import unittest

import invoice_conditions as condition
from config import PERFORMANCE
from controls import VERSION, execute
from performance import verify_findings
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


NUMBER = "98123456789012345678"
RIDER = "验收款支付前提：买方收到供应方就本合同开具的发票"
INLINE = "最终验收合格且采购方收到本合同对应的发票后支付60%"
INVOICE = [("invoice","","采购发票"), *CONTRACT[1:4], ("invoice_id","发票号码",NUMBER), ("issued_on","开票日期","2026-09-18")]
ACK = [("received_invoice_id","签收发票号码",NUMBER), ("invoice_received_on","收票日期","2026-09-20"),
       ("invoice_received_seal","收票方签章","演练甲（已盖章）")]


def fixture(*, clause=RIDER, ack=ACK, invoices=None, edit=None, extra=(), confirmed=True):
    contract = [(f,k,INLINE if not clause and k=="第二期" else v) for f,k,v in CONTRACT]
    groups = [contract, [*RECEIPT,*ack], WARRANTY, BANK_DOC, *(invoices if invoices is not None else [INVOICE])]
    omissions = [(1,clause)] if clause else []
    edits = {f"d02/p1/f{len(RECEIPT)+3}":{"decision":"confirm","source_check":{"fixture":True}}} if confirmed and ack else {}
    graph = material(groups, edit=edit, omissions=omissions+list(extra), attestations=edits)
    return graph, execute(graph, PERFORMANCE)


def second(f):
    return next(x for x in f if x["rule"]=="H04" and x["stage"]["name"]=="第二期")


def paid(f):
    return next(x for x in f if x["rule"]=="H05")


class InvoiceConditionsTests(unittest.TestCase):
    def test_unextracted_separate_rider_and_invoice_without_buyer_receipt(self):
        g, f = fixture(ack=[])
        phases = [x for x in f if x["rule"]=="H04"]
        self.assertEqual([x["status"] for x in phases], ["ok","missing","ok"])
        self.assertNotIn("invoice_receipt", phases[0])
        self.assertNotIn("invoice_receipt", phases[2])
        self.assertEqual(paid(f)["status"], "missing")
        gate = second(f)["invoice_receipt"]
        self.assertTrue(gate["scope_clear"])
        self.assertEqual((gate["invoice"]["status"],gate["receipt"]["status"]), ("ok","missing"))
        self.assertEqual(gate["clauses"][0]["quote"], RIDER)
        self.assertEqual(gate["clauses"][0]["line"], len(CONTRACT)+1)
        self.assertEqual(gate["clauses"][0]["facts"], [])
        self.assertIn("d01/p1", second(f)["evidence"])
        self.assertTrue(any(e["type"]=="stage_invoice_clause" and e["to"]=="d01/p1" for e in g["edges"]))

    def test_independent_and_inline_clauses_bind_to_signed_evidence(self):
        for clause in (None, RIDER, "第二期付款前提：采购方须收到本合同对应的发票"):
            with self.subTest(clause=clause):
                _, f = fixture(clause=clause)
                self.assertEqual((second(f)["status"],paid(f)["status"]), ("ok","ok"))
                gate = second(f)["invoice_receipt"]
                for item in (gate["receipt"],gate["invoice"]):
                    self.assertTrue(all(v in second(f)["evidence"] for k,v in item.items() if k.endswith("_ref")))
                self.assertEqual(gate["receipt"]["received_on"], "2026-09-20")

    def test_date_order_and_existing_quality_failure(self):
        for date, verdict in (("2026-09-22","risk"),("2026-09-21","missing"),("2026-09-17","missing"),
                              ("2026-09-2 0","missing")):
            _, f = fixture(edit=lambda i,field,k,v: date if field=="invoice_received_on" else v)
            self.assertEqual(paid(f)["status"], verdict, date)
        _, f = fixture(edit=lambda i,field,k,v: "柜温8℃" if field=="measured_result" else v)
        self.assertEqual(second(f)["status"], "risk")
        self.assertEqual(second(f)["invoice_receipt"]["status"], "ok")

    def test_identity_mask_qualifications_and_multiplicity(self):
        for options in ({"confirmed":False}, {"invoices":[]}, {"invoices":[INVOICE,INVOICE]},
                        {"edit":lambda i,f,k,v: "演练乙（已盖章）" if f=="invoice_received_seal" else v},
                        {"edit":lambda i,f,k,v: "YL-999" if i==5 and f=="contract_id" else v},
                        {"edit":lambda i,f,k,v: "00123456789012345678" if f=="received_invoice_id" else v},
                        {"edit":lambda i,f,k,v: NUMBER[:5]+" "+NUMBER[5:] if f=="invoice_id" else v},
                        {"extra":[(2,"备注：上述发票已退回")]}, {"extra":[(2,"签收发票号码："+NUMBER)]},
                        {"extra":[(5,"附注：本张已作废")]}, {"extra":[(1,"并须同时提供履约保函")]},
                        {"extra":[(2,"上述签认仅供内部登记")]}):
            with self.subTest(options=options):
                _, f = fixture(**options)
                self.assertEqual(second(f)["status"], "missing")
                self.assertEqual(paid(f)["status"], "missing")

    def test_unresolved_conditions_remain_visible(self):
        for clause, statuses in (("验收款须先票后款",["ok","missing","ok"]),
                                 ("付款条件：先票后款",["missing"]*3),
                                 ("收票约定：收到发票后方可支付验收款",["ok","missing","ok"]),
                                 (RIDER+"且金额足额",["ok","missing","ok"])):
            _, f = fixture(clause=clause)
            self.assertEqual([x["status"] for x in f if x["rule"]=="H04"], statuses)
            self.assertFalse(second(f)["invoice_receipt"]["scope_clear"])

    def test_archive_and_legacy_signature(self):
        g, f = fixture()
        # Re-read the files independently of the extracted graph, as archive and sign-off do.
        originals = [CONTRACT, [*RECEIPT,*ACK], WARRANTY, BANK_DOC, INVOICE]
        pages = {f"d{i:02d}": "\n".join([k+"："+v if k else v for _,k,v in group] +
                                        ([RIDER] if i==1 else [])) for i,group in enumerate(originals,1)}
        read = lambda doc,page: pages[doc]
        paper = {"graph":g, "findings":f, "policy":{**VERSION, "profile":PERFORMANCE}}
        condition.verify(paper, read)
        verify_findings(paper)
        bad = copy.deepcopy(paper)
        second(bad["findings"])["invoice_receipt"]["receipt"]["received_on"] = "2026-09-01"
        with self.assertRaises(ValueError):
            verify_findings(bad)
        bad = copy.deepcopy(paper)
        bad["graph"]["invoice_receipt_sources"]["lines"].pop()
        with self.assertRaises(ValueError):
            condition.verify(bad, read)
        old = copy.deepcopy(paper)
        del old["policy"]["invoice_receipt_conditions"]
        old["policy"]["version"] = "2026.11.25.22"
        old["graph"].pop("invoice_receipt_sources")
        old["graph"]["edges"] = [e for e in old["graph"]["edges"] if e["type"]!="stage_invoice_clause"]
        old["findings"] = execute(old["graph"], PERFORMANCE)
        condition.verify(old, read)
        with self.assertRaisesRegex(ValueError, "重新审计"):
            condition.verify(old, read, signing=True)
