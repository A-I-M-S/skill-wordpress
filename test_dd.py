import os
import time
import requests
import json

DD_API_KEY = "1aa5f7f72f85381d5e077ee8b2ad2fbe"
DD_APP_KEY = "ddapp_lghjtOJeaopJCkIC3c0hYqRK1rA64fCm4F"
WORKFLOW_ID = "e9b2e6fb-0205-4915-b887-4ff28bf033fb"
url = f"https://api.ap1.datadoghq.com/api/v2/workflows/{WORKFLOW_ID}/instances"

headers = {
    "Content-Type": "application/json",
    "DD-API-KEY": DD_API_KEY,
    "DD-APPLICATION-KEY": DD_APP_KEY
}
payload = {
    "meta": {
        "payload": {
            "input": "Reply with {\"test\": \"Hello, this is Datadog!\"}"
        }
    }
}
response = requests.post(url, headers=headers, json=payload)
response.raise_for_status()
instance_id = response.json()["data"]["id"]
print(f"Instance ID: {instance_id}")

while True:
    poll_url = f"https://api.ap1.datadoghq.com/api/v2/workflows/{WORKFLOW_ID}/instances/{instance_id}"
    res = requests.get(poll_url, headers=headers)
    res.raise_for_status()
    poll_data = res.json()
    status = poll_data.get("data", {}).get("attributes", {}).get("instanceStatus", {}).get("detailsKind")
    print(f"Status: {status}")
    if status == "SUCCEEDED":
        print(json.dumps(poll_data, indent=2))
        break
    elif status in ["FAILED", "CANCELED", "ERROR", "TIMEOUT", "ABORTED"]:
        print(f"Failed with status: {status}")
        break
    time.sleep(2)
