"""Check the bytes supporting a human field decision and retain its source revision."""

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone

from config import CaseError


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


def check_file(path, expected):
    try:
        flags = os.O_RDONLY | getattr(os,"O_NOFOLLOW",0) | getattr(os,"O_NONBLOCK",0)
        with os.fdopen(os.open(path,flags),"rb") as file:
            before = os.fstat(file.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise CaseError("待核原件或页图不是普通文件。",409)
            checksum = hashlib.file_digest(file,"sha256").hexdigest()
            if checksum != expected or fingerprint(before) != fingerprint(os.fstat(file.fileno())):
                raise CaseError("原件或页图与所选底稿的来源摘要不符，请核对原始资料或备份。",409)
            return fingerprint(before)
    except OSError as error:
        raise CaseError("待核原件或页图缺失或无法读取，请核对原始资料或备份。",409) from error


def check_registry(db, case_id, pages):
    rows = db.execute("""SELECT p.doc,p.number,d.ext,d.sha256,p.sha256 FROM pages p
                      JOIN docs d ON d.case_id=p.case_id AND d.id=p.doc WHERE p.case_id=?""",(case_id,))
    registered = {(r[0],r[1]):tuple(r)[2:] for r in rows}
    if any(registered.get(address) != entry for address,entry in pages.items()):
        raise CaseError("登记的原件或页图与所选底稿版本不一致。",409)


def check_archived_files(db, case_id, folder, observations):
    pages,files = {},{}
    for receipt,ext in observations:
        doc,page = receipt["doc"],receipt["page"]
        pages[doc,page] = (ext,receipt["original_sha256"],receipt["page_sha256"])
        files[folder/doc/("original"+ext)] = receipt["original_sha256"]
        files[folder/doc/(str(page)+".jpg")] = receipt["page_sha256"]
    if pages:
        check_registry(db,case_id,pages)
        for path,expected in files.items():
            check_file(path,expected)


def check_cited_files(db, case_id, folder, graph, citations):
    docs = {d["id"]:d for d in graph["documents"]}
    nodes = {n["id"]:n for n in graph["nodes"]}
    observations = []
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

    @classmethod
    def prepare(cls, db, folder, case_id, revision, selected, address):
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
        docs = {d["id"]:d for d in report["graph"]["documents"]}
        nodes = {node["id"]:node for node in report["graph"]["nodes"]}
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
        result = cls(case_id,revision,row["hash"],facts,pages,files,{})
        check_registry(db,case_id,pages)
        return result

    def read_files(self):
        self.signatures = {path:check_file(path,expected) for path,expected in self.files.items()}
        self.checked_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def guard(self, db):
        row = db.execute("SELECT content,hash FROM reports WHERE case_id=? AND rev=?",(self.case_id,self.revision)).fetchone()
        if not row or row["hash"] != self.report_hash or hashlib.sha256(row["content"].encode()).hexdigest() != self.report_hash:
            raise CaseError("核图期间底稿版本的内容发生变化。",409)
        check_registry(db,self.case_id,self.pages)
        try:
            if any(fingerprint(path.stat(follow_symlinks=False)) != saved for path,saved in self.signatures.items()):
                raise CaseError("提交核图意见时原件或页图已变更，请重新核对。",409)
        except OSError as error:
            raise CaseError("提交核图意见时原件或页图已不可用。",409) from error

    def receipt(self, doc, page, operation):
        _,original,image = self.pages[doc,page]
        return {"format":"field-source-v1","operation":operation,"case_id":self.case_id,"rev":self.revision,"report_hash":self.report_hash,
                "doc":doc,"page":page,"original_sha256":original,"page_sha256":image,"checked_at":self.checked_at}
