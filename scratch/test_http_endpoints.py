import json
import urllib.request
import urllib.error
import time

def test_live_api():
    base_url = "http://127.0.0.1:8000"
    api_key = "SECRET_API_KEY_PLACEHOLDER"
    
    # Wait for server to be fully ready
    print("Waiting 3 seconds for the server to be ready...")
    time.sleep(3)
    
    # 1. Test /status
    print("\n--- Requesting GET /status ---")
    try:
        req = urllib.request.Request(f"{base_url}/status")
        with urllib.request.urlopen(req) as response:
            status_code = response.status
            body = response.read().decode('utf-8')
            print(f"Status Code: {status_code}")
            print(f"Response: {body}")
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Error: {e}")

    # 2. Test /products/stock/bulk
    print("\n--- Requesting POST /products/stock/bulk ---")
    payload = {
        "symbols": ["1001058", "1120067942", "NONEXISTENT_SYMBOL"]
    }
    data = json.dumps(payload).encode('utf-8')
    
    req = urllib.request.Request(
        f"{base_url}/products/stock/bulk",
        data=data,
        headers={
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            status_code = response.status
            body = response.read().decode('utf-8')
            print(f"Status Code: {status_code}")
            print(f"Response: {body}")
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_live_api()
