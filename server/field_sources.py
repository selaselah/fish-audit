"""Check the bytes supporting a human field decision and retain its source revision."""

import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config import CaseError
from payment_visibility import review_declarations


def source_row(row):
    item = dict(row)
    receipt = item.pop("source_check",None)
    if receipt is not None:
        try:
            parsed = json.loads(receipt)
            if not isinstance(parsed,dict) or parsed.get("format") != "field-source-v1":
                raise ValueError("invalid field check")
        except (ValueError,TypeError) as exc:
            raise CaseError("人工核图存证已损坏，请核对历史底稿或备份。",409) from exc
        item["source_check"] = parsed
    return item


def fingerprint(info):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


class SourceFileError(CaseError):
    def __init__(self, path, message):
        self.path = path
        super().__init__(message,409)


class PaymentSourceError(CaseError):
    def __init__(self, case_id, revision, facts, error):
        doc = error.path.parent.name
        original = error.path.name.startswith("original.")
        page = None if original else int(error.path.stem)
        candidates = [f for f in facts if f["doc"]==doc and (page is None or f["page"]==page)]
        fact = next((f for f in candidates if f["field"]=="transfer_ref"),next(iter(candidates),None))
        name = fact.get("name",doc) if fact else doc
        self.source = {"case_id":case_id,"rev":revision,"doc":doc,"page":page,"name":name,
                       "fact":fact["id"] if fact else None,"file":"original" if original else "page"}
        location = "原件" if original else f"第 {page} 页"
        super().__init__(f"R{revision}《{name}》{location}核验失败。{error}",409)


