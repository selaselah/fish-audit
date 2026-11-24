import json
import zipfile

from config import CaseError
from documents import digest
from field_receipts import field_actions, validate_field_actions
from invoice_approval import validate as validate_invoice_approval
from invoice_proof import FORMAT as INVOICE_SOURCE_FORMAT
from payment_history import payment_matches_with_evidence
from payment_index import checked_visibility
from peer_review import journal_decision, verify_referrals, verify_review
from storage import encode


def journal(store, case_id):
    case = store.detail(case_id,with_actions=True)
    result = {"id": case_id, "title": case["title"], "workspace":case["workspace"], "submitter":case["submitter"],
            "status": case["status"], "created": case["created"],
            "events": case["events"], "revisions": case["revisions"], "decisions": case["decisions"],
            "attestations":case["attestations"], "amendments":case["amendments"]}
    if case["supplement_of"]:
        result["supplement_of"] = case["supplement_of"]
    result["referrals"] = case["referrals"]
    try:
        verify_referrals(result)
    except (ValueError, TypeError, KeyError) as exc:
        raise CaseError("提交复核的签收记录或版本摘要不符。",409) from exc
    return result


def write_invoice_approval(store, report, checksum, signoff, write, folder=""):
    if signoff["decision"]!="approve":
        return
    with store.connect() as db:
        row = db.execute("SELECT invoice_check FROM signoffs WHERE case_id=? AND rev=?",(signoff["case_id"],signoff["rev"])).fetchone()
    raw = row["invoice_check"].encode() if row and row["invoice_check"] is not None else None
    try:
        validate_invoice_approval(report,checksum,signoff,raw)
    except (ValueError,KeyError,TypeError) as exc:
        raise CaseError("签收时的同票检查回执与所据底稿或人工意见不符。",409) from exc
    if raw is not None:
        write(folder+"approval/invoices.json",raw,signoff["invoice_check_hash"])


def write_peer_source(store, report, revision, write, folder=""):
    receipt = report.get("peer_review")
    if not receipt:
        return
    case_id = report["case_id"]
    with store.connect() as db:
        db.execute("BEGIN")
        source, first = store.signed_version(db, case_id, receipt["source_rev"])
        _, second = store.signed_version(db, case_id, revision)
        pin = db.execute("""SELECT report_hash,signoff_hash FROM case_referrals
                         WHERE case_id=? AND rev=? AND resolved_rev=?""", (case_id,first["rev"],revision)).fetchone()
    if not pin or tuple(pin) != (receipt["source_hash"], receipt["referral_hash"]):
        raise CaseError("复核版与提交复核时的存证不符。",409)
    try:
        verify_review(report, source, first, second)
    except (ValueError, TypeError, KeyError) as exc:
        raise CaseError("复核签收、原版底稿或所选依据不符。",409) from exc
    write(folder+"review/source-report.json",source,receipt["source_hash"])
    write(folder+"review/referral.json",encode(first).encode(),receipt["referral_hash"])


def write_field_sources(store, report, revision, write, *, folder="", journal=None, selected=None):
    with store.connect() as db:
        def load_version(rev):
            row = db.execute("SELECT content,hash FROM reports WHERE case_id=? AND rev=?",(report["case_id"],rev)).fetchone()
            if not row or digest(row["content"].encode()) != row["hash"]:
                raise CaseError("核图时的底稿版本或摘要不符。",409)
            if rev != revision:
                write(folder+f"field-checks/r{rev}/report.json",row["content"].encode(),row["hash"])
            return row["hash"],json.loads(row["content"])
        try:
            validate_field_actions(report,revision,field_actions(report,revision,journal,selected),load_version)
            if folder:
                actions = checked_visibility(db,report["case_id"],report["graph"],selected)
                if actions:
                    ledger = {"case_id":report["case_id"],"rev":revision,"actions":{a["fact"]:a for a in actions}}
                    write(folder+"field-checks/reference-visibility.json",encode(ledger).encode())
        except (TypeError, ValueError, KeyError) as exc:
            raise CaseError("核图记录与字段、人工日志或原版底稿不符。",409) from exc


def write_returned_source(store, report, write):
    supplement = report["supplement"]
    prior = supplement["parent"]
    with store.connect() as db:
        content, signoff = store.signed_source(db, report["case_id"], prior, supplement["rev"])
    write("supplement/report.json", content, supplement["report_hash"])
    write("supplement/signoff.json", encode(signoff).encode(), supplement["signoff_hash"])
    previous = json.loads(content)
    write_peer_source(store, previous, supplement["rev"], write, "supplement/")
    write_field_sources(store,previous,supplement["rev"],write,folder="supplement/")
    graph = previous["graph"]
    if previous["policy"].get("archived_methods"):
        current_methods = report["policy"].get("code_sha256", {}) if report["policy"].get("archived_methods") else {}
        for name, checksum in previous["policy"]["code_sha256"].items():
            if current_methods.get(name) != checksum:
                write("supplement/methods/"+name, store.method_source(checksum), checksum)
    retained = {r["parent_doc"] for r in supplement["retained"]}
    for doc in graph["documents"]:
        if doc["id"] not in retained:
            source = store.files / prior / doc["id"] / ("original" + doc["ext"])
            write("supplement/originals/" + doc["id"] + doc["ext"], source.read_bytes(), doc["sha256"])
    pages = {(p["doc"],p["number"]):p for p in store.pages(prior)}
    for node in graph["nodes"]:
        if node["type"] == "page":
            doc, number = node["id"].split("/p")
            prefix = f"supplement/pages/{doc}/{number}"
            write(prefix+".jpg", (store.files / prior / doc / (number+".jpg")).read_bytes(), node["sha256"])
            write(prefix+".txt", pages[doc,int(number)]["text"].encode(), node.get("text_sha256"))


