import copy
import unittest

from acceptance_authority import LEGACY_FORMAT, page_evidence, verify_sources, witness_edges
from controls import VERSION, execute
from performance import compute, verify_findings
from test_acceptance_authority import JOINT, contract, sign
from test_performance import BANK_DOC, RECEIPT, WARRANTY, material


DATES = ("周宁签认日期：2026年9月20日", "林岚签认日期：2026年9月25日")


def example(*, paid="2026-09-22", dates=DATES, names=("周宁","林岚"), phase="第二期", extra=(), edit=None, confirm=True):
    records = [contract(JOINT), sign(RECEIPT, *names), WARRANTY, BANK_DOC, *extra]
    def change(i, field, label, value):
        value = {"paid_on": paid, "payment_designation": phase}.get(field, value) if i == 4 else value
        return edit(i, field, label, value) if edit else value
    graph = material(records, change, confirm=confirm, omissions=[(2,s) for s in dates])
    texts = {d["id"]: "\n".join([*(f["quote"] for f in graph["facts"] if f["doc"] == d["id"]),
                                 *(dates if d["id"] == "d02" else ())]) for d in graph["documents"]}
    return graph, lambda doc, page: texts[doc]


def payment(graph):
    return next(f for f in compute(graph) if f["rule"] == "H05")


class SignerTimingTests(unittest.TestCase):
    def test_only_last_named_date_controls_the_comparison(self):
        for paid, state, days, status in (("2026-09-22","before",-3,"risk"), ("2026-09-25","same_day",0,"missing"),
                                          ("2026-09-26","after",1,"missing")):
            with self.subTest(paid=paid):
                g, _ = example(paid=paid, dates=DATES[::-1])
                f = payment(g)
                t = f["signer_timing"]
                self.assertEqual((t["state"],t["days"],t["latest_on"],f["status"]), (state,days,"2026-09-25",status))
                self.assertTrue(set([*t["rows"],t["paid_ref"],t["stage_ref"],t["clause_ref"]]).issubset(f["evidence"]))
                self.assertEqual([f["status"] for f in compute(g) if f["rule"]=="H02"], ["missing"])

    def test_ambiguous_and_absent_dates_and_unchecked_people_require_review(self):
        for dates in ((), DATES[:1], DATES + (DATES[1],), (DATES[0], "张锐签字日期：2026-09-25"),
                      (DATES[0], "林岚签字日期：2026-02-30"), (DATES[0], "林岚签认日期：2026-09-2 5"),
                      (DATES[0], "林岚签署日期：2026年9月25日 10:30"), (DATES[0], "林岚签认日期：待补")):
            with self.subTest(dates=dates):
                g,_ = example(dates=dates)
                f = payment(g)
                self.assertEqual((f["signer_timing"]["state"],f["signer_timing"]["latest_on"],f["status"]), ("incomplete",None,"missing"))
        for kwargs in ({"names":("周宁","验收负责人")}, {"confirm":False}, {"dates":DATES+("备注：补签已撤回",)}):
            f = payment(example(**kwargs)[0])
            self.assertIsNone(f["signer_timing"]["days"])
            self.assertNotEqual(f["status"],"ok")

    def test_only_corresponding_final_acceptance_payment_is_compared(self):
        g,_ = example(phase="第一期")
        self.assertNotIn("signer_timing",payment(g))
        g,_ = example(edit=lambda i,k,l,v:"演练丙" if i==4 and k=="payee" else v)
        self.assertNotIn("signer_timing",payment(g))
        for kwargs in ({"edit":lambda i,k,l,v:"YL-333" if i==2 and k=="contract_id" else v},
                       {"extra":[[("other","","补充协议待辨")]]}):
            self.assertEqual(payment(example(**kwargs)[0])["signer_timing"]["state"],"scope")
        g,_ = example(extra=[BANK_DOC])
        transfers = [f for f in compute(g) if f["rule"]=="H05"]
        self.assertEqual([(f["signer_timing"]["bank"],f["signer_timing"]["days"]) for f in transfers],[("d04",-3),("d05",-4)])

    def test_qualifications_and_unverified_dates_keep_their_own_weight(self):
        g,_ = example(paid="2026-09-26", edit=lambda i,k,l,v:"不合格" if k=="acceptance_result" else v)
        findings = compute(g)
        f = next(f for f in findings if f["rule"] == "H05")
        self.assertEqual(f["signer_timing"]["state"], "after")
        self.assertNotEqual(f["status"], "ok")
        self.assertEqual(next(f["status"] for f in findings if f["rule"]=="H02"),"issue")
        g,_ = example()
        source = g["acceptance_authority_sources"]
        source["dates"][0]["disputed"] = True
        self.assertEqual(payment(g)["signer_timing"]["state"], "incomplete")
        source["dates"][0]["disputed"] = False
        source["pages"][-1]["text_only"] = False
        self.assertEqual(payment(g)["signer_timing"]["state"], "scope")

    def test_original_lines_conclusions_and_legacy_replay(self):
        g, read = example()
        def report(graph, version):
            findings = execute(graph,graph["profile"])
            graph["edges"].extend(witness_edges(findings))
            return {"policy":{**VERSION,"acceptance_authority":version,"profile":graph["profile"]}, "graph":graph, "findings":findings}
        paper = report(g,g["acceptance_authority_sources"]["format"])
        verify_sources(paper,read)
        verify_findings(paper)
        for target in ("row","edge","outcome","policy"):
            altered = copy.deepcopy(paper)
            if target == "outcome":
                next(f for f in altered["findings"] if f["rule"]=="H05")["signer_timing"]["days"] = 3
                with self.assertRaises(ValueError): verify_findings(altered)
                continue
            elif target == "row":
                altered["graph"]["acceptance_authority_sources"]["dates"][0]["day"] = "2026-09-01"
            elif target == "edge":
                next(e for e in altered["graph"]["edges"] if e["type"]=="signer_date_source")["from"]="d01/p1"
            else:
                altered["policy"]["acceptance_authority"] = LEGACY_FORMAT
            with self.assertRaises(ValueError): verify_sources(altered,read)
        old = copy.deepcopy(g)
        old["acceptance_authority_sources"] = page_evidence(old,read,LEGACY_FORMAT)
        old["nodes"] = [n for n in old["nodes"] if n["type"] != "acceptance_signer_date"]
        old["edges"] = [e for e in old["edges"] if e["type"] not in ("signer_date_source","named_acceptance_signature")]
        legacy = report(old,LEGACY_FORMAT)
        legacy["policy"]["version"] = "2026.11.26.20"
        for f in legacy["findings"]: f["version"] = legacy["policy"]["version"]
        verify_sources(legacy,read)
        verify_findings(legacy)
        with self.assertRaisesRegex(ValueError,"旧版"): verify_sources(legacy,read,signing=True)
