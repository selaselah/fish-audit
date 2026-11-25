import copy
import unittest

import repair_completion
from controls import VERSION, execute
from performance import compute, verify_findings
from test_reinspection import graph
from test_performance import PERFORMANCE


NOTE = "整改备注：控制探头仅临时校准，正式更换尚未完成"


def issued(*, note=None, day="2026-09-23"):
    def edit(i, field, label, value):
        return {"paid_on":"2026-09-27","repaired_on":day}.get(field,value)
    g = graph(edit, omissions=[(3,note)] if note else [])
    raw = {d["id"]:"\n".join(f["quote"] for f in g["facts"] if f["doc"]==d["id"]) for d in g["documents"]}
    if note:
        raw["d03"] += "\n" + note
    return {"policy":{**VERSION,"profile":PERFORMANCE},"graph":g,"findings":execute(g,PERFORMANCE)}, lambda doc,page:raw[doc]


class RepairCompletionTests(unittest.TestCase):
    def test_unreported_rider_on_repair_keeps_signed_initial_defect_and_payment_dependencies(self):
        for note, status in [(NOTE,"risk"),("整改备注：详见另附工单","missing"),
                             ("整改状态：作废","missing"),("整改备注：无","ok")]:
            with self.subTest(note=note):
                paper, read = issued(note=note)
                repair_completion.verify(paper,read)
                found = paper["findings"]
                h = next(f for f in found if f["rule"]=="H02")
                fix = h["reinspection"]["steps"][1]["completion"]
                self.assertEqual(fix["status"],status)
                if status=="ok":
                    self.assertEqual(h["reinspection"]["state"],"closed")
                    continue
                line = fix["lines"][-1]
                self.assertEqual((line["quote"],line["facts"],line["line"]),(note,[],14))
                self.assertEqual((h["status"],h["reinspection"]["state"],h["reinspection"]["focus"]),("issue","open","repair"))
                phase = [f for f in found if f["rule"]=="H04"]
                self.assertEqual([f["status"] for f in phase],["ok","risk","risk"])
                self.assertNotIn("d03/p1",phase[0]["evidence"])
                self.assertTrue(all("d03/p1" in p["evidence"] for p in (h,*phase[1:])))
                self.assertEqual(next(f["status"] for f in found if f["rule"]=="H05"),"missing")

    def test_date_must_be_unique_and_readable_on_the_original(self):
        for note,day in [(None,"2026年9月2 3日"),("整改完成日期：2026-09-23","2026-09-23")]:
            with self.subTest(note=note):
                paper,_ = issued(note=note,day=day)
                h = next(f for f in paper["findings"] if f["rule"]=="H02")
                fix = h["reinspection"]["steps"][1]
                self.assertEqual((fix["date"],fix["completion"]["date"],h["reinspection"]["state"]),(None,None,"open"))
                self.assertEqual(h["reinspection"]["focus"],"dates")
        paper,read = issued()
        g=paper["graph"]
        next(n for n in g["nodes"] if n["id"]=="d03/p1")["clause_text_only"]=False
        g["repair_completion_sources"]=repair_completion.sources(g,read)
        h=compute(g)[1]
        self.assertEqual((h["status"],h["reinspection"]["state"]),("issue","open"))
        self.assertEqual(h["reinspection"]["steps"][1]["completion"]["mixed_pages"][0]["doc"],"d03")

    def test_verify_original_edges_finding_and_legacy_approval(self):
        for note,day in [(NOTE,"2026-09-23"),(None,"2026年9月2 3日"),(None,"2026-09-23")]:
            with self.subTest(note=note,day=day):
                paper,read=issued(note=note,day=day)
                for target in ("evidence","edge","marker","finding"):
                    fake=copy.deepcopy(paper)
                    if target=="evidence":
                        fake["graph"]["repair_completion_sources"]["lines"].pop()
                    elif target=="edge":
                        next(e for e in fake["graph"]["edges"] if e["type"]=="repair_completion_basis")["line"]=888
                    elif target=="marker":
                        del fake["policy"]["repair_completion"]
                    else:
                        next(f for f in fake["findings"] if f.get("reinspection"))["reinspection"]["steps"][1]["date"]="2026-10-01"
                    with self.assertRaises(ValueError):
                        verify_findings(fake) if target=="finding" else repair_completion.verify(fake,read)
                old=copy.deepcopy(paper)
                g=old["graph"]
                del g["repair_completion_sources"], old["policy"]["repair_completion"]
                old["policy"]["version"]="2026.11.25.20"
                g["edges"]=[e for e in g["edges"] if e["type"]!="repair_completion_basis"]
                old["findings"]=compute(g)
                self.assertEqual(old["findings"][1]["reinspection"]["state"],"closed")
                repair_completion.verify(old,read)
                if note or " " in day:
                    with self.assertRaisesRegex(ValueError,"旧版关闭缺陷"):
                        repair_completion.verify(old,read,signing=True)
                else:
                    repair_completion.verify(old,read,signing=True)
