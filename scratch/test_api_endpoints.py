import logging
import sys
from fastapi.testclient import TestClient
from app.main import app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_endpoints():
    client = TestClient(app)
    
    # 1. Check Status Endpoint
    print("\n--- Testing /status endpoint ---")
    response = client.get("/status")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # 2. Check Bulk Stock Endpoint
    print("\n--- Testing /products/stock/bulk endpoint ---")
    headers = {"X-API-Key": "test"} # Let's see if we need API key or what the key is.
    # Let's inspect dependencies.py to see how the key is loaded
    
    from app.config import load_config
    config = load_config()
    api_key = config.security.api_key if hasattr(config, 'security') and hasattr(config.security, 'api_key') else "test"
    print(f"Using API Key: {api_key}")
    
    headers = {"X-API-Key": api_key}
    request_data = {
        "symbols": ["1001058", "1120067942", "NONEXISTENT_SYMBOL"]
    }
    response = client.post("/products/stock/bulk", json=request_data, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")

if __name__ == "__main__":
    test_endpoints()
