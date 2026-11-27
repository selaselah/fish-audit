import unittest
from copy import deepcopy
from unittest.mock import patch

from controls import execute
from performance import Material, verify_findings
from test_acceptance_execution import printed
from test_acceptance_originals import filed
from test_performance import material
from test_warranty_terms import audit
import warranty_dates as dates


def report_for(value, *, paid="2026-11-22", designation="第三期", omissions=()):
    def fixture():
        return audit(edit=lambda i,k,l,v:{"warranty_release":value,"paid_on":paid,"payment_designation":designation}.get(k,v),
                     omissions=omissions)
    template=fixture()
    template["facts"].extend({"doc":"d03","quote":line} for unit,line in omissions if unit==3)
    return filed(printed(template,"d03"),fixture,"d03",".pdf",render=True)


class WrittenWarrantyDates(unittest.TestCase):
    def test_only_complete_source_lines_and_unbroken_digits_yield_a_calendar_date(self):
        def reading(raw, transcription=None):
            line = "质保期满确认："+raw+"双方确认质保期已满"
            fact = {"field":"warranty_release","status":"anchored","quote":line if transcription is None else transcription,
                    "source_line":{"text":line,"rects":[[0,0,1,1]],"number":7},"value":line,
                    "id":"d02/p1/f5","doc":"d02","page":1}
            return dates.read_date(fact,dates.CERTIFICATE_LABELS,dates.STATEMENT)
        for raw in ("2024 年 2 月 29 日","２０２４\u3000年２月２９日","2024 / 02 / 29","2024-2-29","2024．02．29"):
            with self.subTest(raw=raw):
                found = reading(raw)
                self.assertEqual((found["literal"],found["iso"],found["line"]),(raw,"2024-02-29",7))
        for raw in ("20 24年2月29日","2024年2月2 9日","2026 年 2 月 29 日","2024年00月1日",
                    "2024/02-29","2024/02/","2024年2月29日或3月1日","预计2024年2月29日","2024\t年2月29日"):
            with self.subTest(raw=raw):
                self.assertIsNone(reading(raw))
        for wrong in ("签发日期：2024年2月29日","质保期满确认：2024年2月28日双方确认质保期已满",
                      "质保期满确认：2024年2月2 9日双方确认质保期已满"):
            self.assertIsNone(reading("2024 年 2 月 29 日",wrong))

    def test_bank_record_uses_its_own_phase_date_and_graph_witness(self):
        for paid,days,status in (("2026-11-20",-1,"risk"),("2026-11-21",0,"missing"),("2026-11-22",1,"missing")):
            with self.subTest(paid=paid):
                paper,text = report_for("2026 年 11 月 21 日双方确认质保期已满",paid=paid)
                bank, = [f for f in paper["findings"] if f["rule"]=="H05"]
                stage, = [f for f in paper["findings"] if f["rule"]=="H04" and f.get("warranty_check")]
                check = bank["warranty_check"]
                reading = check["certificate"]["date"]
                self.assertEqual((reading["literal"],reading["iso"],check["stated_on"],check["confirmed_on"]),
                                 ("2026 年 11 月 21 日","2026-11-21","2026-11-21",None))
                pair = bank["warranty_payment"]["comparison"]
                self.assertEqual((pair["days"],pair["bank"]["doc"],pair["bank"]["literal"],bank["status"]),(days,"d04",paid,status))
                self.assertTrue({stage["stage"]["clause_ref"],"warranty-pdf/d03",reading["ref"],pair["bank"]["ref"]} <= set(pair["evidence"]))
                self.assertTrue(set(pair["evidence"])<=set(bank["evidence"]))
                self.assertNotIn(pair["bank"]["ref"],stage["evidence"])
                self.assertFalse(any(reading["ref"] in f["evidence"] for f in paper["findings"] if f["rule"]=="H04" and f is not stage))
                edges=dates.edges(paper["findings"])
                self.assertEqual([(e["from"],e["to"]) for e in edges],[(reading["ref"],pair["bank"]["ref"])])
                paper["graph"]["edges"].extend(edges)
                dates.verify(paper,text)
                for mode in ("date","delta","row","edge","marker"):
                    with self.subTest(mode=mode), self.assertRaises(ValueError):
                        changed=deepcopy(paper)
                        h05=next(f for f in changed["findings"] if f["rule"]=="H05")
                        if mode=="date":
                            h05["warranty_check"]["certificate"]["date"]["literal"]="2026年11月1日"
                            verify_findings(changed)
                        elif mode=="delta":
                            h05["warranty_payment"]["comparison"]["days"]=12
                            verify_findings(changed)
                        else:
                            if mode=="row": changed["graph"][dates.KEY]["lines"][0]["quote"]="付款日期：1999年12月1日"
                            if mode=="edge": changed["graph"]["edges"].remove(edges[0])
                            if mode=="marker": changed["policy"].pop("warranty_dates")
                            dates.verify(changed,text)

    def test_competing_dates_and_broken_rows_do_not_create_a_payment_interval(self):
        for value, omissions in (("2026年11月2 1日双方确认质保期已满",()),
                ("预计2026年11月21日双方确认质保期已满",()),
                ("2026年11月21日双方确认质保期已满",[(3,"质保期满确认：2026年11月25日质保期已满")]),
                ("2026年11月21日双方确认质保期已满",[(4,"交易日期：2026年11月25日")])):
            with self.subTest(value=value,omissions=omissions):
                paper,_=report_for(value,omissions=omissions)
                bank,=[f for f in paper["findings"] if f["rule"]=="H05"]
                self.assertIsNone(bank.get("warranty_payment",{}).get("comparison"))
                self.assertFalse(dates.edges(paper["findings"]))
                if not omissions or omissions[0][0]==3:
                    stage=next(f for f in paper["findings"] if f["rule"]=="H04" and f.get("warranty_check"))
                    self.assertIsNone(stage["warranty_check"]["stated_on"])
        paper,_=report_for("2026年11月21日双方确认质保期已满",designation="第二期")
        self.assertFalse(any(f.get("warranty_payment") for f in paper["findings"]))

    def test_title_misclassification_requires_the_same_bound_physical_heading(self):
        paper,_=report_for("2026年11月21日双方确认质保期已满")
        g=paper["graph"]
        title=next(f for f in g["facts"] if f["field"]=="warranty")
        item={**title,"id":"d03/p1/f99","status":"visual","field":"warranty_release"}
        g["facts"].append(item)
        self.assertEqual(dates.certificate(g,Material(g,"d03"))["heading_refs"],[title["id"],item["id"]])
        for k,v in (("quote","第二次期满"),("page",2),("page_sha256","another-page")):
            with self.subTest(field=k),patch.dict(item,{k:v}):
                self.assertIsNone(dates.certificate(g,Material(g,"d03")))

    def test_same_installment_can_have_two_independently_dated_receipts(self):
        def two(groups,edit,**opts):
            def values(i,k,l,v):
                return "2026-11-21" if i==5 and k=="paid_on" else edit(i,k,l,v)
            return material([*groups,groups[-1]],values,**opts)
        with patch("test_warranty_terms.material",two):
            paper,_=report_for("2026年11月21日双方确认质保期已满")
        pairs=[f["warranty_payment"]["comparison"] for f in paper["findings"] if f["rule"]=="H05"]
        self.assertEqual([(p["bank"]["doc"],p["days"]) for p in pairs],[("d04",1),("d05",0)])
        self.assertNotIn(pairs[0]["bank"]["ref"],pairs[1]["evidence"])

    def test_legacy_rendering_keeps_the_issued_date_and_marker(self):
        paper,text=report_for("2026 年 11 月 21 日双方确认质保期已满")
        g=paper["graph"]; del g[dates.KEY]
        del paper["policy"]["warranty_dates"]
        paper["policy"]["version"]="2026.11.27.13"
        with patch("controls.RULE_VERSION",paper["policy"]["version"]):
            paper["findings"]=execute(g,paper["policy"]["profile"])
        w=next(f["warranty_check"] for f in paper["findings"] if f.get("warranty_check"))
        self.assertIsNone(w["stated_on"])
        self.assertNotIn("date",w["certificate"])
        dates.verify(paper,text)
