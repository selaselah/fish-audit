import copy
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import advance_guarantee as guarantee
from config import CaseError, PERFORMANCE
from controls import execute
from graph import build_graph
from performance import verify_findings
from storage import Store, encode
from test_advance_guarantee import ACK, BANK, LETTER, RIDER, bank_day, issued, layout, specimen
from test_performance import BANK_DOC


TERM = "保函有效期要求：第一期预付款的付款日须在本合同项下预付款保函的有效期内"
START = "保函有效期自：2026年9月2日"
END = "保函有效期至（含当日）：2026年9月4日"
NOTE = "展期说明：延期申请已提交，尚待开立机构确认"
RECEIPT = (*ACK[:-1],"签收日期：2026年9月3日")


def sample(*, term=TERM, start=START, end=END, tail=(), receipt=RECEIPT, bank=None, extras=(), omitted=(), transform=None, names=None):
    original=(*LETTER,*(s for s in (start,end) if s),*tail)
    def build(docs,pages,attestations):
        for doc in docs:
            doc["name"]=(names or {}).get(doc["id"],doc["name"])
        if transform:
            transform(pages,attestations)
        return build_graph(docs,pages,attestations)
    with patch("test_performance.build_graph",side_effect=build):
        return specimen(letter=original,receipt=receipt,bank=bank or bank_day("2026-09-05"),extras=extras,
                        omitted=[*([(1,term)] if term else []),*omitted])


def checks(g,rule):
    return [f for f in execute(g,PERFORMANCE) if f["rule"]==rule]


def proof(g,rule="H05"):
    return checks(g,rule)[0]["advance_guarantee"]


