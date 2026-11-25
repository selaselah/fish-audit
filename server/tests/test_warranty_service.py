import copy
import unittest

from controls import VERSION, execute
from performance import compute, verify_findings
from test_performance import CONTRACT, RECEIPT, WARRANTY, BANK_DOC, material
from test_warranty_terms import TERM, CONDITION, texts
from warranty_terms import edges, sources, verify, SUBMISSION_FORMAT, TICKET_FORMAT


def ticket(state="已关闭",closed="2026-11-19",signature="演练丁（已签字）",number="WX-101",opening="2026-11-02",item="冷藏柜"):
    fields=[("warranty_ticket","","质保维修工单"),*[(f,l,item if f=="subject" else v) for f,l,v in CONTRACT[1:5]],
            ("warranty_ticket_id","质保工单编号",number),("warranty_reported_on","报修日期",opening),
            ("warranty_fault","报修事项","温控探头故障"),("warranty_ticket_state","工单状态",state)]
    if closed: fields.append(("warranty_closed_on","关闭日期",closed))
    if signature: fields.append(("warranty_closed_by","采购方关闭签认",signature))
    return fields


def audit(*tickets,cert="2026-11-21",paid="2026-11-22",attest=True,omissions=(),condition=CONDITION,extra_pages=()):
    contract=CONTRACT+[("warranty_period","质保期限",TERM)]+([("warranty_condition","质保金返还条件",condition)] if condition else [])
    release=WARRANTY+[("warranty_defects","质保遗留事项","无未关闭缺陷")]
    confirmed={}
    if attest:
        for i,rows in enumerate(tickets,5):
            for j,(field,_,_) in enumerate(rows,1):
                if field=="warranty_closed_by":
                    confirmed[f"d{i:02d}/p1/f{j}"]={"decision":"confirm","source_check":{"fixture":True}}
    def change(i,k,l,v):
        return {"warranty_release":cert+"双方确认质保期已满","paid_on":paid,"payment_designation":"第三期"}.get(k,v)
    graph=material([contract,RECEIPT,release,BANK_DOC,*tickets],change,omissions=omissions,attestations=confirmed,extra_pages=extra_pages)
    graph["warranty_as_of"]="2026-11-25"
    return graph


def decisions(graph):
    checks=compute(graph)
    phases=[f for f in checks if f["rule"]=="H04"]
    bank,=[f for f in checks if f["rule"]=="H05"]
    return phases,bank


