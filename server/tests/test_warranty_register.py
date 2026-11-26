import copy
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from config import CaseError, PERFORMANCE
from controls import VERSION, conclusion, execute
from graph import link_procedures
from performance import verify_findings
from storage import Store, encode
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material
from test_warranty_service import ticket
from test_warranty_terms import CONDITION, TERM
import warranty_register as register
import warranty_terms as terms


CASE="0"*32


def order(number="WX-101", fault="柜体风扇故障", state="待维修", opened="2026-11-05", closing=None, signed=None):
    return [(k,l,fault if k=="warranty_fault" else v) for k,l,v in ticket(state,closing,signed,number,opened)]


def change(rows,field,value):
    return [(k,l,value if k==field else v) for k,l,v in rows if k!=field or value is not None]


def sample(*orders,accepted=False,release=None,contract=None,attest=True,omissions=(),extras=(),extra_pages=()):
    contract = CONTRACT+[("warranty_period","质保期限",TERM),("warranty_condition","质保金返还条件",CONDITION)] if contract is None else contract
    release = change(WARRANTY,"warranty_release","2026-11-22双方确认质保期已满")+[("warranty_defects","质保遗留事项","无未关闭缺陷")] if release is None else release
    rows=[contract,RECEIPT if accepted else change(RECEIPT,"acceptance_signer",None),release,change(change(BANK_DOC,"payment_designation","第三期"),"paid_on","2026-11-24"),*orders,*extras]
    signoffs={f"d{i:02d}/p1/f{j}":{"decision":"confirm","source_check":{"fixture":True}} for i,group in enumerate(rows,1)
              for j,(k,_,_) in enumerate(group,1) if k=="warranty_closed_by" and attest}
    for j,(field,_,_) in enumerate(release,1):
        if field=="acceptance_signer":
            ref=f"d03/p1/f{j}"
            signoffs[ref]={"decision":"confirm","fact":ref,"rev":1,"source_check":{"case_id":CASE,"format":"field-source-v1",
                         "operation":"confirm","doc":"d03","page":1,"rev":1,"original_sha256":"sample","page_sha256":"page","report_hash":"e"*64}}
    graph=material(rows,attestations=signoffs,omissions=omissions,extra_pages=extra_pages)
    graph["warranty_as_of"]="2026-11-25"
    originals={(f"d{i:02d}",1):"\n".join([*(l+"："+v if l else v for _,l,v in group),
                                          *(line for n,line in omissions if n==i)]) for i,group in enumerate(rows,1)}
    originals.update({(p["doc"],p["number"]):p["text"] for p in extra_pages})
    return graph,originals


def issue(graph):
    findings=execute(graph,PERFORMANCE)
    link_procedures(graph,findings,{"pages":[],"expert":{"model":"fixture"}})
    return {"case_id":CASE,"policy":{**VERSION,"profile":PERFORMANCE},"graph":graph,"findings":findings,"result":conclusion(findings)}


def differences(graph):
    return [f for f in execute(graph,PERFORMANCE) if f["rule"]=="H07"]