def export_bundle(store, case_id, revision, stream):
    bundle = store.report(case_id, revision)
    report = bundle["report"]
    with store.connect() as db:
        raw_report = db.execute("SELECT content FROM reports WHERE case_id=? AND rev=?", (case_id, revision)).fetchone()[0].encode()
    if digest(raw_report) != bundle["sha256"]:
        raise CaseError("底稿内容与留存摘要不一致，暂无法导出。", 409)
    files = []
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        def write(path, data, expected=None):
            checksum = digest(data)
            if expected and expected != checksum:
                raise CaseError("证据文件与底稿摘要不一致，暂无法导出。", 409)
            archive.writestr(path, data)
            files.append({"path": path, "bytes": len(data), "sha256": checksum})

        write("report.json", raw_report, bundle["sha256"])
        history = journal(store,case_id)
        write("journal.json", encode(history).encode())
        if any(d["rev"]==revision for d in history["decisions"]):
            write_invoice_approval(store,report,bundle["sha256"],journal_decision(history,revision),write)
        write_peer_source(store, report, revision, write)
        write_field_sources(store,report,revision,write,journal=history)
        if report["policy"].get("archived_methods"):
            for name, checksum in report["policy"]["code_sha256"].items():
                write("methods/" + name, store.method_source(checksum), checksum)
        pages = {f"{row['doc']}/p{row['number']}": row for row in store.pages(case_id)}
        nodes = {node["id"]: node for node in report["graph"]["nodes"]}
        for doc in report["graph"]["documents"]:
            folder = store.files / case_id / doc["id"]
            write(f"originals/{doc['id']}{doc['ext']}", (folder / ("original" + doc["ext"])).read_bytes(), doc["sha256"])
        for source in report["calls"]["pages"]:
            doc, number = source["doc"], source["page"]
            page = pages[f"{doc}/p{number}"]
            write(f"pages/{doc}/{number}.jpg", (store.files / case_id / doc / f"{number}.jpg").read_bytes(), source["page_sha256"])
            write(f"pages/{doc}/{number}.txt", page["text"].encode(), nodes[f"{doc}/p{number}"].get("text_sha256"))
        included = set()
        invoices = []
        full_invoices = report["policy"].get("invoice_sources") == INVOICE_SOURCE_FORMAT
        for match in report["graph"].get("prior_invoices", []):
            if full_invoices or "peer_source_rev" in match or match.get("checked_field"):
                invoices.append(match)
                continue
            label = (match["case_id"], match["rev"], match["doc"], match["page"])
            if label in included:
                continue
            included.add(label)
            historic = store.files / match["case_id"] / match["doc"] / f"{match['page']}.jpg"
            path = f"prior/{match['case_id']}/r{match['rev']}/{match['doc']}/{match['page']}.jpg"
            write(path, historic.read_bytes(), match["page_hash"])
        invoices.extend(bundle.get("invoice_approval",{}).get("screened",[]))
        payments = payment_matches_with_evidence(report["graph"].get("payment_history", {"matches":[]}))
        references = {}
        for match in [*invoices,*payments]:
            key = match["case_id"],match["rev"]
            group = references.setdefault(key,{"report_hash":match["report_hash"],"signoff_hash":None,"facts":set(),"pages":set(),"text_hashes":{}})
            if match.get("source"):
                group["text_hashes"][match["doc"],match["page"]] = match["source"]["text_sha256"]
            if "signoff_hash" in match:
                group["signoff_hash"] = match["signoff_hash"]
            for item in [*match.get("evidence",[match]),*match.get("code_evidence",[])]:
                group["facts"].add(item["fact"])
                group["pages"].add((item["doc"],item["page"]))
        for (prior, rev), group in references.items():
            root = f"prior/{prior}/r{rev}"
            with store.connect() as db:
                content, signoff = store.signed_source(db, case_id, prior, rev)
            write(root + "/report.json", content, group["report_hash"])
            write(root + "/signoff.json", encode(signoff).encode(), group["signoff_hash"])
            previous = json.loads(content)
            write_invoice_approval(store,previous,group["report_hash"],signoff,write,root+"/")
            write_peer_source(store, previous, rev, write, root+"/")
            write_field_sources(store,previous,rev,write,folder=root+"/",selected=group["facts"])
            graph = previous["graph"]
            documents = {d["id"]: d for d in graph["documents"]}
            prior_nodes = {n["id"]: n for n in graph["nodes"]}
            pages = {(p["doc"], p["number"]): p for p in store.pages(prior)}
            cited = group["pages"]
            for doc in sorted({doc for doc, page in cited}):
                meta = documents[doc]
                original = "original" + meta["ext"]
                write(root + "/originals/" + doc + meta["ext"], (store.files / prior / doc / original).read_bytes(), meta["sha256"])
            for doc, page in sorted(cited):
                node = prior_nodes[f"{doc}/p{page}"]
                path = f"{root}/{doc}/{page}"
                if (prior, rev, doc, page) not in included:
                    write(path + ".jpg", (store.files / prior / doc / f"{page}.jpg").read_bytes(), node["sha256"])
                write(path + ".txt", pages[doc, page]["text"].encode(), group["text_hashes"].get((doc,page),node.get("text_sha256")))
        if "supplement" in report:
            write_returned_source(store, report, write)
        manifest = {"case_id": case_id, "revision": revision, "report_sha256": bundle["sha256"],
                    "encoding": "UTF-8", "files": files}
        archive.writestr("manifest.json", encode(manifest))
    stream.seek(0)
