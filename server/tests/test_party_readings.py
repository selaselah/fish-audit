from copy import deepcopy
from hashlib import sha256
import unittest
from unittest.mock import patch

from graph import build_graph, entity_id
from payment_quality import witness
from performance import Material
import party_readings as parties


def example(corrected=True, *, extra="", heading="验收报告"):
    cid,doc,pid = "1"*32,"d02","d02/p1"
    original,added = pid+"/f1",pid+"/h0123456789ab"
    name,old,line = "云桥演练中心","供 方 ：云桥演练中心","供应方：云桥演练中心"
    text = heading+"\n"+line+extra
    file_hash,image="2"*64,"3"*64
    file={"id":doc,"sha256":file_hash,"ext":".pdf","pages":1,"name":"验收报告.pdf"}
    region={"number":2,"text":line,"rects":[[.1,.2,.6,.3]]}
    candidate={"field":"seller","value":name,"quote":old,"region":"middle"}
    facts=[]
    for key,op in ((original,"correct"),(added,"add")):
        receipt={"format":"field-source-v1","case_id":cid,"rev":2 if op=="correct" else 1,"report_hash":"4"*64,
                 "operation":op,"doc":doc,"page":1,"original_sha256":file_hash,"page_sha256":image}
        edit={"source_check":receipt,"target":key,"rev":receipt["rev"],"doc":doc,"page":1,"field":"seller","quote":line,"value":name}
        confirm={"source_check":receipt,"decision":"confirm","fact":key,"rev":receipt["rev"]}
        f={"id":key,"doc":doc,"page":1,"field":"seller","value":name,"quote":line,"source_line":region,"label":"供应方",
           "region":"middle","status":"confirmed","source_sha256":file_hash,"page_sha256":image,
           "original_candidate":candidate if key==original else None,"attestation":confirm,"amendment":edit,
           "response_id":"model","check_response_id":"reader"}
        if key==original and not corrected:
            f.update(status="visual",quote=old,source_line=None,attestation=None,amendment=None,original_candidate=None)
        facts.append(f)
    edges=[]
    for f in facts:
        edges.append({"from":pid,"to":f["id"],"type":"records","evidence":[f["id"]]})
        if f["status"]=="confirmed":
            edges.append({"from":doc,"to":entity_id("party",name),"type":"seller","evidence":[f["id"]]})
    graph={"documents":[file],"facts":facts,"nodes":[{"id":pid,"type":"page","sha256":image,"text_sha256":sha256(text.encode()).hexdigest()}],
           "edges":edges,"gaps":[],"documents_by_kind":{"acceptance":[doc]},
           "payment_window_sources":{"pages":[{"doc":doc,"page":1,"unit":doc,"document_kind":"acceptance","native":True,"text_only":True}]}}
    reread={"response_id":"reader","input":[{"index":"1","field":"供应方","quote":old,"value":name}],
            "output":{"checks":[{"index":"1","support":"clear"}]}}
    call={"doc":doc,"page":1,"page_sha256":image,"response_id":"model","check":reread,"output":{"facts":[candidate]}}
    finding={"id":"H02-3","rule":"H02","scope":[doc],"evidence":[added],"status":"missing"}
    report={"case_id":cid,"graph":graph,"findings":[finding],"calls":{"pages":[call]},"policy":{"version":"2026.11.27.22"}}
    return report,lambda d,n:text,lambda d,n:{"lines":{"2":region["rects"]}}


def issue(report, read, layout):
    g=report["graph"]
    rows=parties.sources(g,read,layout)
    if rows:
        g[parties.KEY]={"format":parties.FORMAT,"rows":rows}
        report["policy"]["party_readings"]=parties.FORMAT
        nodes,edges=parties.source_graph(rows)
        g["nodes"].extend(nodes)
        g["edges"].extend(edges)
        parties.attach(g,report["findings"])
        for f in report["findings"]:
            g["edges"].extend({"type":"supports_result","from":ref,"to":"finding/"+f["id"],"evidence":[ref]} for ref in f["evidence"])
    return rows


