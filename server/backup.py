"""Take a consistent database and evidence snapshot, verify it, or restore it into a new directory."""

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path


MARKER = ".fish-copy-in-progress"


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def database(root, live=False):
    return sqlite3.connect((root / "audit.sqlite3").resolve().as_uri() + ("?mode=ro" if live else "?immutable=1"), uri=True)


def inventory(db):
    for case, doc, ext, sha in db.execute("SELECT case_id,id,ext,sha256 FROM docs ORDER BY case_id,id"):
        if not all(re.fullmatch(r"[A-Za-z0-9_-]+", entry) for entry in (case, doc)) or not re.fullmatch(r"\.[a-z0-9]+", ext):
            raise ValueError("资料路径无效")
        yield Path("cases",case,doc,"original"+ext), sha
    for case, doc, number, sha in db.execute("SELECT case_id,doc,number,sha256 FROM pages ORDER BY case_id,doc,number"):
        if not all(re.fullmatch(r"[A-Za-z0-9_-]+", entry) for entry in (case, doc)) or not isinstance(number,int) or number < 1:
            raise ValueError("原页路径无效")
        yield Path("cases",case,doc,f"{number}.jpg"), sha


@contextmanager
def new_target(source, target):
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("源目录和目标目录须相互独立")
    target.mkdir(mode=0o700)
    try:
        (target/MARKER).touch(mode=0o600)
        yield
        (target/MARKER).unlink()
    except BaseException:
        shutil.rmtree(target)
        raise


def check_inventory(root):
    files = size = 0
    with closing(database(root)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("数据库完整性检查失败")
        for path, expected in inventory(db):
            if checksum(root/path) != expected:
                raise ValueError("备份文件与原件摘要不符："+str(path))
            files += 1
            size += (root/path).stat().st_size
    return files, size


def copy_evidence(db, source, target):
    for path, _ in inventory(db):
        out = target/path
        out.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        shutil.copyfile(source/path, out)
        out.chmod(0o600)


def snapshot(source, target):
    if (source/MARKER).exists():
        raise ValueError("源目录仍在复制中")
    with new_target(source, target):
        with closing(database(source,live=True)) as current, closing(sqlite3.connect(target/"audit.sqlite3")) as frozen:
            current.backup(frozen)
            frozen.execute("PRAGMA journal_mode=DELETE")
            frozen.execute("PRAGMA secure_delete=ON")
            tables = {r[0] for r in frozen.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "sessions" in tables:
                frozen.execute("DELETE FROM sessions")
            if "invitations" in tables:
                frozen.execute("""UPDATE invitations SET cancelled=strftime('%s','now')
                              WHERE cancelled IS NULL AND claimed_by IS NULL""")
            frozen.commit()
            frozen.execute("VACUUM")
            copy_evidence(frozen,source,target)
        (target/"audit.sqlite3").chmod(0o600)
        files, size = check_inventory(target)
        manifest = {"format":1,"created":datetime.now(timezone.utc).isoformat(),"database_sha256":checksum(target/"audit.sqlite3"),
                    "evidence_files":files,"evidence_bytes":size}
        (target/"backup.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return manifest


def verify_snapshot(source):
    if (source/MARKER).exists():
        raise ValueError("复制尚未完成")
    manifest = json.loads((source/"backup.json").read_text())
    if manifest["format"] != 1 or checksum(source/"audit.sqlite3") != manifest["database_sha256"]:
        raise ValueError("备份版本或数据库摘要不符")
    files, size = check_inventory(source)
    if (files,size) != (manifest["evidence_files"],manifest["evidence_bytes"]):
        raise ValueError("原件与页图清单不符")
    return manifest


def restore(source, target):
    manifest = verify_snapshot(source)
    with new_target(source,target):
        shutil.copyfile(source/"audit.sqlite3",target/"audit.sqlite3")
        (target/"audit.sqlite3").chmod(0o600)
        if checksum(target/"audit.sqlite3") != manifest["database_sha256"]:
            raise ValueError("恢复的数据库摘要不符")
        with closing(database(target)) as db:
            copy_evidence(db,source,target)
        check_inventory(target)
    return manifest


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for key in ("snapshot","verify","restore"):
        cmd = commands.add_parser(key)
        cmd.add_argument("source",type=Path)
        if key != "verify":
            cmd.add_argument("target",type=Path)
    args = parser.parse_args()
    try:
        source = args.source.resolve()
        result = verify_snapshot(source) if args.command == "verify" else (
            snapshot if args.command == "snapshot" else restore)(source,args.target.resolve())
        print(f"已校验 {result['evidence_files']} 份原件与页图，共 {result['evidence_bytes']} 字节。")
    except (OSError, sqlite3.Error, ValueError, KeyError) as error:
        parser.exit(1,str(error)+"\n")
