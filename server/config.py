import os
from pathlib import Path

from dotenv import load_dotenv
from performance import PROFILE as PERFORMANCE


SERVER = Path(__file__).resolve().parent
FRONTEND = SERVER.parent / "frontend"
load_dotenv(SERVER / ".env", interpolate=False)
DATA = Path(os.getenv("AUDIT_DATA_DIR", SERVER / "data")).resolve()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini-2025-04-14")
AUDITOR_MODEL = os.getenv("OPENAI_AUDITOR_MODEL", MODEL)
MAX_FILES = 12
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_CASE_BYTES = 48 * 1024 * 1024
MAX_PAGES = 60
FORMATS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".heic", ".heif"}
PROFILE = "cn-procurement-full-settlement/v1"
TRAVEL = "cn-travel-reimbursement/v1"
BANK = "cn-bank-contract-payment/v1"
PROFILES = {PROFILE: "采购与付款", PERFORMANCE: "合同履约与分期", TRAVEL: "差旅报销", BANK: "付款回单核对"}
RULE_VERSION = "2026.11.26.27"
PROMPT_VERSION = "2026.11.26.06"
RECHECK_EVIDENCE = os.getenv("OPENAI_RECHECK_EVIDENCE", "1").strip().lower() in {"1", "true", "yes"}


class CaseError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status
