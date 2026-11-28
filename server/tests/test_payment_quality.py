import unittest
from copy import deepcopy
from unittest.mock import patch

from config import PERFORMANCE
from controls import VERSION, execute
from graph import build_graph
from performance import verify_findings
import payment_quality as quality
from test_performance import BANK_DOC, CONTRACT, RECEIPT, material


def example(*, date="2026-09-21", standard="柜温不高于4℃", measure="柜温8℃", other=(), changes=None, omissions=(), include_bank=True):
    texts = {}
    def build(docs,pages,*args,**kwargs):
        texts.update({(p["doc"],p["number"]):p["text"] for p in pages})
        return build_graph(docs,pages,*args,**kwargs)
    values = {"paid_on":date,"measured_result":measure,"inspection_basis":standard,"acceptance_criteria":standard}
    def edit(i,k,label,v):
        return (changes or {}).get((i,k),values.get(k,v))
    with patch("test_performance.build_graph",build):
        docs=[CONTRACT,RECEIPT]
        if include_bank:
            docs.append(BANK_DOC)
        graph=material([*docs,*other],edit,omissions=omissions)
    found=execute(graph,PERFORMANCE)
    graph["edges"].extend(quality.edges(found))
    return {"graph":graph,"policy":{**VERSION,"profile":PERFORMANCE},"findings":found}, lambda d,n:texts[d,n]


