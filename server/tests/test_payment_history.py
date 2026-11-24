from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

from calculations import FORMAT
from config import BANK, CaseError
from controls import VERSION, conclusion, execute
from evidence import export_bundle
from graph import build_graph, link_procedures
from identity import Directory
from jobs import CODE_DIGESTS, METHODS
from payment_history import LIMIT
from policy import link_sources
from storage import Store, encode
from test_transfers import receipt_material
from verify import replay_rules, sha, verify, verify_payment_history


class PaymentHistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = Store(self.root)

    def workpaper(self, case_id, *, fresh=True, history=True, workspace="local", user=None, contract_variant=0, legacy=False, **fields):
        docs, pages = receipt_material(**fields)
        for doc, page in zip(docs, pages):
            # The controlled extractor supplies the text layer. The bundle still carries real image bytes.
            photo = io.BytesIO()
            variant = contract_variant if doc["id"]=="d01" else 0
            Image.new("RGB", (24, 20), color=(12+variant, 34, int(doc["id"][1:]))).save(photo, format="JPEG")
            data = photo.getvalue()
            doc.update(ext=".jpg", size=len(data), sha256=sha(data))
            page.update(sha256=sha(data), width=24, height=20)
            path = self.store.files / case_id / doc["id"]
            path.mkdir(parents=True, exist_ok=True)
            (path / "original.jpg").write_bytes(data)
            (path / "1.jpg").write_bytes(data)
        if fresh:
            self.store.create(case_id, "演练 "+case_id, docs, case_id, case_id, BANK, workspace, user)
            for doc, page in zip(docs, pages):
                self.store.put_pages(case_id, doc["id"], [page])
        with patch("graph.attach_payment_references") if legacy else nullcontext():
            graph = build_graph(docs, pages, self.store.attestations(case_id), self.store.amendments(case_id))
        graph["profile"] = BANK
        lookup = (lambda signature: self.store.payment_history(case_id, signature)) if history else None
        findings = execute(graph, BANK, lookup)
        calls = {"expert": {"model": "fixture", "output": {"followups": []}}, "pages": [
            {"model":"fixture", "doc":p["doc"], "page":1, "page_sha256":p["sha256"],
             "output":p["extraction"]["output"]} for p in pages]}
        link_procedures(graph, findings, calls)
        link_sources(graph)
        policy = {**VERSION, "profile": BANK, "code_sha256": CODE_DIGESTS, "calculations": FORMAT, "archived_methods": True}
        methods = METHODS
        if legacy:
            policy.pop("payment_references")
            policy["code_sha256"] = {k:v for k,v in CODE_DIGESTS.items() if k!="payment_reference.py"}
            methods = {k:v for k,v in METHODS.items() if k!="payment_reference.py"}
        if not history or legacy:
            policy.pop("payment_checks")
            policy["code_sha256"] = {k:v for k,v in policy["code_sha256"].items() if k!="payment_checks.py"}
            methods = {k:v for k,v in methods.items() if k!="payment_checks.py"}
        report = {"case_id": case_id, "graph": graph, "findings": findings, "result": conclusion(findings), "policy": policy, "calls": calls}
        self.store.save_report(case_id, report, sha(encode(report).encode()), methods)
        return report

    def sign(self, case, decision="approve"):
        self.store.review(case, 1, "演练验收", "合成底稿回归", decision)

    def assert_controls(self, report, same, full):
        self.assertEqual({f["rule"]: f["status"] for f in report["findings"] if f["rule"] in {"B06", "B07"}},
                         {"B06": same, "B07": full})

    def installment(self,case,amount="4200.00",reference="YL-FIRST",**fields):
        return self.workpaper(case,payment_term="分期付款",transfer_amount=amount,transfer_ref=reference,**fields)

    def test_installment_totals_use_unique_approved_receipts_and_pinned_sources(self):
        first = self.installment("first")
        self.sign("first")
        duplicate = self.installment("same-receipt")
        duplicate_calc = duplicate["graph"]["payment_history"]["installments"]["calculation"]
        self.assertEqual((duplicate_calc["paid_total"],len(duplicate_calc["payments"][0]["copies"])),("4200.00",1))
        self.sign("same-receipt")
        self.installment("returned",amount="2700.00",reference="YL-RETURN")
        self.sign("returned","return")
        self.installment("pending",amount="1800.00",reference="YL-ESCALATED")
        self.sign("pending","escalate")
        next_payment = self.installment("second","4350.01","YL-SECOND",paid_on="2026-10-22")
        window = next_payment["graph"]["payment_history"]["installments"]
        self.assertEqual({m["case_id"] for m in window["matches"]},{"first","same-receipt"})
        calc = window["calculation"]
        self.assertEqual((len(calc["payments"]),calc["paid_total"],calc["difference"]),(2,"8550.01","150.01"))
        self.assertEqual(len(calc["payments"][0]["copies"]),1)
        self.assertTrue(calc["payments"][0]["amount_fact"].startswith("prior/"))
        self.assertEqual([f["status"] for f in next_payment["findings"] if f["rule"]=="B08"],["risk"])
        first_calc = first["graph"]["payment_history"]["installments"]["calculation"]
        self.assertEqual(first_calc["difference"],"-4200.00")
        buf=io.BytesIO()
        export_bundle(self.store,"second",1,buf)
        self.assertEqual(verify(buf,True)[:2],("second",1))
        with zipfile.ZipFile(buf) as archive:
            journal=json.loads(archive.read("journal.json"))
            hashes={e["path"]:e["sha256"] for e in json.loads(archive.read("manifest.json"))["files"]}
            for target in ("entry","difference","citation","decision"):
                bad=deepcopy(next_payment)
                changed=bad["graph"]["payment_history"]["installments"]
                if target=="entry": changed["matches"][0]["entry"]["amount"]="999.00"
                if target=="difference": changed["calculation"]["difference"]="0.00"
                if target=="citation": changed["matches"][0]["evidence"][-1]["quote"]="错引的测试原文"
                if target=="decision": changed["matches"][0]["decision"]="return"
                with self.subTest(target=target), self.assertRaises(ValueError):
                    verify_payment_history(archive,hashes,bad,journal)

    def test_installment_uncertainty_never_produces_a_partial_sum(self):
        self.installment("base")
        self.sign("base")
        for key,opts in (("amount",{"amount":"4199.00"}),("date",{"paid_on":"2026-10-21"}),
                         ("ceiling",{"total":"9900.00"}),("account",{"payee_account":"****0081"}),
                         ("different-original",{"contract_variant":80}),
                         ("currency",{"currency":"美元"}),("status",{"transfer_status":"已受理"})):
            with self.subTest(key=key):
                result=self.installment(key,**opts)["graph"]["payment_history"]["installments"]["calculation"]
                self.assertIn(result["state"],{"conflict","missing"})
                self.assertNotIn("paid_total",result)
        other=self.workpaper("amended-contract",payment_term="分期付款，须扣减退款",transfer_ref="YL-AMEND")
        self.assertEqual(other["graph"]["payment_history"]["installments"]["calculation"]["state"],"missing")
        self.workpaper("full-contract",transfer_ref="YL-ADDITIONAL")
        self.sign("full-contract")
        blocked=self.installment("different-terms","4300.00","YL-NEW")
        self.assertEqual(blocked["graph"]["payment_history"]["installments"]["calculation"]["state"],"conflict")
        directory=Directory(self.store)
        session,wid=directory.register({"login":"other-payer","name":"演练","password":"synthetic-password-42","workspace":"乙"})
        tenant=self.installment("other-tenant",workspace=wid,user=directory.user(session))
        self.assertEqual(tenant["graph"]["payment_history"]["installments"]["count"],0)

    def test_new_distinct_installment_blocks_stale_initial_and_peer_approval(self):
        self.installment("first")
        stale=self.installment("later","4350.00","YL-SECOND")
        self.installment("peer","4351.00","YL-THIRD")
        self.sign("peer","escalate")
        self.sign("first")
        with self.assertRaisesRegex(CaseError,"新的已签收付款线索"):
            self.sign("later")
        source=self.store.detail("peer")["referrals"][0]
        b08=next(f["id"] for f in stale["findings"] if f["rule"]=="B08")
        with self.assertRaisesRegex(CaseError,"新的已签收付款线索"):
            self.store.resolve_referral("peer",1,source["report_hash"],source["signoff_hash"],"独立复核","复核分期凭证","approve",[b08])
        self.assertEqual(self.store.detail("peer")["status"],"in_review")
        fresh=self.installment("later","4350.00","YL-SECOND",fresh=False)
        self.assertEqual(fresh["graph"]["payment_history"]["installments"]["calculation"]["difference"],"150.00")

    def test_installment_rechecks_original_even_for_printed_native_text(self):
        self.installment("approved-originals")
        self.sign("approved-originals")
        path=self.store.files/"approved-originals"/"d02"/"original.jpg"
        original=path.read_bytes()
        path.write_bytes(b"changed fixture")
        with self.assertRaisesRegex(CaseError,"来源摘要不符"):
            self.installment("blocked","4200.01","YL-SECOND")
        self.assertEqual(self.store.detail("blocked")["rev"],0)
        path.write_bytes(original)
        report=self.installment("blocked","4200.01","YL-SECOND",fresh=False)
        self.assertEqual(report["graph"]["payment_history"]["installments"]["calculation"]["difference"],"0.01")

    def test_two_distinct_installments_cannot_sign_the_same_history_concurrently(self):
        self.installment("thread-a","4200.00","YL-THREAD-A")
        self.installment("thread-b","4350.00","YL-THREAD-B")
        barrier=threading.Barrier(2)
        def approve(case):
            barrier.wait(timeout=5)
            try:
                self.sign(case)
                return 200
            except CaseError as error:
                return error.status
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(executor.map(approve,("thread-a","thread-b")),[200,409])

    def test_installment_index_migration_limit_and_wrong_historical_scope(self):
        from installments import LIMIT
        for n in range(LIMIT+1):
            self.installment("history-"+str(n),"100.00","YL-HIST-"+str(n))
            self.sign("history-"+str(n))
        with self.store.connect(True) as db:
            db.execute("DROP TABLE contract_payments")
            db.execute("PRAGMA user_version=3")
        self.store=Store(self.root)
        report=self.installment("over-limit","10.00","YL-NEXT")
        window=report["graph"]["payment_history"]["installments"]
        self.assertEqual((window["count"],len(window["matches"]),window["calculation"]["state"]),(LIMIT+1,LIMIT,"incomplete"))
        self.assertNotIn("paid_total",window["calculation"])
        bundle=io.BytesIO()
        export_bundle(self.store,"over-limit",1,bundle)
        self.assertEqual(verify(bundle,True)[:2],("over-limit",1))
        self.installment("other-contract",contract_id="OTHER-CONTRACT")
        self.sign("other-contract")
        with self.store.connect(True) as db:
            db.execute("UPDATE contract_payments SET contract_key=(SELECT contract_key FROM contract_payments WHERE case_id='history-0') WHERE case_id='other-contract'")
        with self.assertRaisesRegex(CaseError,"历史合同"):
            self.installment("corrupt-index")

    def test_scope_decisions_and_legacy_backfill(self):
        legacy = self.workpaper("archived", history=False)
        self.sign("archived")
        self.workpaper("returned")
        self.sign("returned", "return")
        self.workpaper("pending")
        with self.store.connect(True) as db:
            db.execute("DROP TABLE payment_index")
            db.execute("PRAGMA user_version=2")
        self.store = Store(self.root)
        self.assertEqual(legacy, self.store.report("archived", 1)["report"])
        same = self.workpaper("copy")
        self.assert_controls(same, "risk", "ok")
        matches = same["graph"]["payment_history"]["matches"]
        self.assertEqual({(m["case_id"], m["decision"]) for m in matches}, {("archived", "approve"), ("returned", "return")})
        self.assertTrue(all({f["field"] for f in m["evidence"]} == {"transfer_ref", "payer"} for m in matches))
        full = self.workpaper("another", transfer_ref="YL-081-B")
        self.assert_controls(full, "ok", "risk")
        self.assertEqual([m["case_id"] for m in full["graph"]["payment_history"]["matches"]], ["archived"])
        directory = Directory(self.store)
        session, workspace = directory.register({"login":"fixture-other", "name":"演练", "password":"synthetic-password-42", "workspace":"乙企业"})
        unrelated = self.workpaper("other", workspace=workspace, user=directory.user(session))
        self.assert_controls(unrelated, "ok", "ok")
        with self.store.connect() as db, self.assertRaises(CaseError):
            self.store.signed_source(db, "other", "archived", 1)

    def test_payment_history_keeps_escalated_and_peer_approved_sources(self):
        base = self.workpaper("peer-base")
        self.sign("peer-base","escalate")
        interim = self.workpaper("before-resolution")
        self.assert_controls(interim,"risk","ok")
        self.assertEqual(interim["graph"]["payment_history"]["matches"][0]["decision"],"escalate")
        before = self.workpaper("other-reference-before",transfer_ref="YL-another")
        self.assert_controls(before,"ok","ok")
        pin = self.store.detail("peer-base")["referrals"][0]
        fid = next(f["id"] for f in base["findings"] if f["rule"]=="B07")
        self.store.resolve_referral("peer-base",1,pin["report_hash"],pin["signoff_hash"],"复核人员","已核对全额结算依据。","approve",[fid])
        fresh = self.workpaper("other-reference-after",transfer_ref="YL-another")
        self.assert_controls(fresh,"ok","risk")
        match = fresh["graph"]["payment_history"]["matches"][0]
        self.assertEqual((match["case_id"],match["rev"],match["decision"]),("peer-base",2,"approve"))
        for cid, prior_rev in (("before-resolution",1),("other-reference-after",2)):
            buf = io.BytesIO()
            export_bundle(self.store,cid,1,buf)
            self.assertEqual(verify(buf,True)[:2],(cid,1))
            with zipfile.ZipFile(buf) as z:
                self.assertEqual("prior/peer-base/r2/review/referral.json" in z.namelist(),prior_rev==2)
                prior = json.loads(z.read(f"prior/peer-base/r{prior_rev}/signoff.json"))
                self.assertEqual(prior["decision"],"approve" if prior_rev==2 else "escalate")

    def test_historical_payment_replays_human_checked_transfer_reference(self):
        original = self.workpaper("checked-payment")
        ref = next(f["id"] for f in original["graph"]["facts"] if f["field"]=="transfer_ref")
        self.store.review("checked-payment",1,"演练核图","已核流水号。","confirm",[ref])
        self.workpaper("checked-payment",fresh=False)
        self.store.review("checked-payment",2,"验收员","已核回单。","approve")
        found = self.workpaper("later-copy")
        self.assert_controls(found,"risk","ok")
        buf = io.BytesIO()
        export_bundle(self.store,"later-copy",1,buf)
        self.assertEqual(verify(buf,True)[:2],("later-copy",1))
        with zipfile.ZipFile(buf) as z:
            self.assertIn("prior/checked-payment/r2/field-checks/r1/report.json",z.namelist())
        field = next(f for f in original["graph"]["facts"] if f["id"]==ref)
        (self.store.files/"checked-payment"/field["doc"]/"original.jpg").write_bytes(b"damaged historical synthetic upload")
        with self.assertRaisesRegex(CaseError,"来源摘要不符"):
            self.workpaper("unverifiable-copy")
        self.assertEqual(self.store.detail("unverifiable-copy")["rev"],0)

    def test_new_payment_blocks_stale_peer_approval(self):
        source = self.workpaper("first-referral")
        self.sign("first-referral","escalate")
        self.workpaper("later-cleared",transfer_ref="YL-later")
        self.sign("later-cleared")
        pin = self.store.detail("first-referral")["referrals"][0]
        args = ("first-referral",1,pin["report_hash"],pin["signoff_hash"],"第二位","已核原账与回单。")
        findings = [source["findings"][0]["id"]]
        with self.assertRaisesRegex(CaseError,"最新付款记录"):
            self.store.resolve_referral(*args,"approve",findings)
        self.assertEqual(self.store.detail("first-referral")["status"],"in_review")
        self.assertEqual(self.store.resolve_referral(*args,"return",findings),2)

    def test_currency_amount_names_dates_and_masked_references(self):
        self.workpaper("base", transfer_ref="00001234")
        self.sign("base")
        for i, (fields, expected) in enumerate([
                ({"transfer_ref":"1234"}, ("ok","risk")),
                ({"transfer_ref":"XXXX1234"}, ("missing","missing")),
                ({"transfer_ref":None}, ("missing","missing")),
                ({"transfer_ref":"00001234","currency":"美元"}, ("risk","missing")),
                ({"transfer_ref":"OTHER","transfer_status":"已受理"}, ("ok","missing")),
                ({"transfer_ref":"OTHER","payment_term":"分期结算"}, ("ok","missing")),
                ({"transfer_ref":"OTHER","total":"0.00","transfer_amount":"0"}, ("ok","missing")),
                ({"transfer_ref":"OTHER","payee_account":"********0081"}, ("ok","missing")),
                ({"transfer_ref":"OTHER","total":"9,000","transfer_amount":"9,000"}, ("ok","ok")),
                ({"transfer_ref":"00001234","payer":"演练丙","buyer":"演练丙"}, ("ok","ok")),
                ({"transfer_ref":"OTHER","paid_on":"2026-10-01"}, ("ok","missing"))]):
            with self.subTest(fields=fields):
                self.assert_controls(self.workpaper("probe"+str(i), **fields), *expected)
        self.workpaper("case-sensitive", contract_id="YL-lower", transfer_ref="lower-A")
        self.sign("case-sensitive")
        self.assert_controls(self.workpaper("upper", contract_id="YL-lower", transfer_ref="LOWER-A"), "ok", "risk")

    def test_concurrent_approvals_require_new_review_and_frozen_replay(self):
        cases = ["batch-A", "batch-B"]
        initial = [self.workpaper(cid, transfer_ref=cid) for cid in cases]
        barrier = threading.Barrier(2)
        def decide(cid):
            barrier.wait(timeout=5)
            try:
                self.sign(cid)
                return "approved"
            except CaseError as error:
                self.assertEqual(error.status, 409)
                return "stale"
        with ThreadPoolExecutor(max_workers=2) as pool:
            decisions = list(pool.map(decide, cases))
        self.assertCountEqual(decisions, ["approved", "stale"])
        index = decisions.index("stale")
        cid = cases[index]
        self.assertEqual(self.store.detail(cid)["status"], "ready")
        self.store.rerun(cid, 1)
        revised = self.workpaper(cid, fresh=False, transfer_ref=cid)
        self.assert_controls(revised, "ok", "risk")
        self.assert_controls(initial[index], "ok", "ok")
        replay_rules(self.store.report(cid, 1)["report"])
        replay_rules(revised)
        self.store.review(cid, 2, "演练验收", "已核对两笔流水，升级复核", "escalate")

    def test_bundle_links_originals_signoffs_and_exact_citations(self):
        self.workpaper("base")
        self.sign("base")
        report = self.workpaper("second", transfer_ref="YL-081-B")
        stream = io.BytesIO()
        export_bundle(self.store, "second", 1, stream)
        self.assertEqual(verify(stream, True)[:2], ("second", 1))
        with zipfile.ZipFile(stream) as bundle:
            hashes = {r["path"]: r["sha256"] for r in json.loads(bundle.read("manifest.json"))["files"]}
            self.assertIn("prior/base/r1/originals/d02.jpg", hashes)
            journal = json.loads(bundle.read("journal.json"))
            for field, value in (("decision", "return"), ("title", "被替换的底稿"), ("signed_at", "2000-01-01T00:00:00+00:00")):
                modified = deepcopy(report)
                modified["graph"]["payment_history"]["matches"][0][field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    verify_payment_history(bundle, hashes, modified, journal)
            modified = deepcopy(report)
            modified["graph"]["payment_history"]["matches"][0]["evidence"][0]["quote"] += "虚构"
            with self.assertRaisesRegex(ValueError, "逐字引文"):
                verify_payment_history(bundle, hashes, modified, journal)

    def test_bounded_lookup_keeps_exact_count(self):
        for i in range(LIMIT+2):
            cid = "returned-"+str(i)
            self.workpaper(cid)
            self.sign(cid, "return")
        current = self.workpaper("copy")
        history = current["graph"]["payment_history"]
        self.assertEqual(history["counts"], {"same": LIMIT+2, "full": 0})
        self.assertEqual(len(history["matches"]), LIMIT)
        self.assertTrue(any("列示最近签收" in f["detail"] for f in current["findings"]))

    def test_invalid_index_cannot_create_a_finding_against_unrelated_originals(self):
        self.workpaper("base", transfer_ref="YL-AAA")
        self.sign("base")
        with self.store.connect(True) as db:
            db.execute("UPDATE payment_index SET reference='YL-BBB' WHERE case_id='base'")
        with self.assertRaisesRegex(CaseError, "与已签收底稿中的原文不一致"):
            self.workpaper("new", transfer_ref="YL-BBB")

    def test_missing_payment_indexes_are_restored_once_from_the_signed_workpaper(self):
        from payment_history import payment_record
        first = self.installment("first")
        self.sign("first")
        copy = self.installment("copy")
        signature = payment_record(copy["graph"], copy["findings"])
        with self.store.connect(True) as db:
            db.execute("DELETE FROM payment_index WHERE case_id='first'")
            db.execute("DELETE FROM contract_payments WHERE case_id='first'")
        barrier = threading.Barrier(2)
        def lookup(_):
            barrier.wait(timeout=5)
            return self.store.payment_history("copy", signature)
        with ThreadPoolExecutor(max_workers=2) as pool:
            for result in pool.map(lookup, range(2)):
                self.assertEqual((result["counts"]["same"],result["installments"]["count"]), (1,1))
                self.assertEqual(result["installments"]["calculation"]["paid_total"], "4200.00")
        self.assertEqual(first, self.store.report("first",1)["report"])
        with self.store.connect() as db:
            messages = [r[0] for r in db.execute("SELECT message FROM events WHERE case_id='first' AND stage='payment_index'")]
            self.assertEqual(len(messages), 1)
            self.assertIn("流水、合同付款", messages[0])
            self.assertIsNone(db.execute("SELECT 1 FROM payment_index_pending WHERE case_id='first'").fetchone())

    def test_missing_current_and_historical_indexes_do_not_allow_stale_approval(self):
        self.workpaper("signed-before-approval", transfer_ref="YL-FIRST")
        self.workpaper("stale", transfer_ref="YL-SECOND")
        peer = self.workpaper("peer", transfer_ref="YL-THIRD")
        self.sign("peer","escalate")
        self.sign("signed-before-approval")
        with self.store.connect(True) as db:
            for table in ("payment_index","contract_payments"):
                db.execute("DELETE FROM "+table)
        with self.assertRaisesRegex(CaseError,"新的已签收付款线索"):
            self.sign("stale")
        pin = self.store.detail("peer")["referrals"][0]
        finding = next(f["id"] for f in peer["findings"] if f["rule"]=="B07")
        with self.assertRaisesRegex(CaseError,"新的已签收付款线索"):
            self.store.resolve_referral("peer",1,pin["report_hash"],pin["signoff_hash"],"独立复核","核对原流水","approve",[finding])
        self.assertEqual(self.store.detail("stale")["status"],"ready")
        self.assertEqual(self.store.detail("peer")["status"],"in_review")
        current = self.workpaper("stale",fresh=False,transfer_ref="YL-SECOND")
        self.assert_controls(current,"ok","risk")

    def test_missing_contract_projection_keeps_uncountable_signed_history_and_checks_tenant(self):
        self.installment("incomplete",transfer_status="已受理")
        self.sign("incomplete")
        directory = Directory(self.store)
        session, other = directory.register({"login":"bank-index-other","name":"演练","password":"synthetic-password-42","workspace":"乙"})
        self.installment("other",workspace=other,user=directory.user(session))
        self.store.review("other",1,"演练验收","异企业演练","approve",actor=directory.user(session)["id"])
        with self.store.connect(True) as db:
            db.execute("DELETE FROM contract_payments WHERE case_id IN ('incomplete','other')")
            db.execute("PRAGMA user_version=5")
        self.store = Store(self.root)
        history = self.installment("later",reference="YL-NEXT")["graph"]["payment_history"]["installments"]
        self.assertEqual([(m["case_id"],m["entry"]) for m in history["matches"]],[("incomplete",None)])
        self.assertNotIn("paid_total",history["calculation"])
        with self.store.connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM contract_payments WHERE case_id='other'").fetchone())
            self.assertIsNotNone(db.execute("SELECT 1 FROM payment_index_pending WHERE case_id='other'").fetchone())
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 7)

    def test_damaged_signed_payment_archive_cannot_silently_disappear(self):
        self.installment("signed")
        self.sign("signed")
        with self.store.connect(True) as db:
            db.execute("DELETE FROM contract_payments WHERE case_id='signed'")
            db.execute("UPDATE reports SET content=content || ' ' WHERE case_id='signed'")
        with self.assertRaisesRegex(CaseError,"归档摘要不符"):
            self.installment("later",reference="YL-NEXT")
        self.assertEqual(self.store.detail("later")["rev"],0)

    def test_historical_partial_receipt_is_visible_but_cannot_supply_an_amount_or_match(self):
        note = "交易流水号说明：仅显示后四位"
        # Issue the old rows as they stood before qualification was added, then open the upgraded store.
        with patch("payment_index.checked_references",return_value=[]):
            original = self.installment("historical",reference="0042",reference_note=note,legacy=True)
            self.sign("historical")
        with self.store.connect(True) as db:
            db.execute("ALTER TABLE payment_index DROP COLUMN reference_eligible")
            db.execute("PRAGMA user_version=6")
        self.store = Store(self.root)
        new = self.installment("complete",reference="0042")
        history = new["graph"]["payment_history"]
        self.assertEqual(history["counts"],{"same":0,"full":0})
        window = history["installments"]
        self.assertEqual((window["count"],window["calculation"]["state"]),(1,"missing"))
        self.assertNotIn("paid_total",window["calculation"])
        match = window["matches"][0]
        self.assertIsNone(match["entry"])
        self.assertEqual(match["incomplete_references"][0]["lines"][-1]["text"],note)
        self.assertEqual(self.store.report("historical",1)["report"],original)
        with self.store.connect() as db:
            row = db.execute("SELECT reference,reference_eligible FROM payment_index WHERE case_id='historical'").fetchone()
            self.assertEqual(tuple(row),("0042",0))
        bundle = io.BytesIO()
        export_bundle(self.store,"complete",1,bundle)
        self.assertEqual(verify(bundle,True)[:2],("complete",1))
        with zipfile.ZipFile(bundle) as archive:
            hashes={e["path"]:e["sha256"] for e in json.loads(archive.read("manifest.json"))["files"]}
            journal=json.loads(archive.read("journal.json"))
            changed=deepcopy(new)
            item=changed["graph"]["payment_history"]["installments"]["matches"][0]
            item["incomplete_references"][0]["lines"][-1]["number"]-=1
            with self.assertRaisesRegex(ValueError,"历史回单遮盖提示"):
                verify_payment_history(archive,hashes,changed,journal)

    def test_legacy_initial_and_peer_approval_check_current_and_previously_counted_partial_references(self):
        from payment_index import LegacyPartialTransfer
        with patch("payment_index.checked_references",return_value=[]):
            old = self.installment("masked-pending",reference="26XX0042",legacy=True)
            peer = self.installment("masked-peer",reference="26XX0042",legacy=True)
            self.sign("masked-peer","escalate")
            self.installment("paid",reference="0042",reference_note="银行流水号说明：仅显示末4位",legacy=True)
            self.sign("paid")
            total = self.installment("old-total",amount="4350.00",reference="OTHER-43",legacy=True)
        self.assertEqual(total["graph"]["payment_history"]["installments"]["calculation"]["paid_total"],"8550.00")
        with self.store.connect(True) as db:
            db.execute("UPDATE payment_index SET reference_eligible=NULL")
        with self.assertRaises(LegacyPartialTransfer) as blocked:
            self.sign("masked-pending")
        self.assertEqual(blocked.exception.fields[0]["value"],"26XX0042")
        self.assertEqual(old,self.store.report("masked-pending",1)["report"])
        pin=self.store.detail("masked-peer")["referrals"][0]
        finding=next(f["id"] for f in peer["findings"] if f["rule"]=="B05")
        with self.assertRaisesRegex(LegacyPartialTransfer,"退回补件"):
            self.store.resolve_referral("masked-peer",1,pin["report_hash"],pin["signoff_hash"],"独立复核","复核凭证","approve",[finding])
        with self.assertRaisesRegex(LegacyPartialTransfer,"旧版累计金额") as historical:
            self.sign("old-total")
        self.assertEqual((historical.exception.case_id,historical.exception.revision),("paid",1))
        self.assertEqual(self.store.detail("old-total")["status"],"ready")

    def test_corrupt_reference_eligibility_or_native_text_cannot_release_a_payment_report(self):
        self.installment("first")
        self.sign("first")
        with self.store.connect(True) as db:
            db.execute("UPDATE payment_index SET reference_eligible=0 WHERE case_id='first'")
        with self.assertRaisesRegex(CaseError,"历史付款索引"):
            self.installment("bad-flag",reference="YL-NEXT")
        with self.store.connect(True) as db:
            db.execute("UPDATE payment_index SET reference_eligible=1 WHERE case_id='first'")
            db.execute("UPDATE pages SET text=text||' ' WHERE case_id='first' AND doc='d02'")
        with self.assertRaisesRegex(CaseError,"流水的原文"):
            self.installment("bad-text",reference="YL-NEXT")

    def test_native_same_reference_and_full_settlement_require_the_cited_original_and_page(self):
        self.workpaper("paid")
        self.sign("paid")
        for case,reference,doc,name in (("copy","YL-081-A","d02","original.jpg"),("another","YL-OTHER","d01","1.jpg")):
            with self.subTest(case=case):
                path = self.store.files/"paid"/doc/name
                original = path.read_bytes()
                path.write_bytes(b"replaced synthetic file")
                with self.assertRaisesRegex(CaseError,"来源摘要不符"):
                    self.workpaper(case,transfer_ref=reference)
                self.assertEqual(self.store.detail(case)["rev"],0)
                path.write_bytes(original)
                self.assert_controls(self.workpaper(case,fresh=False,transfer_ref=reference),
                                     "risk" if case=="copy" else "ok","ok" if case=="copy" else "risk")

    def test_initial_and_peer_approval_verify_pinned_files_and_signoff_again(self):
        from field_sources import PaymentSourceError
        self.workpaper("prior")
        self.sign("prior")
        self.workpaper("next",transfer_ref="YL-NEXT")
        peer = self.workpaper("peer",transfer_ref="YL-PEER")
        self.sign("peer","escalate")
        pin = self.store.detail("peer")["referrals"][0]
        fid = next(f["id"] for f in peer["findings"] if f["rule"]=="B07")
        path = self.store.files/"prior"/"d02"/"1.jpg"
        original = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(PaymentSourceError,"无法读取") as missing:
            self.sign("next")
        cited = missing.exception.source
        self.assertEqual((cited["case_id"],cited["rev"],cited["doc"],cited["page"],cited["file"]),("prior",1,"d02",1,"page"))
        self.assertTrue(cited["fact"].startswith("d02/p1/"))
        with self.assertRaisesRegex(CaseError,"无法读取"):
            self.store.resolve_referral("peer",1,pin["report_hash"],pin["signoff_hash"],"复核人乙","比对前案付款","approve",[fid])
        self.assertEqual(self.store.detail("next")["status"],"ready")
        self.assertEqual(self.store.detail("peer")["status"],"in_review")
        path.write_bytes(original)
        with self.store.connect(True) as db:
            db.execute("UPDATE signoffs SET note='签收文本变化' WHERE case_id='prior'")
        with self.assertRaisesRegex(CaseError,"签收决定与出具时的摘要"):
            self.sign("next")
        with self.store.connect(True) as db:
            db.execute("UPDATE signoffs SET note='合成底稿回归' WHERE case_id='prior'")
        self.sign("next")
        messages = [e["message"] for e in self.store.detail("next")["events"] if e["stage"]=="payment_sources"]
        self.assertEqual(len(messages),1)
        self.assertIn("1 份历史签收底稿，共 8 个原件及页图",messages[0])

    def test_otherwise_valid_pdf_and_page_do_not_override_a_changed_contract_text_layer(self):
        self.workpaper("prior")
        self.sign("prior")
        self.workpaper("issued",transfer_ref="YL-ISSUED")
        with self.store.connect(True) as db:
            db.execute("UPDATE pages SET text=text||' ' WHERE case_id='prior' AND doc='d01'")
        with self.assertRaisesRegex(CaseError,"文字层与归档摘要"):
            self.workpaper("next",transfer_ref="YL-NEXT")
        with self.assertRaisesRegex(CaseError,"文字层与归档摘要"):
            self.sign("issued")
        self.assertEqual(self.store.detail("issued")["decisions"],[])

    def test_approval_hashes_outside_writer_and_detects_file_change_before_decision(self):
        import sqlite3
        from field_sources import FieldSources
        self.workpaper("approval")
        hashed,resume = threading.Event(),threading.Event()
        read = FieldSources.read_files
        def stall(source):
            read(source)
            hashed.set()
            if not resume.wait(timeout=5):
                raise AssertionError("timed out waiting for test")
        path = self.store.files/"approval"/"d02"/"original.jpg"
        original = path.read_bytes()
        with patch.object(FieldSources,"read_files",stall), ThreadPoolExecutor(max_workers=1) as pool:
            attempt = pool.submit(self.sign,"approval")
            try:
                self.assertTrue(hashed.wait(timeout=5))
                with sqlite3.connect(self.store.path,timeout=.2) as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("UPDATE cases SET title=title WHERE id='approval'")
                path.write_bytes(original+b"changed during review")
            finally:
                resume.set()
            with self.assertRaisesRegex(CaseError,"页图已变更"):
                attempt.result(timeout=5)
        self.assertEqual(self.store.detail("approval")["decisions"],[])
        path.write_bytes(original)
        self.sign("approval")

    def replace_draft(self, draft):
        raw=encode(draft)
        with self.store.connect(True) as db:
            db.execute("UPDATE reports SET content=?,hash=? WHERE case_id=? AND rev=1",
                       (raw,sha(raw.encode()),draft["case_id"]))

    def test_initial_and_offline_checks_reconstruct_the_full_signed_citation_list(self):
        self.workpaper("signed")
        self.sign("signed")
        original=self.workpaper("later",transfer_ref="YL-SECOND")
        bundle=io.BytesIO()
        export_bundle(self.store,"later",1,bundle)
        with zipfile.ZipFile(bundle) as archive:
            hashes={e["path"]:e["sha256"] for e in json.loads(archive.read("manifest.json"))["files"]}
            journal=json.loads(archive.read("journal.json"))
            for change in ("omit citation","status","wording","duplicate","early cutoff","future cutoff"):
                draft=deepcopy(original)
                finding=next(f for f in draft["findings"] if f["rule"]=="B07")
                if change=="omit citation":
                    match=draft["graph"]["payment_history"]["matches"][0]
                    omitted=match["evidence"].pop()
                    finding["evidence"].remove(omitted["id"])
                elif change=="status":
                    finding["status"]="ok"
                elif change=="wording":
                    finding["detail"]="演练：没有查到另一笔付款。"
                elif change=="duplicate":
                    draft["findings"].append(deepcopy(finding))
                else:
                    history=draft["graph"]["payment_history"]
                    old=history["as_of"]
                    history["as_of"]="2000-01-01T00:00:00+00:00" if change=="early cutoff" else "2099-01-01T00:00:00+00:00"
                    for item in draft["findings"]:
                        item["detail"]=item["detail"].replace(old,history["as_of"])
                self.replace_draft(draft)
                with self.subTest(change=change):
                    with self.assertRaises(CaseError) as rejected:
                        self.sign("later")
                    self.assertEqual(rejected.exception.status,409)
                    with self.assertRaises(ValueError):
                        verify_payment_history(archive,hashes,draft,journal,issued_at=journal["revisions"][0]["created"])
                    self.assertEqual(self.store.detail("later")["decisions"],[])
        self.replace_draft(original)
        self.sign("later")

    def test_peer_compares_even_an_internally_consistent_total_to_the_signed_payment(self):
        from installments import calculate, finding as installment_finding
        from payment_history import payment_record
        self.installment("first")
        self.sign("first")
        draft=self.installment("second","4350.00","YL-SECOND")
        history=draft["graph"]["payment_history"]
        window=history["installments"]
        basis=payment_record(draft["graph"],draft["findings"])["installment"]
        window["matches"][0]["entry"]["amount"]="4000.00"
        window["calculation"]=calculate(basis,window)
        self.assertEqual(window["calculation"]["paid_total"],"8350.00")
        rule=next(f for f in draft["findings"] if f["rule"]=="B08")
        status,detail,refs=installment_finding(basis,window,history["as_of"])
        rule.update(status=status,detail=detail,evidence=list(dict.fromkeys(refs)))
        draft["result"]=conclusion(draft["findings"])
        self.replace_draft(draft)
        self.sign("second","escalate")
        pin=self.store.detail("second")["referrals"][0]
        args=("second",1,pin["report_hash"],pin["signoff_hash"],"独立复核","逐笔复算两期回单")
        with self.assertRaisesRegex(CaseError,"金额与已签收底稿不符"):
            self.store.resolve_referral(*args,"approve",[rule["id"]])
        self.assertEqual(self.store.detail("second")["status"],"in_review")
        self.assertEqual(self.store.resolve_referral(*args,"return",[rule["id"]]),2)

    def test_approval_and_standalone_bundle_compare_the_review_summary_and_check_scope(self):
        self.workpaper("signed")
        self.sign("signed")
        original=self.workpaper("later",transfer_ref="YL-DIFFERENT")
        for field in ("verdict","human_required","counts","history"):
            draft=deepcopy(original)
            if field=="history":
                del draft["graph"]["payment_history"]
            elif field=="counts":
                draft["result"]["counts"]["risk"]=0
            else:
                draft["result"][field]="pass" if field=="verdict" else False
            self.replace_draft(draft)
            with self.subTest(field=field):
                with self.assertRaises(CaseError) as blocked:
                    self.sign("later")
                self.assertEqual(blocked.exception.status,409)
                package=io.BytesIO()
                export_bundle(self.store,"later",1,package)
                with self.assertRaisesRegex(ValueError,"人工核验要求|缺少出具时的跨案"):
                    verify(package)
        self.replace_draft(original)
        self.sign("later")
