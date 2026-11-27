"""Make one isolated local workpaper with a synthetic field for browser navigation."""

from io import BytesIO
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from jobs import Worker
from main import create_app
from storage import Store


def extract(_):
    output = {"quality":"readable","facts":[{"field":"invoice_id","value":"TEST-17","quote":"TEST-17","region":"top"}]}
    return output, {"model":"fixture","output":output,"check":{"model":"fixture","output":{"checks":[{"index":"1","support":"clear"}]}}}


store = Store(Path(sys.argv[1]))
worker = Worker(store, extract, lambda graph, findings: ([], {"model":"fixture","output":{"followups":[]}}))
client = create_app(store, worker).test_client()
image = BytesIO()
Image.new("RGB",(48,48),"white").save(image,"JPEG")
image.seek(0)
reply = client.post("/api/cases",headers={"Idempotency-Key":"walkthrough-test-fixture"},data={"title":"合成演练 · 走查","files":(image,"合成页.jpg")})
assert reply.status_code == 202, reply.json
worker.run(store.claim())
case = reply.json["id"]
assert store.report(case,1)["report"]["case_id"] == case
print(case)
