import copy
import unittest

from config import PERFORMANCE
from controls import VERSION, conclusion, execute
from graph import build_graph
from performance import verify_findings
from stage_payments import edges, verify
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


def fixture(amounts=("25000.00","35000.00"),refs=("TR-001","TR-002"),dates=("2026-09-21","2026-09-22"),
            uses=("第二期","第二期"),contract_edits=None,edits=None,extras=(),omissions=()):
    agreement=CONTRACT+[("total","含税总额","100000.00"),("currency","币种","人民币"),("unit","金额单位","元")]
    agreement=[(k,label,(contract_edits or {}).get(k,v)) for k,label,v in agreement]
    groups=[agreement,RECEIPT,WARRANTY]
    for i,(amount,ref,paid,used) in enumerate(zip(amounts,refs,dates,uses)):
        values={"paid_on":paid,"payment_designation":used,**(edits or {}).get(i,{})}
        bank=BANK_DOC+[("transfer_amount","付款金额",amount),("transfer_ref","交易流水号",ref),
                       ("currency","币种","人民币"),("unit","金额单位","元")]
        groups.append([(k,l,values.get(k,v)) for k,l,v in bank if values.get(k,v) is not None])
    return material(groups+list(extras),omissions=omissions)


def checks(g):
    return [f for f in execute(g,PERFORMANCE) if f["rule"]=="H06"]