class GuaranteePeriodTests(unittest.TestCase):
    def test_separate_receipt_and_period_for_the_four_printed_variants(self):
        for end,tail,state,status in ((END,(),"expired","risk"),(END.replace("4日","5日"),(),"covered","missing"),
                ("保函有效期至：2026年9月5日",(),"end_unspecified","missing"),(END,(NOTE,),"extension_review","missing")):
            with self.subTest(state=state):
                g,_=sample(end=end,tail=tail)
                h4=checks(g,"H04")
                self.assertEqual(checks(g,"H03")[0]["status"],"ok")
                self.assertEqual([f["status"] for f in h4],["missing","ok","ok"])
                self.assertTrue(all("advance_guarantee" not in f for f in h4[1:]))
                p=proof(g)
                self.assertEqual((proof(g,"H04")["state"],p["state"],p["status"]),("recorded","after_receipt","missing"))
                row=p["period"]
                self.assertEqual((checks(g,"H05")[0]["status"],row["state"],row["status"],row["paid_on"]),(status,state,status,"2026-09-05"))
                self.assertEqual(row["valid_from"],"2026-09-02")
                self.assertEqual(row["end_inclusive"],True if "含当日" in end else None)
                cited={s["quote"]:s for s in row["sources"]}
                for literal in (TERM,RIDER,START,end,RECEIPT[-1],*tail):
                    r=cited[literal]
                    self.assertTrue(r["line"] and r["rects"])
                    self.assertIn(r["id"],p["evidence"])

    def test_strict_outside_inside_and_separate_adverse_timing(self):
        for start,end,bank,state,status in (
                ("保函有效期自：2026年9月6日","保函有效期至：2026年9月9日",None,"before_start","risk"),
                (START,"保函有效期至：2026年9月4日",None,"expired","risk"),
                (START,"保函有效期至：2026年9月6日",None,"covered","missing"),
                ("保函有效期自：2026年9月1日","保函有效期至：2026年9月6日",bank_day("2026-09-02"),"covered","risk")):
            with self.subTest(start=start,end=end,bank=bank):
                g,_=sample(start=start,end=end,bank=bank)
                p=proof(g)
                self.assertEqual((p["period"]["state"],checks(g,"H05")[0]["status"]),(state,status))
                if bank:
                    self.assertEqual(p["state"],"before_receipt")
        g,_=sample(term=None)
        self.assertEqual(proof(g)["state"],"after_receipt")
        self.assertNotIn("period",proof(g))
        g,_=sample(extras=[BANK_DOC])
        self.assertNotIn("advance_guarantee",checks(g,"H05")[1])

    def test_pages_and_dates_must_be_unique_legible_ordered_and_bound(self):
        def altered_page(pages,_):
            pages[4]["layer"]["clause_text_only"]=False
        for opts in ({"end":None},{"start":None},{"tail":(END,)},{"tail":("保函有效期至：2026年9月12日",)},
                     {"end":"保函有效期至（含当日）：2026年9月0 4日"},{"end":"保函有效期至：2026年2月30日"},
                     {"start":"保函有效期自：2026年9月14日"},{"tail":("承保资格：须另经审批",)},
                     {"tail":("保函有效期另按审核结果确定",)},{"receipt":None},{"receipt":(*RECEIPT[:2],"签收保函编号：OTHER-5",*RECEIPT[3:])},
                     {"transform":altered_page},{"extras":[[("other","","预付款保函")]]},
                     {"extras":[bank_day("2026-09-05")]},{"omitted":[(4,"回单提示：本单仅为付款申请受理凭证，不代表实际扣款")]}):
            with self.subTest(opts=opts):
                g,_=sample(**opts)
                self.assertEqual(proof(g)["period"]["state"],"review")
        for f,v in (("payee","演练丙"),("transfer_status","已受理"),("payment_designation","第二期")):
            g,_=sample(bank=[(field,l,v if field==f else val) for field,l,val in BANK])
            self.assertNotIn("advance_guarantee",checks(g,"H05")[0])

    def test_attachments_and_packets_never_replace_the_original_period(self):
        for doc,state in (([("other","","展期申请"),("other","说明","尚待确认")],"extension_review"),
                          ([("contract_addendum","","补充协议"),("other","说明","详见附件")],"review"),
                          ([("other","","未归属的单据")],"review")):
            with self.subTest(doc=doc):
                g,_=sample(extras=[doc])
                p=proof(g)
                self.assertEqual((p["state"],p["period"]["state"],p["period"]["valid_until"]),("after_receipt",state,"2026-09-04"))
                self.assertTrue(any(s["doc"]=="d07" and s["role"]=="extension" for s in p["sources"]))
        def extra_page(pages,_):
            pages.append({"doc":"d05","number":2,"sha256":"second","text":NOTE,
                          "layer":{"type":"text","clause_text_only":True,"lines":{"1":[[.1,.1,.9,.2]]}},
                          "extraction":{"output":{"quality":"readable","facts":[]}}})
        g,_=sample(transform=extra_page)
        self.assertNotIn(proof(g)["period"]["state"],("covered","expired","before_start"))
        self.assertTrue(any(s["doc"]=="d05" and s["page"]==2 for s in proof(g)["sources"]))
        g,_=sample(names={"d05":"预付款保函展期申请附件.pdf"})
        p=proof(g)["period"]
        self.assertEqual(p["state"],"extension_review")
        self.assertTrue(any(s["role"]=="extension" and s["line"] is None and not s["rects"] for s in p["sources"]))
        def unidentified_leaf(pages,_):
            text="特别约定：期限以所附批复为准"
            pages.append({"doc":"d02","number":2,"sha256":"second","text":text,"layer":layout(text),
                          "extraction":{"output":{"quality":"readable","facts":[]}}})
        g,_=sample(transform=unidentified_leaf)
        p=proof(g)["period"]
        self.assertEqual(p["state"],"review")
        self.assertTrue(any(s["doc"]=="d02" and s["page"]==2 and s["line"] is None for s in p["sources"]))

    def test_only_two_exact_adjacent_originals_can_explain_a_merged_transcription(self):
        def observation(quote,disputed=False):
            def edit(pages,signs):
                facts=pages[0]["extraction"]["output"]["facts"]
                facts.append({"field":"other","value":quote,"quote":quote,"region":"top"})
                if disputed:
                    signs[f"d01/p1/f{len(facts)}"]={"decision":"dispute"}
            return edit
        for sep in (""," "):
            g,_=sample(transform=observation(RIDER+sep+TERM))
            self.assertEqual((checks(g,"H03")[0]["status"],proof(g)["period"]["state"]),("ok","expired"))
            rows=[s for s in proof(g)["sources"] if s["role"]=="clause"]
            self.assertEqual([s["quote"] for s in rows],[RIDER,TERM])
            self.assertTrue(all(s["line"] and not s["facts"] for s in rows))
        for kwargs in ({"transform":observation(RIDER+"但须董事会批准"+TERM)},
                       {"transform":observation(RIDER+TERM,True)},{"term":TERM+"，另须取得董事会批准"},
                       {"term":TERM.replace("第一期","第二期")},{"omitted":[(1,TERM)]},
                       {"omitted":[(1,"第二期另须取得质检部门放行意见")]}):
            with self.subTest(kwargs=kwargs):
                g,_=sample(**kwargs)
                self.assertNotEqual(checks(g,"H03")[0]["status"],"ok")
                self.assertNotEqual(checks(g,"H04")[1]["status"],"ok")

    def test_verify_recomputes_interval_risk_and_requires_each_bound_source(self):
        g,texts=sample()
        original=issued(g)
        read=lambda d,n:texts[d,n]
        guarantee.verify(original,read)
        verify_findings(original)
        for target in ("period","status","method","downgrade","edge","scope","paid","remove","rect","source","conclusion"):
            with self.subTest(target=target):
                bad=copy.deepcopy(original)
                f=next(f for f in bad["findings"] if f["rule"]=="H05")
                p=f["advance_guarantee"]["period"]
                if target=="period": p["state"]="covered"
                if target=="status": f["status"]="missing"
                if target=="method": bad["policy"]["code_sha256"]={"advance_guarantee.py":"x"}
                if target=="downgrade": bad["policy"]["advance_guarantee"]=guarantee.LEGACY
                if target=="paid": p["paid_on"]="2026-09-04"
                if target=="scope": f["scope"].remove("d05")
                if target=="remove": del f["advance_guarantee"]["period"]
                end=next(r for r in g[guarantee.KEY]["rows"] if r["field"]=="valid_until_inclusive")
                if target=="rect": bad["calls"]["pages"][4][guarantee.RECTS][str(end["line"])]=[[.2,.2,.8,.3]]
                if target=="source": bad["graph"][guarantee.KEY]["rows"][-1]["doc"]="d09"
                if target=="edge": bad["graph"]["edges"].remove(next(e for e in bad["graph"]["edges"] if
                    e["type"]=="supports_result" and e["from"]==end["id"] and e["to"]=="finding/"+f["id"]))
                if target=="conclusion": p["sources"]=p["sources"][:-1]
                with self.assertRaises(ValueError):
                    guarantee.verify(bad,read)

    def test_unlocated_or_disputed_date_cannot_replace_print_and_supply_an_expiry_risk(self):
        for quote,observed in ((END,"2026年9月9日"),("保函有效期至（含当日）：2026年9月8日","2026年9月8日")):
            def competing_reading(pages,_):
                pages[4]["extraction"]["output"]["facts"].append({"field":"grant_until","value":observed,"quote":quote,"region":"top"})
            g,_=sample(transform=competing_reading)
            p=proof(g)
            self.assertEqual((p["state"],p["period"]["state"],p["period"]["valid_until"]),("after_receipt","review",None))
        def partial(pages,_):
            pages[4]["extraction"]["output"]["quality"]="partial"
        g,_=sample(transform=partial)
        self.assertEqual(proof(g)["period"]["state"],"review")
        self.assertTrue(all(r["line"] is None for r in proof(g)["sources"] if r["role"]=="guarantee"))

    def test_actual_signoff_rechecks_stored_physical_period_geometry(self):
        g,texts=sample()
        report=issued(g)
        raw=encode(report)
        with tempfile.TemporaryDirectory() as temp,sqlite3.connect(":memory:") as db:
            store=Store(Path(temp))
            db.row_factory=sqlite3.Row
            db.executescript("CREATE TABLE cases(id,created);CREATE TABLE reports(case_id,rev,content,hash);CREATE TABLE pages(case_id,doc,number,text,layer);")
            db.execute("INSERT INTO cases VALUES('test','2026-11-27')")
            db.execute("INSERT INTO reports VALUES('test',1,?,?)",(raw,hashlib.sha256(raw.encode()).hexdigest()))
            db.executemany("INSERT INTO pages VALUES('test',?,?,?,?)",[(d,n,t,encode(layout(t))) for (d,n),t in texts.items()])
            end=next(r for r in g[guarantee.KEY]["rows"] if r["field"]=="valid_until_inclusive")
            saved=layout(texts[end["doc"],end["page"]])
            saved["lines"][str(end["line"])]=[[.3,.1,.6,.2]]
            db.execute("UPDATE pages SET layer=? WHERE doc=? AND number=?",(encode(saved),end["doc"],end["page"]))
            with self.assertRaisesRegex(CaseError,"签收前核对预付款保函失败"):
                store.recheck_approval(db,"test",1,{})
