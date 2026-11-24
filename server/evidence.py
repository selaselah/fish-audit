import json
import zipfile

from config import CaseError
from documents import digest
from storage import encode


def journal(store, case_id):
    case = store.detail(case_id)
    with store.connect() as db:
        attestations = [dict(row) for row in db.execute("""SELECT seq,rev,fact,decision,reviewer,actor,note,time
                         FROM attestations WHERE case_id=? ORDER BY seq""", (case_id,))]
    return {"id": case_id, "title": case["title"], "workspace":case["workspace"], "submitter":case["submitter"],
            "status": case["status"], "created": case["created"],
            "events": case["events"], "revisions": case["revisions"], "decisions": case["decisions"],
            "attestations": attestations, "amendments": store.amendments(case_id)}


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
        write("journal.json", encode(journal(store, case_id)).encode())
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
        for match in report["graph"].get("prior_invoices", []):
            label = (match["case_id"], match["rev"], match["doc"], match["page"])
            if label in included:
                continue
            included.add(label)
            historic = store.files / match["case_id"] / match["doc"] / f"{match['page']}.jpg"
            path = f"prior/{match['case_id']}/r{match['rev']}/{match['doc']}/{match['page']}.jpg"
            write(path, historic.read_bytes(), match["page_hash"])
        for match in report["graph"].get("payment_history", {}).get("matches", []):
            prior, rev = match["case_id"], match["rev"]
            root = f"prior/{prior}/r{rev}"
            with store.connect() as db:
                content, signoff = store.signed_source(db, case_id, prior, rev)
            write(root + "/report.json", content, match["report_hash"])
            write(root + "/signoff.json", encode(signoff).encode(), match["signoff_hash"])
            graph = json.loads(content)["graph"]
            documents = {d["id"]: d for d in graph["documents"]}
            prior_nodes = {n["id"]: n for n in graph["nodes"]}
            pages = {(p["doc"], p["number"]): p for p in store.pages(prior)}
            cited = {(f["doc"], f["page"]) for f in match["evidence"]}
            for doc in sorted({doc for doc, page in cited}):
                meta = documents[doc]
                original = "original" + meta["ext"]
                write(root + "/originals/" + doc + meta["ext"], (store.files / prior / doc / original).read_bytes(), meta["sha256"])
            for doc, page in sorted(cited):
                node = prior_nodes[f"{doc}/p{page}"]
                path = f"{root}/{doc}/{page}"
                if (prior, rev, doc, page) not in included:
                    write(path + ".jpg", (store.files / prior / doc / f"{page}.jpg").read_bytes(), node["sha256"])
                write(path + ".txt", pages[doc, page]["text"].encode(), node.get("text_sha256"))
        manifest = {"case_id": case_id, "revision": revision, "report_sha256": bundle["sha256"],
                    "encoding": "UTF-8", "files": files}
        archive.writestr("manifest.json", encode(manifest))
    stream.seek(0)
