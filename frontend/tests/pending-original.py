"""Exercise the reader while a watermarked 24-page document is waiting for extraction."""
import io
import logging
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread, current_thread
from unittest.mock import patch

from reportlab.pdfgen.canvas import Canvas
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "server"), str(ROOT / "docs/samples")]
from generate import WATERMARK, draw_pdf_page, embedded_font
from jobs import Worker
from main import create_app
from storage import Store


class EndPreview(Exception):
    pass


def exercise():
    waiting, finished = Event(), Event()

    def pause_before_extraction(_path):
        waiting.set()
        finished.wait(120)
        raise EndPreview()

    data = io.BytesIO()
    pdf = Canvas(data, pagesize=(595, 842), invariant=True)
    font = embedded_font("ReaderFixture")
    for number in range(1, 25):
        draw_pdf_page(pdf, "交付验收记录", [("档案页码", str(number)), ("设备编号", f"YL-{number:03d}")], font=font)
        pdf.showPage()
    pdf.save()
    data.seek(0)
    fixture_env = {"AUDIT_ACCESS_MODE":"local", "AUDIT_PUBLIC_ORIGIN":"", "OPENAI_API_KEY":"synthetic-unit-test"}
    with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, fixture_env):
        store = Store(Path(temp))
        worker = Worker(store, extractor=pause_before_extraction)
        app = create_app(store, worker)
        with app.test_client() as client:
            response = client.post("/api/cases", data={"title":"合成演练 · 验收附件分页",
                                                       "files":(data, "长篇验收附件.pdf")})
            assert response.status_code == 202, response.json
            cid = response.json["id"]
        assert store.claim() == cid
        with make_server("127.0.0.1", 0, app, threaded=True) as server, ThreadPoolExecutor(1) as pool:
            web = Thread(target=server.serve_forever, daemon=True)
            web.start()

            def run_case():
                worker.thread = current_thread()
                try:
                    worker.run(cid)
                except EndPreview:
                    pass

            job = pool.submit(run_case)
            try:
                if not waiting.wait(30):
                    if job.done():
                        job.result()
                    raise AssertionError("分页检查点超时")
                pages = store.pages(cid)
                assert len(pages) == 24 and all("".join(WATERMARK.split()) in "".join(p["text"].split()) for p in pages)
                subprocess.run(["node", "frontend/tests/workspace.mjs", "--original-reader-case", cid], cwd=ROOT,
                               env={**os.environ, "AUDIT_READER_ORIGIN":f"http://127.0.0.1:{server.server_port}"}, check=True, timeout=90)
            finally:
                finished.set()
                server.shutdown()
                web.join()
            job.result()


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    exercise()
