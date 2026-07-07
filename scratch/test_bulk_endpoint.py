import urllib.request
import json

url = "http://127.0.0.1:8001/products/stock/bulk"
headers = {
    "X-API-Key": "SECRET_API_KEY_PLACEHOLDER",
    "Content-Type": "application/json"
}

payload = {
    "symbols": [
        "58EE1.20W",
        "FM 104.4",
        "ZEST_WUV8612+DS8412",
        "ZEST_BIE24300B+HI164",
        "NON_EXISTENT_SYMBOL"
    ]
}

data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(url, data=data, headers=headers, method="POST")

try:
    with urllib.request.urlopen(req) as response:
        res_data = response.read().decode("utf-8")
        print("Response status code:", response.status)
        print("Response JSON:")
        print(json.dumps(json.loads(res_data), indent=2))
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code)
    print("Response text:", e.read().decode("utf-8"))
except Exception as e:
    print("Error:", e)
