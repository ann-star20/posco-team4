import json
import os
import time
import urllib.request

URL = "http://127.0.0.1:8400/api/v1/tcad/jobs/demo-tcadverify-0001"
TOKEN = os.environ["TCAD_SERVICE_TOKEN"]

while True:
    req = urllib.request.Request(URL, headers={"X-Fab-Token": TOKEN})
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if data["status"] in ("succeeded", "failed", "cancelled"):
        with open("tcad_demo_job_final.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print(json.dumps(data, ensure_ascii=False))
        break
    time.sleep(30)