class PaymentQualityEvidence(unittest.TestCase):
    def test_inclusive_limits_use_the_filed_precision_before_declaring_compliance_or_an_excess(self):
        note="测量精度说明：柜温读数已取整，判定须核对未取整的原始记录"
        for contract,basis,value,doc,status in (
                ("柜温不高于8℃","柜温≤8.000℃","柜温8℃",2,"missing"),
                ("柜温不高于7.99℃","柜温不高于7.99℃","柜温8℃",2,"missing"),
                ("柜温不低于-2.49℃","柜温至少-2.49℃","柜温-2.50℃",1,"missing"),
                ("柜温不高于7.99℃","柜温不高于8℃","柜温8℃",1,"risk")):
            with self.subTest(contract=contract,basis=basis):
                p,text=example(standard=contract,measure=value,changes={(2,"inspection_basis"):basis},omissions=[(doc,note)])
                h=next(f for f in p["findings"] if f["rule"]=="H02");proof=h["quality_comparison"]
                n,=proof["reading_notes"]
                self.assertEqual((h["status"],n["doc"],n["quote"]),(status,f"d{doc:02d}",note))
                self.assertEqual(text(n["doc"],n["page"]).splitlines()[n["line"]-1],note)
                self.assertIn(("合同" if doc==1 else "验收单")+f"第 {n['page']} 页第 {n['line']} 行",h["detail"])
                self.assertTrue(all(v["result"]=="reading_required" and "outside_by" not in v for v in proof["limits"].values()))
                self.assertNotIn("超出",h["detail"])
                related=[f for f in p["findings"] if f.get("payment_quality")]
                self.assertEqual([(f["rule"],f["stage"]["name"],f["status"]) for f in related],[("H04","第二期",status),("H05","第二期","missing")])
                self.assertTrue(all(f["payment_quality"]["comparison"]["reading_notes"]==[n] for f in related))
                quality.verify(p,text);verify_findings(p)

    def test_measurement_qualification_preserves_independent_acceptance_findings(self):
        note="仪器说明：柜温判定须核对仪器允差"
        for key,value,status,reason in (
                ("quantity_accepted","1台","risk","数量"),("accepted_on","2025-02-01","risk","早于"),
                ("acceptance_exception","尚待复验","risk","遗留"),("acceptance_signer",None,"missing","签认")):
            p,text=example(standard="柜温不高于7.99℃",changes={(2,key):value},omissions=[(2,note)])
            h=next(f for f in p["findings"] if f["rule"]=="H02")
            self.assertEqual(h["status"],status);self.assertIn(reason,h["detail"]);self.assertIn(note,h["detail"])
            self.assertNotIn("超出",h["detail"]);quality.verify(p,text)
        p,text=example(standard="柜温不高于7.99℃",changes={(2,"acceptance_result"):"不合格"},omissions=[(2,note)])
        h=next(f for f in p["findings"] if f["rule"]=="H02")
        self.assertEqual(h["status"],"issue");self.assertIn("不合格",h["detail"]);self.assertNotIn("reading_caveats",h)
        quality.verify(p,text)

    def test_incomplete_acceptance_quotes_the_caveat_without_issuing_a_final_comparison(self):
        note="检测说明：柜温读数已取整"
        for key in ("acceptance_result","acceptance_scope","seller"):
            p,text=example(standard="柜温不高于7.99℃",changes={(2,key):None},omissions=[(2,note)])
            h=next(f for f in p["findings"] if f["rule"]=="H02");n,=h["reading_caveats"]
            self.assertEqual(h["status"],"missing");self.assertNotIn("quality_comparison",h)
            self.assertEqual(n["quote"],note);self.assertIn(f"{n['doc']}/p{n['page']}",h["evidence"])
            self.assertFalse(any(f.get("payment_quality") for f in p["findings"]))
            self.assertEqual(quality.reading_notes(p["findings"]),[n]);quality.verify(p,text);verify_findings(p)
            h["reading_caveats"]=[]
            with self.assertRaisesRegex(ValueError,"精度说明"):quality.verify(p,text)

    def test_fee_rounding_is_separate_only_for_a_complete_monetary_clause(self):
        fee="检验费用结算：费用金额四舍五入到分"
        for line,qualified in ((fee,False),("测量精度说明：柜温读数已取整，检验费用金额四舍五入到分",True),
                               (fee+"。仪器读数含允差",True),("金额说明：付款金额四舍五入到分",False)):
            p,text=example(standard="柜温不高于7.99℃",omissions=[(2,line)])
            h=next(f for f in p["findings"] if f["rule"]=="H02");bank=next(f for f in p["findings"] if f["rule"]=="H05")
            if qualified:
                self.assertEqual(h["quality_comparison"]["reading_notes"][0]["quote"],line)
                self.assertEqual(bank["status"],"missing")
            else:
                self.assertEqual(h["status"],"issue");self.assertEqual(bank["payment_quality"]["measure"]["outside_by"],"0.01")
                self.assertFalse(quality.reading_notes(p["findings"]))
            quality.verify(p,text)

    def test_previous_precision_rule_replays_and_requires_reaudit_only_for_affected_papers(self):
        for bound,scope,note,blocked in (
                ("8","全部交付终验","测量说明：柜温读数已取整",True),
                ("7.99","全部交付终验","测量说明：柜温读数已取整",True),
                ("7.99",None,"测量说明：柜温读数已取整",True),
                ("7.99","全部交付终验","检验费用结算：费用金额四舍五入到分",False)):
            p,text=example(standard=f"柜温不高于{bound}℃",changes={(2,"acceptance_scope"):scope},omissions=[(2,note)])
            g=p["graph"];g[quality.KEY]=quality.sources(g,text,quality.OPEN_FORMAT)
            g["edges"]=[e for e in g["edges"] if e["type"] not in (quality.EDGE,quality.BASIS_EDGE)]
            p["findings"]=execute(g,PERFORMANCE);g["edges"].extend(quality.edges(p["findings"]))
            p["policy"].update(version="2026.11.28.10",payment_quality=quality.OPEN_FORMAT)
            for f in p["findings"]:f["version"]=p["policy"]["version"]
            quality.verify(p,text);verify_findings(p)
            if blocked:
                with self.assertRaisesRegex(ValueError,"重审"):quality.verify(p,text,signing=True)
            else:quality.verify(p,text,signing=True)

    def test_exact_excluded_boundary_on_either_original_has_no_invented_excess(self):
        cases=(
            ("柜温低于8℃","柜温不高于8℃","柜温8℃",("excluded_boundary","within")),
            ("柜温不低于-2.50℃","柜温＞-2.50℃","柜温-2.500℃",("within","excluded_boundary")),
            ("柜温＜8℃","柜温小于8.0℃","柜温8℃",("excluded_boundary","excluded_boundary")),
            ("柜温大于-2.5℃","柜温高于-2.50℃","柜温-2.51℃",("outside","outside")),
        )
        for contract,basis,value,states in cases:
            with self.subTest(contract=contract,basis=basis):
                p,text=example(standard=contract,measure=value,changes={(2,"inspection_basis"):basis})
                accepted=next(f for f in p["findings"] if f["rule"]=="H02")
                limits=accepted["quality_comparison"]["limits"]
                self.assertEqual(accepted["status"],"issue")
                self.assertEqual(tuple(limits[k]["result"] for k in ("contract","inspection")),states)
                for entry in limits.values():
                    if entry["result"]=="outside":self.assertEqual(entry["outside_by"],"0.01")
                    else:self.assertNotIn("outside_by",entry)
                self.assertNotIn("超出限值0°C",accepted["detail"])
                self.assertEqual([(f["rule"],f["stage"]["name"]) for f in p["findings"] if f.get("payment_quality")],
                                 [("H04","第二期"),("H05","第二期")])
                quality.verify(p,text)
                verify_findings(p)

    def test_matching_strict_bounds_only_resolve_the_measurement(self):
        for change,expected in (({},"ok"),({(2,"acceptance_signer"):None},"missing"),
                                ({(2,"quantity_accepted"):"1台"},"risk"),({(2,"acceptance_exception"):"未复验"},"risk")):
            p,text=example(standard="柜温大于7.99℃",changes={(2,"inspection_basis"):"柜温＞7.990℃",**change})
            accepted=next(f for f in p["findings"] if f["rule"]=="H02")
            self.assertEqual([v["result"] for v in accepted["quality_comparison"]["limits"].values()],["within","within"])
            self.assertEqual(accepted["status"],expected)
            self.assertFalse(any(f.get("payment_quality") for f in p["findings"]))
            quality.verify(p,text)
            verify_findings(p)
        for wording in ("柜温不得高于8℃","柜温不小于8℃","柜温不宜低于8℃","柜温约低于8℃","柜温低于8℃±1℃","按附件执行"):
            with self.subTest(wording=wording):
                p,_=example(standard=wording,changes={(2,"inspection_basis"):"柜温低于8℃"})
                self.assertFalse(any(f.get("quality_comparison") for f in p["findings"]))
        p,_=example(standard="柜温低于8℃",omissions=[(2,"实测结果：柜温7.9℃")])
        self.assertFalse(any(f.get("quality_comparison") for f in p["findings"]))

    def test_printed_rounding_note_needs_original_measurement_before_comparing(self):
        note="检测备注：柜温读数已取整，须查未取整的原始读数"
        for unit in (1,2):
            p,text=example(standard="柜温低于8℃",changes={(2,"inspection_basis"):"柜温不高于8℃"},omissions=[(unit,note)])
            accepted=next(f for f in p["findings"] if f["rule"]=="H02")
            proof=accepted["quality_comparison"]
            self.assertNotEqual(accepted["status"],"issue")
            row,=proof["reading_notes"]
            self.assertEqual(row["quote"],note)
            self.assertEqual(text(row["doc"],row["page"]).splitlines()[row["line"]-1],note)
            self.assertTrue(all(v["result"]=="reading_required" and "outside_by" not in v for v in proof["limits"].values()))
            stage=next(f for f in p["findings"] if f["rule"]=="H05")
            self.assertEqual(stage["status"],"missing")
            self.assertEqual(stage["payment_quality"]["comparison"]["reading_notes"],[row])
            self.assertIn(f"{row['doc']}/p{row['page']}",stage["evidence"])
            quality.verify(p,text)
            verify_findings(p)
            altered=deepcopy(p)
            ledger=altered["graph"][quality.KEY]
            ledger["rows"]=[r for r in ledger["rows"] if r["field"]!="measurement_note"]
            with self.assertRaises(ValueError):quality.verify(altered,text)
        p,_=example(standard="柜温低于8℃",omissions=[(1,"金额说明：付款金额四舍五入到分"),(3,note)])
        accepted=next(f for f in p["findings"] if f["rule"]=="H02")
        self.assertEqual(accepted["status"],"issue")
        self.assertNotIn("reading_notes",accepted["quality_comparison"])

    def test_previous_program_replays_but_cannot_sign_an_omitted_strict_boundary(self):
        for value,blocked in (("柜温8℃",True),("柜温7.99℃",False)):
            p,text=example(standard="柜温低于8℃",measure=value)
            g=p["graph"];g[quality.KEY]=quality.sources(g,text,quality.BASIS_FORMAT)
            g["edges"]=[e for e in g["edges"] if e["type"] not in (quality.EDGE,quality.BASIS_EDGE)]
            p["findings"]=execute(g,PERFORMANCE)
            p["policy"].update(version="2026.11.28.9",payment_quality=quality.BASIS_FORMAT)
            self.assertFalse(any(f.get("quality_comparison") for f in p["findings"]))
            quality.verify(p,text)
            if blocked:
                with self.assertRaisesRegex(ValueError,"重审"):quality.verify(p,text,signing=True)
            else:quality.verify(p,text,signing=True)

    def test_issued_precision_note_needs_its_own_page_trace_and_original_coordinates(self):
        p,text=example(standard="柜温低于8℃",omissions=[(2,"测量说明：柜温读数取整，原始记录另附")])
        note,=quality.reading_notes(p["findings"]);rects=[[0,.1,.9,.2]]
        from_fact={}
        for f in p["graph"]["facts"]:
            if line:=f.get("source_line"):
                from_fact.setdefault((f["doc"],f["page"]),{})[str(line["number"])]=line["rects"]
        from_fact[note["doc"],note["page"]][str(note["line"])]=rects
        pages={n["id"]:n for n in p["graph"]["nodes"] if n["type"]=="page"}
        def layout(doc,page):
            n=pages[f"{doc}/p{page}"]
            return {"type":n["layer"],"clause_text_only":n.get("clause_text_only",False),"lines":from_fact[doc,page]}
        p["calls"]={"pages":[{"doc":note["doc"],"page":note["page"],"page_sha256":pages[f"{note['doc']}/p{note['page']}"]["sha256"],
                              "response_id":"fixture-primary","check":{"response_id":"fixture-check"},
                              quality.RECTS:{str(note["line"]):rects}}]}
        quality.verify(p,text,read_layout=layout)
        for fault in ("position","missing","page","second_reader","conclusion"):
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                other=deepcopy(p);call,=other["calls"]["pages"]
                if fault=="position":call[quality.RECTS][str(note["line"])]=[[.1,.2,.9,.3]]
                if fault=="missing":call.pop(quality.RECTS)
                if fault=="page":call["page_sha256"]="other"
                if fault=="second_reader":call["check"].clear()
                if fault=="conclusion":
                    h=next(f for f in other["findings"] if f["rule"]=="H02")
                    h["quality_comparison"]["limits"]["contract"]["result"]="excluded_boundary"
                quality.verify(other,text,read_layout=layout)

    def test_distinct_limits_have_independent_results_even_on_the_exact_boundary(self):
        for contract,basis,observed,expected in (
            ("柜温不高于4℃","柜温不高于8℃","柜温8℃",("outside","within")),
            ("柜温不高于8℃","柜温不高于4℃","柜温8℃",("within","outside")),
            ("柜温不高于4℃","柜温不高于8mm","柜温8℃",("outside","incomparable")),
            ("柜温不低于-2.50℃","柜温不低于-3.75℃","柜温-4.00℃",("outside","outside")),
            ("柜温不低于-3℃","柜温不高于8℃","柜温0℃",("within","within")),
            ("压力不高于8MPa","柜温不高于3℃","柜温3℃",("incomparable","within")),
        ):
            with self.subTest(contract=contract,basis=basis):
                p,text=example(standard=contract,measure=observed,changes={(2,"inspection_basis"):basis})
                h02=next(f for f in p["findings"] if f["rule"]=="H02")
                q=h02["quality_comparison"]
                self.assertEqual(tuple(q["limits"][role]["result"] for role in ("contract","inspection")),expected)
                self.assertEqual(h02["status"],"issue" if "outside" in expected else "risk")
                if observed=="柜温-4.00℃":
                    self.assertEqual([q["limits"][k]["outside_by"] for k in ("contract","inspection")],["1.50","0.25"])
                steps=[f for f in p["findings"] if "payment_quality" in f]
                self.assertEqual([(f["rule"],f["stage"]["name"]) for f in steps],[("H04","第二期"),("H05","第二期")])
                for f in steps:
                    self.assertEqual(f["payment_quality"]["comparison"],{k:q[k] for k in ("limits","observed")})
                    self.assertTrue(set(q["fields"].values())<=set(f["payment_quality"]["evidence"]))
                quality.verify(p,text)
                verify_findings(p)

    def test_both_standards_and_the_observation_require_unique_printed_rows_for_this_transaction(self):
        for options in (
            {"omissions":[(1,"约定验收标准：柜温不高于3℃")]},
            {"omissions":[(2,"检验依据：柜温不高于5℃")]},
            {"omissions":[(2,"实测结果：柜温3℃")]},
            {"measure":"实测见附页"},
            {"measure":"压力7MPa"},
            {"other":[RECEIPT]},
            {"changes":{(2,"subject"):"另一批设备"}},
            {"changes":{(2,"acceptance_scope"):"数量签收"}},
            {"changes":{(2,"acceptance_result"):"待检"}},
            {"changes":{(2,"inspection_basis"):"柜温≤4.00℃"}},
        ):
            with self.subTest(options=options):
                kwargs=dict(options)
                edits={(2,"inspection_basis"):"柜温不高于8℃",**kwargs.pop("changes",{})}
                p,_=example(changes=edits,**kwargs)
                self.assertFalse(any(f.get("quality_comparison") or f.get("payment_quality",{}).get("comparison") for f in p["findings"]))
        p,text=example(changes={(2,"inspection_basis"):"柜温不高于8℃",(3,"payment_designation"):"采购价款"})
        self.assertEqual([f["rule"] for f in p["findings"] if "quality_comparison" in f or "payment_quality" in f],["H02","H04"])
        quality.verify(p,text)

    def test_contract_and_acceptance_can_be_compared_before_a_bank_receipt_is_submitted(self):
        p,text=example(include_bank=False,changes={(2,"inspection_basis"):"柜温不高于8℃"})
        accepted=next(f for f in p["findings"] if f["rule"]=="H02")
        self.assertEqual(accepted["quality_comparison"]["limits"]["contract"]["outside_by"],"4")
        self.assertFalse(any(f["rule"]=="H05" for f in p["findings"]))
        quality.verify(p,text)
        verify_findings(p)

    def test_limit_locations_are_rechecked_and_matching_legacy_limits_can_still_be_signed(self):
        p,text=example(changes={(2,"inspection_basis"):"柜温不高于8℃"})
        g=p["graph"]
        layouts={node["id"]:{"type":node["layer"],"clause_text_only":node.get("clause_text_only",False),"lines":{}}
                 for node in g["nodes"] if node["type"]=="page"}
        for fact in g["facts"]:
            if line:=fact.get("source_line"):
                layouts[f"{fact['doc']}/p{fact['page']}"]["lines"][str(line["number"])]=line["rects"]
        def layout(doc,page):
            return layouts[f"{doc}/p{page}"]
        quality.verify(p,text,signing=True,read_layout=layout)
        q=next(f["quality_comparison"] for f in p["findings"] if f["rule"]=="H02")
        ref=q["fields"]["inspection_basis"]
        fact=next(f for f in g["facts"] if f["id"]==ref)
        layout(fact["doc"],fact["page"])["lines"][str(fact["source_line"]["number"])]=[]
        with self.assertRaisesRegex(ValueError,"引文位置"):quality.verify(p,text,signing=True,read_layout=layout)
        same,text=example()
        same["policy"].update(version="2026.11.28.8",payment_quality=quality.FIRST_FORMAT)
        same["graph"][quality.KEY]["format"]=quality.FIRST_FORMAT
        quality.verify(same,text,signing=True)

    def test_omitted_comparison_needs_reaudit_and_tampering_breaks_replay(self):
        p,text=example(changes={(2,"inspection_basis"):"柜温不高于8℃"})
        for key in ("result","delta","field","same_unit","omit","edge","stage"):
            with self.subTest(key=key),self.assertRaises(ValueError):
                changed=deepcopy(p)
                h02=next(f for f in changed["findings"] if f["rule"]=="H02")
                q=h02["quality_comparison"]
                if key=="result":q["limits"]["inspection"]["result"]="outside"
                if key=="delta":q["limits"]["contract"]["outside_by"]="8"
                if key=="field":q["fields"]["inspection_basis"]=q["fields"]["acceptance_criteria"]
                if key=="same_unit":q["observed"]["unit"]="mm"
                if key=="omit":del h02["quality_comparison"]
                if key=="edge":changed["graph"]["edges"]=[e for e in changed["graph"]["edges"] if e["type"]!=quality.BASIS_EDGE]
                if key=="stage":next(f for f in changed["findings"] if f["rule"]=="H05").pop("payment_quality")
                quality.verify(changed,text)
        old=p["graph"]
        old[quality.KEY]["format"]=quality.FIRST_FORMAT
        old["edges"]=[e for e in old["edges"] if e["type"] not in (quality.EDGE,quality.BASIS_EDGE)]
        p["findings"]=execute(old,PERFORMANCE)
        p["policy"].update(version="2026.11.28.8",payment_quality=quality.FIRST_FORMAT)
        quality.verify(p,text)
        with self.assertRaisesRegex(ValueError,"重审"):quality.verify(p,text,signing=True)

    def test_only_the_acceptance_installment_inherits_the_measured_breach(self):
        for when,days in (("2026-09-19",-1),("2026-09-20",0),("2026-09-21",1)):
            with self.subTest(when=when):
                p,text=example(date=when)
                checks=[f for f in p["findings"] if "payment_quality" in f]
                self.assertEqual([(c["rule"],c["stage"]["name"],c["status"]) for c in checks],[("H04","第二期","risk"),("H05","第二期","risk")])
                stage,transfer=[f["payment_quality"] for f in checks]
                self.assertNotIn("payment",stage)
                self.assertEqual((transfer["payment"]["days"],transfer["payment"]["paid_on"]),(days,when))
                self.assertEqual(stage["measure"],{"name":"柜温","unit":"°C","operator":"不高于","limit":"4","observed":"8","outside_by":"4"})
                self.assertIn("当日先后待核" if not days else ("早于" if days<0 else "晚于"),checks[-1]["detail"])
                for f in checks:
                    q=f["payment_quality"]
                    self.assertLessEqual(set(q["fields"].values()),set(q["evidence"]))
                    self.assertLessEqual(set(q["evidence"]),set(f["evidence"]))
                quality.verify(p,text)
                verify_findings(p)

    def test_minimum_decimal_negative_temperatures_and_exact_limits(self):
        p,_=example(standard="柜温不低于-2.50℃",measure="柜温-3.75℃")
        records=[f["payment_quality"] for f in p["findings"] if "payment_quality" in f]
        self.assertEqual([r["measure"]["outside_by"] for r in records],["1.25","1.25"])
        for value in ("柜温4℃","柜温3℃","柜温8mm","压力8MPa","柜温1 0℃"):
            with self.subTest(value=value):
                p,_=example(measure=value)
                self.assertFalse(quality.edges(p["findings"]))

    def test_an_unread_second_entry_or_different_transaction_cannot_supply_the_comparison(self):
        for opts,roles in [
            ({"omissions":[(2,"实测结果：柜温3℃")]},[]),
            ({"omissions":[(1,"约定验收标准：柜温不高于10℃")]},[]),
            ({"omissions":[(1,"第二期：到货后支付60%")]},[]),
            ({"changes":{(2,"seller"):"另一家单位"}},[]),
            ({"changes":{(2,"acceptance_scope"):"数量签收"}},[]),
            ({"other":[RECEIPT]},[]),
            ({"omissions":[(2,"验收日期：2026-09-18")]},["H04"]),
            ({"omissions":[(3,"交易日期：2026-09-10")]},["H04"]),
            ({"changes":{(3,"payment_designation"):"设备采购款"}},["H04"]),
            ({"changes":{(3,"payment_designation"):"第一期"}},["H04"]),
            ({"changes":{(3,"payee"):"另一家公司"}},["H04"]),
            ({"changes":{(3,"transfer_status"):"受理中"}},["H04"]),
        ]:
            with self.subTest(opts=opts):
                p,_=example(**opts)
                self.assertEqual([f["rule"] for f in p["findings"] if f.get("payment_quality")],roles)

    def test_each_successful_receipt_has_its_own_date_and_evidence(self):
        p,text=example(other=[BANK_DOC],changes={(4,"paid_on"):"2026-09-18"})
        a,b=[f["payment_quality"] for f in p["findings"] if f["rule"]=="H05"]
        self.assertEqual([(x["payment"]["bank"],x["payment"]["days"]) for x in (a,b)],[("d03",1),("d04",-2)])
        self.assertNotIn(a["fields"]["paid_on"],b["evidence"])
        quality.verify(p,text)

    def test_archive_rejects_changed_observations_edges_dates_and_methods(self):
        p,text=example()
        for mode in ("source","coordinate","sha","delta","edge","state","marker"):
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                changed=deepcopy(p)
                f=next(r for r in changed["findings"] if r["rule"]=="H05")
                measure=next(r for r in changed["graph"]["facts"] if r["id"]==f["payment_quality"]["fields"]["measured_result"])
                if mode=="source": changed["graph"][quality.KEY]["rows"][-1]["quote"]="不同的付款原行"
                if mode=="coordinate": measure["source_line"]["number"]+=1
                if mode=="sha": measure["page_sha256"]="unrelated"
                if mode=="delta": f["payment_quality"]["payment"]["days"]=5
                if mode=="edge": changed["graph"]["edges"].pop()
                if mode=="state": f["status"]="ok"
                if mode=="marker": changed["policy"].pop("payment_quality")
                quality.verify(changed,text)
        graph=p["graph"]
        graph.pop(quality.KEY)
        graph["edges"]=[e for e in graph["edges"] if e["type"]!=quality.EDGE]
        p["policy"].update(version="2026.11.27.16")
        p["policy"].pop("payment_quality")
        p["findings"]=execute(graph,PERFORMANCE)
        quality.verify(p,None)
        self.assertFalse(any("payment_quality" in f for f in p["findings"]))
