import copy
import unittest

from config import PERFORMANCE
from controls import VERSION, conclusion, execute
from equipment_models import EXCHANGE_FORMAT, EXCHANGE_SINCE, LEGACY, edges, sources, verify
from performance import verify_findings
from test_delivery_batches import contract as batch_contract, receipt as batch_receipt
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material
from test_reinspection import FINAL, FIX, OLD
from verify import verify_model_review_history


ORDER = ("equipment_model", "约定设备型号", "YL-C4")


def received(value):
    return ("equipment_model", "实收设备型号", value)


def findings(graph):
    checks = execute(graph, PERFORMANCE)
    return next(f for f in checks if f["rule"] == "H02"), [f for f in checks if f["rule"] == "H04"], checks


def reviewed_material(groups, index, *, decision="dispute", edit=None, label="实收设备型号"):
    position = next(n for n, row in enumerate(groups[index-1], 1) if row[1] == label)
    ref = f"d{index:02d}/p1/f{position}"
    review = {"decision": decision, "reviewer": "演练审计员", "note": "合成核图记录"}
    if decision == "confirm":
        review["source_check"] = {"fixture": True}
    return material(groups, edit=edit, attestations={ref: review}), ref


class EquipmentModelTests(unittest.TestCase):
    def test_dispute_suspends_both_comparisons_without_losing_the_original_or_other_findings(self):
        for label_field, value in (("equipment_model", "YL-C4"), ("other", "YL-C2")):
            groups = [CONTRACT+[ORDER], RECEIPT+[(label_field, "实收设备型号", value)], WARRANTY, BANK_DOC]
            graph, ref = reviewed_material(groups, 2)
            inspection, phases, checks = findings(graph)
            row, = inspection["equipment_models"]["records"]
            hold, = row["review_holds"]
            self.assertEqual((hold["doc"], hold["line"], hold["facts"], hold["quote"]),
                             ("d02", len(groups[1]), [ref], "实收设备型号："+value))
            self.assertEqual((row["received"]["value"], row["comparison"], inspection["status"]),
                             (value, "unresolved", "missing"))
            self.assertIn(ref, row["evidence"])
            self.assertEqual([s["status"] for s in phases], ["ok","missing","missing"])
            self.assertTrue(all(ref in s["evidence"] for s in phases[1:]))
            self.assertNotEqual(next(f for f in checks if f["rule"]=="H05")["status"], "ok")
            self.assertFalse(edges(checks))

        groups = [CONTRACT+[ORDER], RECEIPT+[received("YL-C4")], WARRANTY, BANK_DOC]
        hot, _ = reviewed_material(groups, 2, edit=lambda i,f,l,v:"柜温8℃" if f=="measured_result" else v)
        inspection, _, checks = findings(hot)
        self.assertEqual((inspection["status"], conclusion(checks)["verdict"]), ("issue","reject"))
        self.assertIn("8", inspection["detail"])
        resolved, _ = reviewed_material(groups, 2, decision="confirm")
        inspection, phases, checks = findings(resolved)
        self.assertNotIn("review_holds", resolved["equipment_model_sources"])
        self.assertEqual((inspection["status"], conclusion(checks)["verdict"]), ("ok","pass"))
        self.assertTrue(all(s["status"]=="ok" for s in phases))

    def test_dispute_follows_specific_batch_or_shared_contract(self):
        groups = [batch_contract()+[ORDER], batch_receipt(1)+[received("YL-C4")],
                  batch_receipt(2)+[received("YL-C4")], WARRANTY, BANK_DOC]
        for index, label, expected in ((3, "实收设备型号", ["ok","ok","missing","missing"]),
                                       (1, "约定设备型号", ["ok","missing","missing","missing"])):
            graph, ref = reviewed_material(groups, index, label=label)
            inspection, phases, checks = findings(graph)
            self.assertEqual([s["status"] for s in phases], expected)
            rows = inspection["equipment_models"]["records"]
            self.assertEqual([r["status"] for r in rows], expected[1:3])
            self.assertEqual([ref in r["evidence"] for r in rows], [s=="missing" for s in expected[1:3]])
            self.assertEqual([e["to"] for e in edges(checks)], ["d02/p1"] if index==3 else [])
        graph, _ = reviewed_material([*groups[:2], groups[2]+[("other","包装编号","P9")], *groups[3:]],
                                     3, label="包装编号")
        self.assertEqual(findings(graph)[0]["equipment_models"]["status"], "ok")
        with_rider = [*groups[:2], groups[2]+[("other","附注","变更第二期付款条件")], *groups[3:]]
        graph, _ = reviewed_material(with_rider, 3)
        self.assertTrue(any(g.get("quote")=="附注：变更第二期付款条件" for g in graph["gaps"]))
        self.assertNotEqual(findings(graph)[1][1]["status"], "ok")

    def test_archived_dispute_is_checked_against_the_journal_at_the_selected_revision(self):
        groups = [CONTRACT+[ORDER], RECEIPT+[received("YL-C4")], WARRANTY, BANK_DOC]
        graph, ref = reviewed_material(groups, 2)
        fact = next(f for f in graph["facts"] if f["id"]==ref)
        fact["attestation"].update(fact=ref, rev=7)
        pages = [{"doc": d["id"], "page": 1, "output": {"facts": [f for f in graph["facts"] if f["doc"]==d["id"]]}}
                 for d in graph["documents"]]
        report = {"graph": graph, "policy": VERSION, "calls": {"pages": pages}}
        original = {"seq": 11, **fact["attestation"]}
        later = {**original, "seq": 12, "rev": 8, "decision": "confirm", "note": "已重新核对"}
        journal = {"attestations": [later, original], "amendments": []}
        verify_model_review_history(report, 8, journal)
        with self.assertRaises(ValueError):
            verify_model_review_history(report, 9, journal)
        forged = copy.deepcopy(report)
        next(f for f in forged["graph"]["facts"] if f["id"]==ref)["attestation"]["note"]="伪造意见"
        with self.assertRaises(ValueError):
            verify_model_review_history(forged, 8, journal)
        forged["graph"]["facts"] = [f for f in forged["graph"]["facts"] if f["id"]!=ref]
        with self.assertRaises(ValueError):
            verify_model_review_history(forged, 8, journal)

    def test_dispute_ledger_and_historical_replay(self):
        groups = [CONTRACT+[ORDER], RECEIPT+[received("YL-C4")], WARRANTY, BANK_DOC]
        def read(doc, page):
            return "\n".join(label+"："+value if label else value for _,label,value in groups[int(doc[1:])-1])
        graph, _ = reviewed_material(groups, 2)
        _, _, checks = findings(graph)
        report = {"graph": graph, "policy": {**VERSION, "profile": PERFORMANCE}, "findings": checks}
        verify(report, read)
        verify_findings(report)
        damaged = copy.deepcopy(report)
        del damaged["graph"]["equipment_model_sources"]["review_holds"]
        with self.assertRaises(ValueError):
            verify(damaged, read)
        damaged = copy.deepcopy(report)
        next(f for f in damaged["findings"] if f["rule"]=="H02")["equipment_models"]["records"][0]["comparison"] = "match"
        with self.assertRaises(ValueError):
            verify_findings(damaged)
        for decision in ("dispute", "confirm"):
            with self.subTest(decision=decision):
                graph, _ = reviewed_material(groups, 2, decision=decision)
                graph["equipment_model_sources"] = sources(graph, read, EXCHANGE_FORMAT)
                _, _, checks = findings(graph)
                graph["edges"].extend(edges(checks))
                for finding in checks:
                    finding["version"] = EXCHANGE_SINCE
                policy = {**VERSION, "profile": PERFORMANCE, "version": EXCHANGE_SINCE, "equipment_models": EXCHANGE_FORMAT}
                old = {"graph": graph, "policy": policy, "findings": checks}
                verify(old, read)
                verify_findings(old)
                if decision=="dispute":
                    with self.assertRaisesRegex(ValueError, "异议"):
                        verify(old, read, signing=True)
                else:
                    verify(old, read, signing=True)

    def test_exact_originals_distinguish_delivered_model_from_quality_and_cash(self):
        for value,status,verdict in (("YL-C4","ok","pass"), ("YL-C2","issue","reject"), ("YL-C*","missing","review"),
                                     ("YL-c4","missing","review"), ("YL-C 4","missing","review"), ("","missing","review")):
            with self.subTest(value=value):
                receipt = RECEIPT + ([received(value)] if value else [])
                g = material([CONTRACT+[ORDER], receipt, WARRANTY, BANK_DOC])
                inspected, phases, all_checks = findings(g)
                models = inspected["equipment_models"]
                self.assertEqual((models["status"],inspected["status"],conclusion(all_checks)["verdict"]), (status,status,verdict))
                self.assertEqual(phases[0]["status"], "ok")
                self.assertEqual([f["status"]=="ok" for f in phases[1:]], [status=="ok"]*2)
                self.assertEqual(len(edges(all_checks)), int(status in ("issue","ok")))
        plain = findings(material([CONTRACT, RECEIPT, WARRANTY, BANK_DOC]))[0]
        self.assertNotIn("equipment_models", plain)

    def test_raw_model_survives_omission_but_unclear_scope_is_held(self):
        rows = [(1,"约定设备型号：YL-C4"),(2,"实收设备型号：YL-C2")]
        g = material([CONTRACT,RECEIPT,WARRANTY,BANK_DOC], omissions=rows)
        check = findings(g)[0]["equipment_models"]
        self.assertEqual(check["status"], "issue")
        self.assertFalse(check["ordered"]["facts"])
        for extra in ((1,"替代型号约定：经书面同意可换同等型号"),(2,"铭牌说明：本台系代用设备"),
                      (1,"约定设备型号：YL-C3"),(2,"实收设备型号：YL-C7")):
            uncertain = material([CONTRACT,RECEIPT,WARRANTY,BANK_DOC], omissions=rows+[extra])
            case = findings(uncertain)
            self.assertEqual(case[0]["equipment_models"]["status"], "missing")
            self.assertFalse(edges(case[2]))
        other = material([CONTRACT+[ORDER],RECEIPT+[received("YL-C2")],WARRANTY,BANK_DOC],
                         lambda i,f,l,v: "YL-929" if i==2 and f=="contract_id" else v)
        self.assertEqual(findings(other)[0]["equipment_models"]["status"], "missing")
        scan = copy.deepcopy(g)
        scan["equipment_model_sources"]["pages"][1]["text_only"]=False
        self.assertEqual(findings(scan)[0]["equipment_models"]["status"], "missing")

    def test_approval_and_temperature_survive_matching_models(self):
        for change,quality,wanted in (("board",False,"review"),("measurement",True,"reject")):
            def edit(i,f,l,v):
                if i==1 and f=="effect_clause" and not quality:
                    return "本合同自双方盖章并经甲方董事会批准后生效"
                return "柜温8℃" if i==2 and f=="measured_result" and quality else v
            g=material([CONTRACT+[ORDER],RECEIPT+[received("YL-C4")],WARRANTY,BANK_DOC],edit)
            inspection,phases,checks=findings(g)
            self.assertEqual(inspection["equipment_models"]["status"],"ok")
            self.assertEqual(inspection["status"],"issue" if quality else "ok")
            self.assertEqual(conclusion(checks)["verdict"],wanted)
            self.assertEqual(phases[0]["status"]=="ok",quality)
            self.assertNotEqual(phases[1]["status"],"ok")

    def test_independent_batches_keep_their_own_model_and_period(self):
        g = material([batch_contract()+[ORDER],batch_receipt(1)+[received("YL-C4")],
                      batch_receipt(2)+[received("YL-C2")],WARRANTY,BANK_DOC])
        inspected, phases, _ = findings(g)
        self.assertEqual([r["status"] for r in inspected["batch_acceptance"]["batches"]],["ok","issue"])
        self.assertEqual([r["status"] for r in phases], ["ok","ok","risk","risk"])
        first=inspected["equipment_models"]["records"][0]
        self.assertFalse(any(ref.startswith("d03/") for ref in first["evidence"]))

    def test_archived_rule_compares_text_not_just_transcribed_fields(self):
        g = material([CONTRACT+[ORDER],RECEIPT+[received("YL-C2")],WARRANTY,BANK_DOC])
        check,_,fs=findings(g)
        g["edges"].extend(edges(fs))
        p={"graph":g,"policy":{**VERSION,"profile":PERFORMANCE},"findings":fs}
        def read(doc,page):
            return "\n".join(f["quote"] for f in g["facts"] if f["doc"]==doc and f["page"]==page)
        verify(p,read)
        verify_findings(p)
        for target in ("value","edge","source","marker"):
            damaged=copy.deepcopy(p)
            if target=="value":
                next(f for f in damaged["findings"] if f["rule"]=="H02")["equipment_models"]["records"][0]["received"]["value"]="YL-C4"
            elif target=="edge":
                next(e for e in damaged["graph"]["edges"] if e["type"]=="equipment_model_comparison")["received_line"]=1
            elif target=="source":
                damaged["graph"]["equipment_model_sources"]["lines"].pop()
            else:
                del damaged["policy"]["equipment_models"]
            with self.assertRaises(ValueError):
                verify_findings(damaged) if target=="value" else verify(damaged,read)

    def test_retest_role_follows_the_linked_defect_and_keeps_the_physical_handover_open(self):
        for generic in (True,False):
            retest = [("acceptance","","验收报告"),*FINAL[1:]] if generic else FINAL
            for begin,end,status,decision in (("YL-C2","YL-C4","risk","replacement_unverified"),
                                               ("YL-C4","YL-C2","issue","final_differs"),
                                               ("YL-C4","YL-C4","ok","same_model"),
                                               ("YL-C2","YL-C*","risk","model_unresolved")):
                with self.subTest(generic=generic,begin=begin,end=end):
                    graph=material([CONTRACT+[ORDER],OLD+[received(begin)],FIX,retest+[received(end)],WARRANTY,BANK_DOC],
                                   lambda i,f,l,v:"2026-09-27" if f=="paid_on" else v)
                    inspected,phases,_=findings(graph)
                    comparison=inspected["equipment_models"]
                    self.assertEqual(comparison["sequence"],{"record_chain_state":"closed","outcome":decision})
                    self.assertEqual([r["inspection_role"] for r in comparison["records"]],["original","final"])
                    self.assertEqual((inspected["status"],comparison["status"]),(status,status))
                    self.assertEqual(inspected["reinspection"]["state"],"closed" if status=="ok" else "open")
                    self.assertEqual(phases[0]["status"],"ok")
                    self.assertEqual(phases[1]["status"]=="ok",status=="ok")
                    graph["equipment_model_sources"]["format"]=LEGACY
                    previous=findings(graph)[0]["equipment_models"]
                    self.assertNotIn("sequence",previous)
                    if begin=="YL-C2" and end=="YL-C4":
                        self.assertEqual(previous["status"],"issue" if generic else "risk")
        broken=material([CONTRACT+[ORDER],OLD+[received("YL-C2")],FIX,FINAL+[received("YL-C4")]],
                        lambda i,f,l,v:"QX-02" if i==4 and f=="defect_number" else v)
        comparison=findings(broken)[0]["equipment_models"]
        self.assertEqual(comparison["sequence"],{"record_chain_state":"open","outcome":"links_pending"})