class WarrantyRegisterTests(unittest.TestCase):
    def test_two_distinct_orders_receipt_and_missing_named_final(self):
        closed=order("WX-102","温控探头故障","已关闭",closing="2026-11-20",signed="演练丁（已签字）")
        g,text=sample(order(),closed)
        paper=issue(g)
        phase,bank=[f for f in paper["findings"] if f.get("warranty_check")]
        f,=[f for f in paper["findings"] if f["rule"]=="H07"]
        self.assertEqual([phase["status"],bank["status"],f["status"]],["missing","missing","risk"])
        for w in (phase["warranty_check"],bank["warranty_check"]):
            self.assertIsNone(w["accepted_on"])
            self.assertIsNone(w["calendar_end"])
            self.assertEqual([r["state"] for r in w["tickets"]],["period","period"])
        d=f["warranty_difference"]
        self.assertEqual((d["ticket_unit"],d["release_unit"],d["number"],d["reported_on"],d["confirmed_on"],d["state"]),
                         ("d05","d03","WX-101","2026-11-05","2026-11-22","record_difference"))
        self.assertEqual(f["scope"],["d01","d03","d05"])
        self.assertEqual(paper["result"]["counts"]["risk"],1)
        self.assertFalse(any(x.startswith("d06") for x in f["evidence"]))
        for ref in d["refs"].values():
            fact=next(x for x in g["facts"] if x["id"]==ref)
            line=fact["source_line"]
            self.assertEqual(line["text"],text[fact["doc"],fact["page"]].splitlines()[line["number"]-1])
            self.assertTrue(line["rects"])
            self.assertIn(ref,f["evidence"])
        verify_findings(paper)
        terms.verify(paper,lambda doc,p:text[doc,p],submitted="2026-11-25T09:00:00+08:00")
        self.assertEqual([e for e in g["edges"] if e["type"]==register.EDGE],
                         [{"type":register.EDGE,"from":d["refs"]["defects"],"to":d["refs"]["ticket_state"],"evidence":f["evidence"]}])

    def test_distinct_open_numbers_not_counted_as_one_and_ambiguous_ownership_is_held(self):
        g,_=sample(order(),order("WX-102","温控探头故障"))
        self.assertEqual([f["warranty_difference"]["number"] for f in differences(g)],["WX-101","WX-102"])
        for other in (order("WX-101","温控探头故障"),order("wx-101","温控探头故障"),
                      order("WX-102","冷却风机损坏","已关闭",closing="2026-11-19",signed="演练丁（已签字）")):
            self.assertFalse(differences(sample(order(),other)[0]))
        for changed in (order(state="已关闭",closing="2026-11-20"),order(closing="2026-11-18"),order(signed="演练丁（已签字）"),
                        order(opened="2026-11-22"),order(opened="2026-11-23"),order(opened="2026-11-0 5"),
                        order(number="WX-XX01"),order(fault="未发现柜体风扇故障"),order(fault="柜体风扇故障，已撤销"),
                        change(order(),"subject","烤箱"),change(order(),"buyer","另一采购方"),change(order(),"seller","另一供应方"),
                        change(order(),"contract_id","YL-987")):
            with self.subTest(changed=changed):
                self.assertFalse(differences(sample(changed)[0]))

    def test_contract_confirmation_qualifications_and_competing_pages(self):
        for doc,line in ((1,"质保补充约定：主风扇另行保修"),(3,"备注：风扇故障另册处理"),(5,"备注：该工单有争议"),
                         (1,"采购标的：另一台冷柜"),(3,"采购标的：另一台冷柜"),(5,"质保工单编号：WX-102"),
                         (2,"维修补充记录：柜体风扇已修复")):
            self.assertFalse(differences(sample(order(),omissions=[(doc,line)])[0]))
        release=change(WARRANTY,"warranty_release","2026-11-22双方确认质保期已满")+[("warranty_defects","质保遗留事项","无未关闭缺陷")]
        for field,value in (("warranty_defects","无未关闭缺陷（风扇除外）"),("warranty_release","2026年11月2 2日双方确认质保期已满"),
                            ("warranty_release","2026-11-29双方确认质保期已满"),("acceptance_signer","采购方待签"),("seller","另一供应方")):
            self.assertFalse(differences(sample(order(),release=change(release,field,value))[0]))
        self.assertFalse(differences(sample(order(),contract=CONTRACT)[0]))
        self.assertFalse(differences(sample(order(),extras=[release])[0]))
        g,text=sample(order())
        for doc in ("d01","d03","d05"):
            with self.subTest(scan=doc):
                held=copy.deepcopy(g)
                page=next(n for n in held["nodes"] if n["id"]==doc+"/p1")
                page.update(layer="image",clause_text_only=False)
                held["warranty_sources"]=terms.sources(held,lambda d,p:text[d,p])
                self.assertFalse(differences(held))
        for field in ("warranty_ticket_state","warranty_reported_on","warranty_defects","acceptance_signer","contract_id"):
            held=copy.deepcopy(g)
            next(f for f in held["facts"] if f["field"]==field and f["doc"] in ("d01","d03","d05"))["status"]="disputed"
            held["warranty_sources"]=terms.sources(held,lambda d,p:text[d,p])
            self.assertFalse(differences(held))

    def test_replay_refuses_claim_edge_scope_source_and_protocol_substitution(self):
        g,text=sample(order())
        paper=issue(g)
        for target in ("claim","missing","foreign","source","parent","line","edge","support","scope","v4","version","coordinates","foreign_signoff","wrong_signed_page","removed_checks","control"):
            with self.subTest(target=target):
                bad=copy.deepcopy(paper)
                graph=bad["graph"]; f=bad["findings"][-1]; d=f["warranty_difference"]
                read=lambda doc,p:text[doc,p]
                layout=None
                if target=="claim": d["refs"]["condition"]=d["refs"]["defects"]
                if target in ("missing","removed_checks"): bad["findings"].pop()
                if target=="removed_checks":
                    for row in bad["findings"]: row.pop("warranty_check",None)
                if target=="control": next(n for n in graph["nodes"] if n["id"]=="control/H07")["version"]="v4"
                if target=="foreign": bad["findings"][0]["warranty_difference"]=d
                if target=="source": next(p for p in graph["warranty_sources"]["register_pages"] if p["doc"]=="d05")["bounded"]=False
                if target=="parent": graph["edges"].append({"type":"contains","from":"d03","to":"d05/p1","evidence":["d05/p1"]})
                if target=="line":
                    row=next(fact for fact in graph["facts"] if fact["id"]==d["refs"]["ticket_state"])
                    row["source_line"]["number"]-=1
                if target=="edge": next(e for e in graph["edges"] if e["type"]==register.EDGE)["to"]=d["refs"]["fault"]
                if target=="support":
                    graph["edges"].remove(next(e for e in graph["edges"] if e["type"]=="supports_result" and e["to"]=="finding/"+f["id"]))
                if target=="scope": f["scope"].append("d02")
                if target=="v4": bad["policy"]["warranty_checks"]=terms.IMAGE_FORMAT
                if target=="version": bad["policy"]["version"]="2026.11.27.06"
                if target in ("foreign_signoff","wrong_signed_page"):
                    signed=next(a for a in graph["facts"] if a["doc"]=="d03" and a["field"]=="acceptance_signer")
                    key="case_id" if target=="foreign_signoff" else "doc"
                    signed["attestation"]["source_check"][key]="foreign"
                if target=="coordinates": layout=lambda doc,p:{"lines":{}}
                with self.assertRaises(ValueError):
                    terms.verify(bad,read,read_layout=layout)

    def test_actual_approval_rechecks_omitted_difference_and_physical_coordinates(self):
        g,text=sample(order())
        read=lambda doc,p:text[doc,p]
        old=copy.deepcopy(g)
        old["warranty_sources"]=terms.sources(old,read,terms.IMAGE_FORMAT)
        legacy=issue(old);legacy["policy"].update(version="2026.11.27.06",warranty_checks=terms.IMAGE_FORMAT)
        terms.verify(legacy,read)
        current=issue(g)
        with tempfile.TemporaryDirectory() as temp,sqlite3.connect(":memory:") as db:
            store=Store(Path(temp))
            db.row_factory=sqlite3.Row
            db.executescript("CREATE TABLE cases(id,created);CREATE TABLE reports(case_id,rev,content,hash);CREATE TABLE pages(case_id,doc,number,text,layer);")
            db.execute("INSERT INTO cases VALUES('test','2026-11-25T09:00:00+08:00')")
            db.executemany("INSERT INTO pages VALUES('test',?,?,?,?)",[(d,p,s,encode({"type":"text","clause_text_only":True,
                        "lines":{str(i):[[0,.1,.9,.2]] for i in range(1,len(s.splitlines())+1)}})) for (d,p),s in text.items()])
            for rev,paper in enumerate((legacy,current),1):
                raw=encode(paper)
                db.execute("INSERT INTO reports VALUES('test',?,?,?)",(rev,raw,hashlib.sha256(raw.encode()).hexdigest()))
            with self.assertRaisesRegex(CaseError,"旧版底稿未揭示"):
                store.recheck_approval(db,"test",1,{})
            db.execute("UPDATE pages SET layer='{}' WHERE doc='d05'")
            with self.assertRaisesRegex(CaseError,"引文定位"):
                store.recheck_approval(db,"test",2,{})

    def test_legacy_gate_recognizes_previously_reported_risk_and_unrelated_material(self):
        for orders,accepted in (([order()],True),([order(state="已关闭",closing="2026-11-19",signed="演练丁（已签字）")],False),
                                ([change(order(),"subject","不同标的")],False)):
            g,text=sample(*orders,accepted=accepted)
            read=lambda doc,p:text[doc,p]
            g["warranty_sources"]=terms.sources(g,read,terms.IMAGE_FORMAT)
            old=issue(g)
            old["policy"].update(version="2026.11.27.06",warranty_checks=terms.IMAGE_FORMAT)
            terms.verify(old,read,signing=True,submitted="2026-11-25T09:00:00+08:00")