class WarrantyTicketTests(unittest.TestCase):
    def test_image_fields_find_only_their_own_page_and_never_establish_release(self):
        def image(number,rows):
            return {"doc":"d05","number":number,"sha256":"scan","text":"","layer":{"type":"image_overlay","lines":{}},
                    "extraction":{"output":{"quality":"readable","facts":[{"field":f,"value":v,"quote":l+"："+v,"region":"middle"} for f,l,v in rows]}}}
        number=("warranty_ticket_id","质保工单编号","WX-TK-274")
        status=("warranty_ticket_state","工单状态","已关闭")
        first=[("other","","附件移交清单")]
        g=audit(first,extra_pages=[image(2,[number,status])])
        pages=[p for p in g["warranty_sources"]["pages"] if p.get("ticket")]
        self.assertEqual([(p["page"],p.get("image_ticket_refs",[])) for p in pages],[(1,[]),(2,["d05/p2/f1","d05/p2/f2"])])
        phases,bank=decisions(g)
        w=phases[-1]["warranty_check"]
        self.assertEqual([(t["state"],t["linked"]) for t in w["tickets"]],[("scope",False)])
        self.assertEqual((phases[-1]["status"],bank["status"]),("missing","missing"))
        self.assertTrue(set(pages[-1]["image_ticket_refs"])<=set(phases[-1]["evidence"]))
        self.assertEqual(edges([*phases,bank]),[])
        for inputs in ([image(2,[status])],[image(2,[number]),image(3,[status])],
                       [image(2,[number,("warranty_ticket_state","审批状态","已关闭")])]):
            graph=audit(first,extra_pages=inputs)
            self.assertFalse(any(p.get("ticket") for p in graph["warranty_sources"]["pages"]))

    def test_archived_invoice_with_scanned_work_order_requires_reaudit_before_approval(self):
        quoted=[{"field":field,"value":value,"quote":label+"："+value,"region":"top"} for field,label,value in
                [("warranty_ticket_state","工单状态","待维修"),("warranty_ticket_id","质保工单编号","WX-061")]]
        image={"doc":"d05","number":2,"sha256":"scan","text":"","layer":{"type":"image","lines":{}},
               "extraction":{"output":{"quality":"readable","facts":quoted}}}
        g=audit([("invoice","","采购发票")],extra_pages=[image])
        def read(doc,page):
            return "\n".join(f["quote"] for f in g["facts"] if f["doc"]==doc and f["page"]==page)
        current=g["warranty_sources"]
        g["warranty_sources"]=sources(g,read,TICKET_FORMAT)
        self.assertFalse(any(p.get("ticket") for p in g["warranty_sources"]["pages"]))
        fs=compute(g)
        self.assertEqual([f["status"] for f in fs if f["rule"] in ("H04","H05")],["ok"]*4)
        g["edges"]+=edges(fs)
        old={"graph":g,"findings":fs,"policy":{**VERSION,"version":"2026.11.25.29","warranty_checks":TICKET_FORMAT}}
        verify(old,read,submitted="2026-11-25T10:00:00Z")
        with self.assertRaisesRegex(ValueError,"重新审计"):
            verify(old,read,submitted="2026-11-25T10:00:00Z",signing=True)
        g["warranty_sources"]=current
        current["pages"][-1]["image_ticket_refs"]=[]
        with self.assertRaisesRegex(ValueError,"归档不符"):
            verify({**old,"policy":{**VERSION}},read)

    def test_controls_follow_each_printed_work_order_without_reopening_other_phases(self):
        for order,state,status in [(ticket(),"closed","ok"),(ticket("待维修",None,None),"open","risk"),
            (ticket(closed="2026-11-24"),"late","risk"),(ticket(closed="2026-11-21"),"same_day","missing"),
            (ticket(closed="2026-11-26"),"future","risk"),(ticket(item="保温柜"),"identity","missing"),
            (ticket(number="WX-XX01"),"number","missing"),(ticket(opening="2026-09-20"),"period","missing"),
            (ticket(closed="2026-10-30"),"pending","missing"),(ticket(signature="维修组已处理"),"pending","missing"),
            (ticket(closed="2026-11-1 9"),"pending","missing")]:
            with self.subTest(state=state,order=order):
                g=audit(order);p,b=decisions(g);w=p[-1]["warranty_check"]; t,=w["tickets"]
                self.assertEqual([f["status"] for f in p]+[b["status"]],["ok","ok",status,status])
                self.assertEqual(t["state"],state)
                self.assertTrue(set(t["evidence"])<=set(p[-1]["evidence"]) & set(b["evidence"]))
                self.assertEqual(t["unit"],"d05")
                self.assertEqual(w["at_submission"]["defects"],"stated_clear")
                self.assertEqual(len([e for e in edges(p) if e["type"]=="warranty_release_basis"]),int(status=="ok"))
                if state=="late": self.assertIn("早于工单关闭日",b["detail"])
                if state=="identity": self.assertFalse(any(e["type"]=="warranty_ticket_comparison" for e in edges(p)))

    def test_duplicate_ids_unsigned_closure_and_outside_warranty(self):
        for g,expected in ((audit(ticket(),attest=False),["pending"]),
                           (audit(ticket(),ticket("待维修",None,None)),["number","number"]),
                           (audit(ticket(),ticket("待维修",None,None,number="WX-102")),["closed","open"]),
                           (audit(ticket(),condition=None),["period"]),
                           (audit(ticket(),cert="2026-11-29"),["period"]),
                           (audit(ticket(opening="2026-11-23")),["period"])):
            p,b=decisions(g)
            self.assertEqual([r["state"] for r in p[-1]["warranty_check"]["tickets"]],expected)
            self.assertNotEqual(b["status"],"ok")
            self.assertEqual(p[0]["status"],"ok")

    def test_riders_and_non_native_pages_keep_their_scope_unresolved(self):
        graph=audit(ticket(),omissions=[(5,"补充意见：本合同第一期暂停支付")])
        phases,bank=decisions(graph)
        self.assertNotEqual(phases[0]["status"],"ok")
        self.assertEqual(phases[-1]["warranty_check"]["tickets"][0]["state"],"scope")
        graph=audit(ticket())
        source=texts(graph)
        next(n for n in graph["nodes"] if n["id"]=="d05/p1")["clause_text_only"]=False
        graph["warranty_sources"]=sources(graph,lambda doc,p:source[doc])
        p,b=decisions(graph)
        self.assertEqual(p[-1]["warranty_check"]["tickets"][0]["state"],"scope")
        self.assertNotEqual(b["status"],"ok")

    def test_warranty_dates_do_not_let_a_ticket_replace_a_required_certificate(self):
        p,b=decisions(audit(ticket(),cert="2026-11-20",paid="2026-11-19"))
        self.assertEqual(p[-1]["status"],"missing")
        self.assertEqual(b["status"],"risk")
        self.assertTrue(any("同日" in t["detail"] for t in b["date_checks"]))
        g=audit(ticket())
        c=next(f for f in g["facts"] if f["field"]=="acceptance_signer" and f["doc"]=="d03")
        c["attestation"]=None
        p,b=decisions(g)
        self.assertEqual(p[-1]["warranty_check"]["confirmed_on"],None)
        self.assertEqual(p[-1]["warranty_check"]["tickets"][0]["state"],"period")
        self.assertNotEqual(b["status"],"ok")

    def test_legacy_approval_rechecks_ticket_printed_on_an_invoice_page(self):
        page=[("invoice","","采购发票")]+[("other",label,value) for _,label,value in ticket("待维修",None,None)]
        graph=audit(page)
        # The historic workpaper classified this page as an invoice and stored the work order as ordinary text.
        invoice_page=next(d["id"] for d in graph["audit_documents"] if d.get("source")=="d05")
        graph["documents_by_kind"]["invoice"]=[invoice_page]
        originals=texts(graph)
        def read(doc,page):
            return originals[doc]
        graph["warranty_sources"]=sources(graph,read,SUBMISSION_FORMAT)
        findings=compute(graph)
        self.assertEqual([f["status"] for f in findings if f["rule"] in ("H04","H05")],["ok"]*4)
        graph["edges"].extend(edges(findings))
        historic={"graph":graph,"findings":findings,
                  "policy":{**VERSION,"version":"2026.11.25.28","warranty_checks":SUBMISSION_FORMAT}}
        submitted="2026-11-25T08:00:00+00:00"
        verify(historic,read,submitted=submitted)
        with self.assertRaisesRegex(ValueError,"重新审计后签收"):
            verify(historic,read,submitted=submitted,signing=True)

    def test_replay_binds_ticket_lines_scope_and_individual_state_edges(self):
        g=audit(ticket()); read=lambda doc,page:texts(g)[doc]
        report={"policy":{**VERSION,"profile":g["profile"]},"graph":g,"findings":execute(g,g["profile"])}
        g["edges"]+=edges(report["findings"])
        verify(report,read,submitted="2026-11-25T08:00:00+00:00")
        verify_findings(report)
        for key in ("line","edge","relation","record"):
            revised=copy.deepcopy(report)
            if key=="line": next(s for s in revised["graph"]["warranty_sources"]["lines"] if s["kind"]=="ticket_line")["quote"]="另一张工单"
            if key=="edge": next(e for e in revised["graph"]["edges"] if e["type"]=="warranty_closed_by")["from"]="d01"
            if key=="relation": next(e for e in revised["graph"]["edges"] if e["type"]=="warranty_ticket_comparison")["to"]="d01/p1"
            if key=="record": next(f for f in revised["findings"] if f.get("warranty_check"))["warranty_check"]["tickets"][0]["state"]="open"
            with self.assertRaises(ValueError):
                verify_findings(revised) if key=="record" else verify(revised,read)
        g["warranty_sources"]=sources(g,read,SUBMISSION_FORMAT)
        old={"graph":g,"policy":{**report["policy"],"version":"2026.11.25.28","warranty_checks":SUBMISSION_FORMAT},
             "findings":compute(g)}
        g["edges"]=[e for e in g["edges"] if e["type"] not in ("warranty_release_basis","warranty_ticket_comparison")]+edges(old["findings"])
        self.assertTrue(all("tickets" not in f.get("warranty_check",{}) for f in old["findings"]))
        verify(old,read,submitted="2026-11-25T08:00:00+00:00")