class StageTransferTests(unittest.TestCase):
    def test_comparison_counts_only_the_submitted_period_and_keeps_the_old_timing_scope(self):
        for amounts,state,status,seen,delta in ((("25000","35000"),"balanced","ok","60000.00","0.00"),
                                                (("25000","15000"),"partial","missing","40000.00","-20000.00"),
                                                (("40000","30000"),"over","risk","70000.00","10000.00")):
            g=fixture(amounts)
            f,=checks(g)
            entry=f["stage_payments"]
            self.assertEqual((entry["state"],f["status"],entry["seen"],entry["expected"],entry["difference"]),
                             (state,status,seen,"60000.00",delta))
            self.assertEqual([x["status"] for x in entry["timing"]],["ok","ok"])
            self.assertEqual(f["stage"]["share"],"60")
            self.assertEqual([e["to"] for e in edges([f])],[r["inputs"]["transfer_amount"]["ref"] for r in entry["records"]])
            self.assertIn(entry["base"]["currency"]["ref"],f["evidence"])
            del g["stage_payment_sources"]
            self.assertEqual(conclusion(execute(g,PERFORMANCE))["verdict"],"pass")
        by_stage=checks(fixture(("30000","60000"),uses=("第一期","第2期")))
        self.assertEqual([(f["stage"]["name"],f["stage_payments"]["seen"],len(f["stage_payments"]["records"])) for f in by_stage],
                         [("第一期","30000.00",1),("第二期","60000.00",1)])
        self.assertEqual(checks(fixture(("60000",))),[])

    def test_duplicates_ambiguous_periods_returns_and_conflicts(self):
        f,=checks(fixture(("30000","30000"),("TR-001","TR-001"),("2026-09-21",)*2))
        entry=f["stage_payments"]
        self.assertEqual((entry["seen"],entry["difference"],entry["records"][1]["duplicate_of"]),("30000.00","-30000.00","d04"))
        self.assertEqual(len(edges([f])),1)
        for g in (fixture(refs=("TR-001","TR-001")),fixture(refs=("TR-001","TR-001"),uses=("第一期","第二期")),
                  fixture(uses=("第二期","第一期及第二期")),fixture(refs=("TR-001","***002")),
                  fixture(omissions=[(5,"银行附注：本笔后来已冲正，净额另核")]),
                  fixture(edits={1:{"currency":"美元"}}),fixture(edits={0:{"unit":None}}),
                  fixture(edits={1:{"transfer_amount":"35 000.00"}}),fixture(edits={1:{"payer":"另一单位"}}),
                  fixture(contract_edits={"total":"100000.01"})):
            results=checks(g)
            self.assertTrue(results)
            self.assertTrue(all(f["stage_payments"]["seen"] is None and f["status"]=="missing" for f in results))
            self.assertEqual(edges(results),[])

    def test_existing_approval_and_date_findings_survive_matching_money(self):
        for g,status,condition,timing in ((fixture(dates=("2026-09-15","2026-09-22")),"risk","ok",["risk","ok"]),
                (fixture(contract_edits={"effect_clause":"本合同自双方盖章并经甲方董事会批准后生效"}),"missing","missing",["missing","missing"])):
            f,=checks(g)
            e=f["stage_payments"]
            self.assertEqual((e["state"],e["condition"],e["seen"],f["status"]),("balanced",condition,"60000.00",status))
            self.assertEqual([r["status"] for r in e["timing"]],timing)
            self.assertTrue(all(r["receipt_ref"] in f["evidence"] for r in e["timing"]))
            self.assertNotEqual(conclusion(execute(g,PERFORMANCE))["verdict"],"pass")

    def test_two_receipts_printed_on_one_page_or_bound_in_one_file_require_page_assignment(self):
        original=fixture()
        docs=[d for d in original["documents"] if d["id"] not in ("d04","d05")]
        docs.append({"id":"bankfile","name":"回单册.pdf","sha256":"synthetic"})
        for combined in (True,False):
            pages,signs={},{}
            for f in original["facts"]:
                bank=f["doc"] in ("d04","d05")
                source,n=("bankfile",1 if combined or f["doc"]=="d04" else 2) if bank else (f["doc"],f["page"])
                p=pages.setdefault((source,n),{"doc":source,"number":n,"sha256":"render","text":"",
                    "layer":{"type":"text","clause_text_only":True,"lines":{}},
                    "extraction":{"output":{"quality":"readable","facts":[]}}})
                records=p["extraction"]["output"]["facts"]
                records.append({k:f[k] for k in ("field","value","quote","region")})
                idx=len(records)
                p["text"]+=f["quote"]+"\n"
                p["layer"]["lines"][str(idx)]=[[0,.1,.8,.2]]
                if f["attestation"]:
                    signs[f"{source}/p{n}/f{idx}"]=f["attestation"]
            g=build_graph(docs,list(pages.values()),signs)
            g["profile"]=PERFORMANCE
            self.assertEqual(g["stage_payment_sources"]["ambiguous_units"],["bankfile"])
            fs=checks(g)
            self.assertTrue(fs and all(f["stage_payments"]["seen"] is None and f["status"]=="missing" for f in fs))

    def test_replay_detects_wrong_amount_operand_wrong_stage_and_missing_source(self):
        g=fixture()
        fs=execute(g,PERFORMANCE)
        g["edges"].extend(edges(fs))
        report={"graph":g,"policy":{**VERSION,"profile":PERFORMANCE},"findings":fs}
        def read(doc,n):
            return "\n".join(f["quote"] for f in g["facts"] if f["doc"]==doc and f["page"]==n)
        verify(report,read)
        verify_findings(report)
        for mode in ("total","period","edge","page","marker"):
            altered=copy.deepcopy(report)
            f=next(f for f in altered["findings"] if f["rule"]=="H06")
            if mode=="total":
                f["stage_payments"]["seen"]="42000.00"
            if mode=="period":
                f["stage"]["name"]="第三期"
            if mode=="edge":
                next(e for e in altered["graph"]["edges"] if e["type"]=="stage_transfer_operand")["to"]="d05/p1/f1"
            if mode=="marker":
                del altered["policy"]["stage_payments"]
            with self.assertRaises(ValueError):
                if mode in ("total","period"):
                    verify_findings(altered)
                else:
                    verify(altered,(lambda d,n:read(d,n)+"多") if mode=="page" else read)