def check_file(path, expected):
    try:
        flags = os.O_RDONLY | getattr(os,"O_NOFOLLOW",0) | getattr(os,"O_NONBLOCK",0)
        with os.fdopen(os.open(path,flags),"rb") as file:
            before = os.fstat(file.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise SourceFileError(path,"待核原件或页图不是普通文件。")
            checksum = hashlib.file_digest(file,"sha256").hexdigest()
            if checksum != expected or fingerprint(before) != fingerprint(os.fstat(file.fileno())):
                raise SourceFileError(path,"原件或页图与所选底稿的来源摘要不符，请核对原始资料或备份。")
            return fingerprint(before)
    except OSError as error:
        raise SourceFileError(path,"待核原件或页图缺失或无法读取，请核对原始资料或备份。") from error


def check_registry(db, case_id, pages):
    rows = db.execute("""SELECT p.doc,p.number,d.ext,d.sha256,p.sha256 FROM pages p
                      JOIN docs d ON d.case_id=p.case_id AND d.id=p.doc WHERE p.case_id=?""",(case_id,))
    registered = {(r[0],r[1]):tuple(r)[2:] for r in rows}
    if any(registered.get(address) != entry for address,entry in pages.items()):
        raise CaseError("登记的原件或页图与所选底稿版本不一致。",409)


def check_text_hashes(db, case_id, hashes):
    for (doc,page),expected in hashes.items():
        row = db.execute("SELECT text FROM pages WHERE case_id=? AND doc=? AND number=?", (case_id,doc,page)).fetchone()
        if row is None or hashlib.sha256(row[0].encode()).hexdigest()!=expected:
            raise CaseError(f"所引文件 {doc} 第 {page} 页的文字层与归档摘要不符。",409)


def check_archived_files(db, case_id, folder, observations):
    pages,files = {},{}
    for receipt,ext in observations:
        doc,page = receipt["doc"],receipt["page"]
        source = (ext,receipt["original_sha256"],receipt["page_sha256"])
        if (doc,page) in pages and pages[doc,page]!=source:
            raise CaseError("同一原页的字段存证与所引底稿摘要冲突。",409)
        pages[doc,page] = source
        files[folder/doc/("original"+ext)] = receipt["original_sha256"]
        files[folder/doc/(str(page)+".jpg")] = receipt["page_sha256"]
    if pages:
        check_registry(db,case_id,pages)
        for path,expected in files.items():
            check_file(path,expected)


def check_cited_files(db, case_id, folder, graph, citations, *, field_actions=()):
    docs = {d["id"]:d for d in graph["documents"]}
    nodes = {n["id"]:n for n in graph["nodes"]}
    observations = list(field_actions)
    for item in citations:
        doc,page = item["doc"],item["page"]
        if (docs[doc]["sha256"] != item["source_sha256"] or nodes[doc]["sha256"] != item["source_sha256"]
                or nodes[f"{doc}/p{page}"]["sha256"] != item["page_sha256"]):
            raise CaseError("已签收字段与原版底稿的原件或页图摘要不符。",409)
        observations.append(({"doc":doc,"page":page,"original_sha256":item["source_sha256"],
                              "page_sha256":item["page_sha256"]},docs[doc]["ext"]))
    check_archived_files(db,case_id,folder,observations)


@dataclass
class FieldSources:
    case_id: str
    revision: int
    report_hash: str
    facts: dict
    pages: dict
    files: dict
    signatures: dict
    checked_at: str = ""
    text_hashes: dict = field(default_factory=dict)
    visibility: dict = field(default_factory=dict)

    @classmethod
    def prepare(cls, db, folder, case_id, revision, selected, address, *, visibility=None):
        row = db.execute("""SELECT r.content,r.hash FROM reports r JOIN cases c ON c.id=r.case_id AND c.rev=r.rev
                         WHERE c.id=? AND c.rev=? AND c.status='ready'""",(case_id,revision)).fetchone()
        if not row or hashlib.sha256(row["content"].encode()).hexdigest() != row["hash"]:
            raise CaseError("请核对当前待验收底稿及其版本摘要。",409)
        report = json.loads(row["content"])
        facts = {f["id"]:f for f in report["graph"]["facts"]}
        if selected is not None:
            if (not selected or any(not isinstance(v,str) for v in selected)
                    or len(set(selected)) != len(selected) or set(selected) - facts.keys()):
                raise CaseError("待核记录不属于当前底稿。",400)
            addresses = {(facts[key]["doc"],facts[key]["page"]) for key in selected}
            if address is not None and addresses != {address}:
                raise CaseError("更正记录与所选原页不匹配。",400)
        else:
            addresses = {address}
        sources = cls.from_graph(db,folder,case_id,revision,row["hash"],report["graph"],selected or (),addresses)
        sources.facts = facts
        if visibility is not None:
            try:
                sources.visibility = review_declarations(report["graph"],selected,visibility)
            except ValueError as exc:
                raise CaseError(str(exc),400) from exc
        return sources

    @classmethod
    def from_graph(cls, db, folder, case_id, revision, checksum, graph, selected, addresses=(), *, check_text=False):
        facts = {f["id"]:f for f in graph["facts"]}
        if set(selected)-facts.keys():
            raise CaseError("留存底稿中缺少所引用的原页字段。",409)
        addresses = set(addresses) | {(facts[ref]["doc"],facts[ref]["page"]) for ref in selected}
        docs = {d["id"]:d for d in graph["documents"]}
        nodes = {node["id"]:node for node in graph["nodes"]}
        files,pages = {},{}
        for doc, page in sorted(addresses):
            meta, parent, node = docs.get(doc),nodes.get(doc),nodes.get(f"{doc}/p{page}")
            if not meta or not parent or not node or node["type"] != "page":
                raise CaseError("所选原页不属于此版本底稿。",400)
            if parent["type"] != "document" or meta["sha256"] != parent["sha256"]:
                raise CaseError("底稿中的原件摘要不一致。",409)
            pages[doc,page] = (meta["ext"],meta["sha256"],node["sha256"])
            files[folder/doc/("original"+meta["ext"])] = meta["sha256"]
            files[folder/doc/(str(page)+".jpg")] = node["sha256"]
        for key in selected or ():
            fact = facts[key]
            if pages[fact["doc"],fact["page"]][1:] != (fact["source_sha256"],fact["page_sha256"]):
                raise CaseError("字段的来源摘要与所选原页不符。",409)
        selected_ids = set(selected)
        result = cls(case_id,revision,checksum,{k:v for k,v in facts.items() if k in selected_ids},pages,files,{})
        check_registry(db,case_id,pages)
        if check_text:
            result.text_hashes = {(doc,page):value for doc,page in addresses
                                  if (value:=nodes[f"{doc}/p{page}"].get("text_sha256"))}
            check_text_hashes(db,case_id,result.text_hashes)
        return result

    def read_files(self):
        self.signatures = {path:check_file(path,expected) for path,expected in self.files.items()}
        self.checked_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def guard(self, db):
        row = db.execute("SELECT content,hash FROM reports WHERE case_id=? AND rev=?",(self.case_id,self.revision)).fetchone()
        if not row or row["hash"] != self.report_hash or hashlib.sha256(row["content"].encode()).hexdigest() != self.report_hash:
            raise CaseError("核图期间底稿版本的内容发生变化。",409)
        check_registry(db,self.case_id,self.pages)
        check_text_hashes(db,self.case_id,self.text_hashes)
        for path,saved in self.signatures.items():
            try:
                if fingerprint(path.stat(follow_symlinks=False)) != saved:
                    raise SourceFileError(path,"提交核验意见时原件或页图已变更，请重新核对。")
            except OSError as error:
                raise SourceFileError(path,"提交核验意见时原件或页图已不可用。") from error

    def receipt(self, doc, page, operation):
        _,original,image = self.pages[doc,page]
        return {"format":"field-source-v1","operation":operation,"case_id":self.case_id,"rev":self.revision,"report_hash":self.report_hash,
                "doc":doc,"page":page,"original_sha256":original,"page_sha256":image,"checked_at":self.checked_at}

    def confirmation(self, fact_id):
        fact = self.facts[fact_id]
        receipt = self.receipt(fact["doc"],fact["page"],"confirm")
        if fact_id in self.visibility:
            receipt["reference_visibility"] = self.visibility[fact_id]
        return receipt
