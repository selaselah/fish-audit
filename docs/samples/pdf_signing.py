"""Generate matched watermarked PDF contracts with zero, current or prior-revision signatures."""

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import mkdtemp

from asn1crypto import keys, x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko_certvalidator.registry import SimpleCertificateStore

LABELS = {"typeset": "仅有排印签章栏", "current": "测试签名覆盖当前文件", "earlier": "签名后另存了新版本"}


def signed_copy(data, field="SyntheticApproval", *, reason=None):
    """The fictional self-signed test identity and private key are created in memory."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Fish Audit synthetic test only")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=7)).sign(key, hashes.SHA256()))
    der = serialization.Encoding.DER
    signer = signers.SimpleSigner(asn1_x509.Certificate.load(cert.public_bytes(der)),
        keys.PrivateKeyInfo.load(key.private_bytes(der, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())),
        SimpleCertificateStore())
    return signers.sign_pdf(IncrementalPdfFileWriter(BytesIO(data)),
                            signers.PdfSignatureMetadata(field_name=field, reason=reason), signer=signer).getvalue()


def later_copy(signed):
    writer = IncrementalPdfFileWriter(BytesIO(signed))
    writer.set_info(generic.DictionaryObject({generic.pdf_name("/Subject"): generic.pdf_string("Synthetic review copy")}))
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def run(seed, upload):
    from contract_milestones import PROFILE, documents
    from generate import ROOT, WATERMARK, embedded_font, pdf
    from printed_dates import read_back
    from reinspection_register import prepare
    from run import get, submit, wait

    code = sha256(seed.encode()).hexdigest()[:8].upper()
    folder = ROOT / "PDF签署凭证"
    folder.mkdir(parents=True, exist_ok=True)
    font = embedded_font("PdfSignatureFixture")
    records = documents(code, "complete")
    base = Path(mkdtemp(prefix=code + "-", dir=folder))
    print(base, flush=True)
    for title, rows in records.items():
        pdf(base / (title + ".pdf"), title, rows, font=font)
    raw = (base / "采购合同.pdf").read_bytes()
    signed = signed_copy(raw)
    variants = {"typeset": raw, "current": signed, "earlier": later_copy(signed)}
    submitted = []
    for mode, content in variants.items():
        dest = base / mode
        dest.mkdir()
        contract = dest / "采购合同.pdf"
        contract.write_bytes(content)
        paths = [contract, base / "验收报告.pdf", base / "银行付款回单.pdf"]
        originals = {}
        for path in paths:
            page, = prepare(path, 1, save_images=False)
            lines = page["text"].splitlines()
            assert lines[0] == WATERMARK and all(k + "：" + v in lines for k, v in records[path.stem])
            originals[path.name] = (sha256(path.read_bytes()).hexdigest(), page)
        print(mode, originals[contract.name][0], flush=True)
        if upload:
            title = "合成演练 · PDF " + LABELS[mode]
            cid = submit(title, paths, seed + mode + originals[contract.name][0][:16], PROFILE)
            submitted.append((mode, cid, title, originals))
            print(mode, cid, flush=True)
    for mode, cid, title, originals in submitted:
        report = read_back(cid, title, originals, wait(cid))
        found = next(f for f in report["findings"] if f["rule"] == "H01")
        assert found["effect_review"]["pdf_execution"]["state"] == mode and found["status"] == "missing"
        assert all(f["status"] != "ok" for f in report["findings"] if f["rule"] in ("H04", "H05"))
        statuses = [(f["rule"], f["status"]) for f in report["findings"] if f["rule"].startswith("H")]
        print(mode, cid, "R" + str(get("/api/cases/" + cid)["rev"]), statuses, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    run(args.seed, args.run)