class PartyReadingsTests(unittest.TestCase):
    def test_matching_one_party_line_reveals_the_cited_inspection_and_preserves_the_payment_qualification(self):
        from config import PERFORMANCE
        from controls import execute
        from test_installment_approval import paper, sheet

        for corrected,date,state in ((False,"2026-09-28",None),(True,"2026-09-28","later"),(True,"2026-09-27","same_day")):
            with self.subTest(corrected=corrected,date=date):
                calls=[]
                def build(docs,pages,decisions):
                    example_report,_,_=example(corrected)
                    extra=example_report["graph"]["facts"]
                    source=pages[1]
                    fact=next(f for f in source["extraction"]["output"]["facts"] if f["field"]=="seller")
                    quote=fact["quote"]
                    model_id="d02/p1/f"+str(source["extraction"]["output"]["facts"].index(fact)+1)
                    docs[1].update(ext=".pdf",pages=1,sha256="2"*64)
                    source["sha256"]="3"*64
                    fact["quote"]="供 方 ："+fact["value"]
                    index=model_id.rsplit("/f",1)[1]
                    extraction=source["extraction"]
                    extraction.update(response_id="first",check={"response_id":"second",
                        "input":[{"index":index,"field":"供应方","quote":fact["quote"],"value":fact["value"]}],
                        "output":{"checks":[{"index":index,"support":"clear"}]}})
                    calls.append({**extraction,"doc":"d02","page":1,"page_sha256":source["sha256"]})
                    edits=[]
                    for entry in extra:
                        if not entry.get("amendment"):continue
                        target=model_id if entry.get("original_candidate") else entry["id"]
                        changes={"target":target,"quote":quote,"value":fact["value"],"region":fact["region"],"page_hash":source["sha256"]}
                        edits.append({**entry["amendment"],**changes})
                        decisions[target]={**entry["attestation"],"fact":target}
                    return build_graph(docs,pages,decisions,edits)
                with patch("test_installment_approval.build_graph",build):
                    p,read,layout=paper(sheet(审批日期=date))
                p["calls"]={"pages":calls}
                g=p["graph"]
                f,=[f for f in p["findings"] if f["rule"]=="H05"]
                self.assertEqual(f.get("inspection_use",{}).get("approval",{}).get("state"),state)
                self.assertEqual(f["status"],"risk" if state=="later" else "missing")
                self.assertEqual(g[parties.KEY]["rows"][0]["id"],f["party_readings"][0])
                # Restore the previously issued method and verify whether signing it now conceals a new adverse finding.
                g.pop(parties.KEY)
                g["edges"]=[e for e in g["edges"] if e["type"] not in parties.EDGES]
                g["nodes"]=[n for n in g["nodes"] if n["type"]!="party_reading_line"]
                p["policy"]["version"]="2026.11.27.21"
                p["findings"]=execute(g,PERFORMANCE)
                prior,=[f for f in p["findings"] if f["rule"]=="H05"]
                self.assertEqual(prior["retest_reference"]["state"],"unresolved")
                if state=="later":
                    with self.assertRaisesRegex(ValueError,"重审"):
                        parties.verify(p,read,read_layout=layout,signing=True)
                else:
                    parties.verify(p,read,read_layout=layout,signing=True)

    def test_unlocated_model_reading_remains_pending_until_the_same_row_is_corrected(self):
        for corrected in (False,True):
            p,read,layout=example(corrected)
            r,=issue(p,read,layout)
            self.assertEqual(r["state"],"same_line" if corrected else "pending")
            m=Material(p["graph"],r["unit"])
            self.assertEqual(m.incomplete("seller"),not corrected)
            self.assertEqual(set(m.evidence("seller")),{r["model_ref"],r["added_ref"]})
            raw={**r,"facts":[r["model_ref"],r["added_ref"]] if corrected else [r["added_ref"]]}
            self.assertEqual(witness([raw],m,"seller"),(r["model_ref"],r["value"]) if corrected else None)
            self.assertEqual(witness([{**raw,"facts":[r["model_ref"]]}],m,"seller"),None)
            parties.verify(p,read,read_layout=layout)

    def test_both_action_histories_exact_roles_values_and_a_single_physical_line_are_required(self):
        for changes in ({"extra":"\n销售方：另一企业"},{"extra":"\n供应方：云桥演练中心"},{"extra":"\n整改记录单"},{"heading":"附件"}):
            p,read,layout=example(**changes)
            self.assertEqual(parties.sources(p["graph"],read,layout),[])
        for mode in ("third","other_value","other_role","unverified","reread","doc","pages","scan","split","amended_role","region","different_case","disputed"):
            with self.subTest(mode=mode):
                p,read,layout=example()
                g=p["graph"];model,extra=g["facts"]
                if mode=="third":g["facts"].append({**model,"id":"d02/p1/f2"})
                if mode=="other_value":model["value"]="云桥"
                if mode=="other_role":model["original_candidate"]={**model["original_candidate"],"quote":"担保方：云桥演练中心"}
                if mode=="unverified":extra["amendment"]["source_check"]={}
                if mode=="reread":extra["attestation"]={**extra["attestation"],"source_check":{}}
                if mode=="doc":g["documents"][0]["ext"]=".docx"
                if mode=="pages":g["documents"][0]["pages"]=2
                if mode=="scan":g["payment_window_sources"]["pages"][0]["text_only"]=False
                if mode=="split":g["payment_window_sources"]["pages"][0]["unit"]="unit/d02/p1"
                if mode=="amended_role":model["original_candidate"]={**model["original_candidate"],"field":"buyer"}
                if mode=="region":model["source_line"]={**model["source_line"],"rects":[[.2,.2,.7,.3]]}
                if mode=="different_case":extra["amendment"]["source_check"]["case_id"]="9"*32
                if mode=="disputed":model["status"]="disputed"
                self.assertEqual(parties.sources(g,read,layout),[])

    def test_without_a_separate_reread_of_this_exact_candidate_the_pair_is_withheld(self):
        for mode in ("disabled","same_call","wrong_index","other_quote","other_role","no_vote","two_votes"):
            with self.subTest(mode=mode):
                p,read,layout=example()
                call,=p["calls"]["pages"]
                check=call["check"]
                if mode=="disabled":call.pop("check")
                if mode=="same_call":check["response_id"]=call["response_id"]
                if mode=="wrong_index":check["input"][0]["index"]="2"
                if mode=="other_quote":check["input"][0]["quote"]="供货方：云桥演练中心"
                if mode=="other_role":check["input"][0]["field"]="采购方"
                if mode=="no_vote":check["output"]["checks"]=[]
                if mode=="two_votes":check["output"]["checks"]*=2
                self.assertEqual(parties.sources(p["graph"],read,layout,calls={("d02",1):call}),[])

    def test_archive_rejects_mismatched_reading_geometry_links_case_and_method(self):
        base,read,layout=example();issue(base,read,layout)
        for mode in ("method","case","candidate","file","decision","location","ownership","edge","support","claim","historical"):
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                p=deepcopy(base);g=p["graph"];r=g[parties.KEY]["rows"][0]
                if mode=="method":p["policy"].pop("party_readings")
                if mode=="case":p["case_id"]="7"*32
                if mode=="candidate":p["calls"]["pages"][0]["output"]["facts"]=[{"value":"另一主体"}]
                if mode=="file":g["documents"][0]["sha256"]="0"*64
                if mode=="decision":r["state"]="pending"
                if mode=="location":r["rects"]=[]
                if mode=="ownership":g["edges"]=[e for e in g["edges"] if e["type"]!="seller"]
                if mode=="edge":g["edges"]=[e for e in g["edges"] if e["type"]!="shares_party_line"]
                if mode=="support":g["edges"]=[e for e in g["edges"] if e["from"]!=r["id"]]
                if mode=="claim":p["findings"][0].pop("party_readings")
                if mode=="historical":p["policy"]["version"]="2026.11.27.21"
                parties.verify(p,read,read_layout=layout)
        with self.assertRaises(ValueError):parties.verify(base,read,read_layout=lambda d,n:{"lines":{}})
