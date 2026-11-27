"""Make a disposable workpaper with a synthetic field for browser navigation."""

from io import BytesIO
from pathlib import Path
import json
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
prefix="/api"
headers={"Idempotency-Key":"walkthrough-test-fixture"}
team=len(sys.argv)>2 and sys.argv[2]=="--team"
if team:
    account=client.post("/api/auth/register",json={"login":"point-walker","name":"影像走查员","password":"synthetic-point-17","workspace":"影像走查企业"})
    assert account.status_code==201, account.json
    workspace=account.json["selected"]
    prefix+="/w/"+workspace
    headers["X-CSRF-Token"]=account.json["csrf"]
filename = "合成　页.jpg" if team else "合成页.jpg"
reply = client.post(prefix+"/cases",headers=headers,data={"title":"合成演练 · 走查","files":(image,filename)})
assert reply.status_code == 202, reply.json
worker.run(store.claim())
case = reply.json["id"]
assert store.report(case,1)["report"]["case_id"] == case
print(json.dumps({"case":case,"workspace":workspace}) if team else case)
