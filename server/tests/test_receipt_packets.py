import copy
import unittest

from controls import VERSION, execute
from graph import build_graph
from receipt_packets import verify_sources
from test_delivery_batches import states
from test_final_signers import example


def packet(*,original=None,modify=None):
    original = original or example()
    # Deliberately print the final form first and the first delivery last.
    order = {"d04":1,"d03":2,"d02":3}
    docs = [{"id":"file","name":"验收原件.pdf","sha256":"original"}]
    pages, signatures = [],{}
    for d in original["documents"]:
        physical = d["id"]
        n = order.get(physical,1)
        if physical in order:
            physical = "file"
        else:
            docs.append(d)
        facts = [f for f in original["facts"] if f["doc"]==d["id"]]
        rows = [{k:f[k] for k in ("field","value","quote","region")} for f in facts]
        for i,f in enumerate(facts,1):
            if f["attestation"]:
                signatures[f"{physical}/p{n}/f{i}"] = f["attestation"]
        lines = [f["quote"] for f in facts]
        page = {"doc":physical,"number":n,"sha256":"rendered","layer":{"type":"text","clause_text_only":True,
                "lines":{str(i):[[0,.1,.9,.2]] for i in range(1,len(lines)+1)}},
                "extraction":{"output":{"quality":"readable","facts":rows}}}
        if modify and physical=="file":
            modify(n,lines,page)
        pages.append({**page,"text":"\n".join(lines)})
    graph = build_graph(docs,pages,signatures)
    graph["profile"] = original["profile"]
    texts = {(p["doc"],p["number"]):p["text"] for p in pages}
    return graph,lambda doc,n:texts[doc,n]


class ReceiptPacketTests(unittest.TestCase):
    def test_reordered_pages_keep_each_signature_and_condition_with_its_own_receipt(self):
        for original,status in ((example(),"ok"),(example(["郑敏"]),"missing"),
                                (example(contract_edits={"effect_clause":"本合同自双方盖章并经甲方董事会批准后生效"}),"missing")):
            g,_=packet(original=original)
            ledger,=g["receipt_packet_sources"]["packets"]
            self.assertEqual(ledger["status"],"split")
            self.assertEqual([p["number"] for p in ledger["pages"]],["ZY-30","YS-20","YS-10"])
            h,phases,cash=states(g)
            original_h,original_phases,original_cash=states(original)
            self.assertEqual((h["status"],cash["status"]),(status,original_cash["status"]))
            self.assertEqual([p["status"] for p in phases],[p["status"] for p in original_phases])
            self.assertEqual(h["batch_acceptance"]["completion_on"],original_h["batch_acceptance"]["completion_on"])
            if status=="ok":
                batches=h["batch_acceptance"]["batches"]
                self.assertEqual([b["records"] for b in batches],[["unit/file/p3"],["unit/file/p2"]])
                final,=h["batch_acceptance"]["separate_final"]["records"]
                self.assertEqual(final,"unit/file/p1")
                self.assertEqual([p["stage"]["share"] for p in phases],["20","35","35","10"])
            edges=[e for e in g["edges"] if e["type"]=="acceptance_page_identity"]
            self.assertEqual(len(edges),6)
            self.assertTrue(all(e["from"]=="unit/"+e["evidence"][0] and e["to"].startswith(e["evidence"][0]+"/") for e in edges))

    def test_ambiguous_and_partially_observed_forms_never_release_an_acceptance_payment(self):
        def alter(mode):
            def change(n,lines,page):
                if n!=2:
                    return
                raw=page["extraction"]["output"]["facts"]
                own=next(f for f in raw if f["field"]=="acceptance_number")
                if mode=="unobserved":
                    raw.remove(own)
                elif mode=="mixed":
                    page["layer"]["clause_text_only"]=False
                elif mode=="scan":
                    page["layer"]={"type":"image","lines":{}}
                    lines.clear()
                elif mode=="quality":
                    page["extraction"]["output"]["quality"]="partial"
                elif mode=="duplicate" or mode=="space":
                    before=own["quote"]
                    own.update(value="YS-10" if mode=="duplicate" else "YS-20",
                               quote="验收单编号：YS-10" if mode=="duplicate" else before)
                    lines[lines.index(before)]=own["quote"] if mode=="duplicate" else "验收单编号：YS-2 0"
                else:
                    lines.append({"continuation":"验收记录续页","masked":"本表编号仅列末四位","multiple":"验收单编号：YS-99"}[mode])
            return change
        for mode in ("duplicate","space","unobserved","mixed","scan","quality","continuation","masked","multiple"):
            with self.subTest(mode=mode):
                g,read=packet(modify=alter(mode))
                ledger,=g["receipt_packet_sources"]["packets"]
                self.assertEqual(ledger["status"],"review")
                self.assertTrue(ledger["pages"][1]["reasons"])
                self.assertFalse(any(e["type"]=="acceptance_page_identity" for e in g["edges"]))
                h,ps,cash=states(g)
                self.assertEqual([p["status"] for p in ps],["ok","missing","missing","missing"])
                self.assertFalse(h["batch_acceptance"]["completion_on"])
                self.assertEqual(cash["status"],"missing")
                self.assertIn("file/p2",h["evidence"])
                self.assertIn("file/p2",ps[1]["evidence"])
                self.assertIn("合订件",h["detail"])
                verify_sources({"policy":VERSION,"graph":g,"findings":[]},read)

    def test_offline_verification_checks_raw_fragments_and_unit_ownership(self):
        g,read=packet()
        report={"policy":VERSION,"graph":g,"findings":execute(g,g["profile"])}
        verify_sources(report,read)
        for change in ("quote","edge","owner","section","policy","number","raw","assignment"):
            bad=copy.deepcopy(report)
            graph=bad["graph"]
            p=graph["receipt_packet_sources"]["packets"][0]["pages"][1]
            if change=="quote":
                p["rows"][0]["quote"]="其他单据"
            elif change=="number":
                p["number"]="YS-99"
            elif change=="edge":
                next(e for e in graph["edges"] if e["type"]=="acceptance_page_identity")["to"]="file/p2/f1"
            elif change=="owner":
                next(f for f in graph["facts"] if f["doc"]=="file")["unit"]="unit/file/p1"
            elif change=="section":
                graph["edges"]=[e for e in graph["edges"] if e["type"]!="section_page"]
            elif change=="assignment":
                graph["documents_by_kind"]["acceptance"].append("unit/file/p2")
            elif change=="policy":
                del bad["policy"]["receipt_packets"]
            with self.assertRaises(ValueError):
                verify_sources(bad,(lambda d,n:read(d,n)+"改") if change=="raw" else read)
