import os
import sys
from fastapi.testclient import TestClient

# Adjust path to find app module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app
from app.config import settings

client = TestClient(app)

def test_get_pdf():
    # Use the test document number
    doc_number = "FS 12500/MAG/2026"
    print(f"Testing GET /sales-invoices/pdf for {doc_number}...")
    
    # Send request with API key
    headers = {"X-API-Key": os.getenv("AGENT_API_KEY", settings.sfera.agent_api_key)}
    
    response = client.get(f"/sales-invoices/pdf?doc_number={doc_number}", headers=headers)
    
    if response.status_code == 200:
        print("Success! Received 200 OK.")
        # Ensure it's a PDF
        content_type = response.headers.get("content-type")
        print(f"Content-Type: {content_type}")
        
        if content_type == "application/pdf":
            # Save the file to verify its contents
            output_path = os.path.abspath("scratch/downloaded_invoice.pdf")
            with open(output_path, "wb") as f:
                f.write(response.content)
            print(f"PDF saved to: {output_path} (Size: {len(response.content)} bytes)")
        else:
            print(f"Error: Expected application/pdf, got {content_type}")
            sys.exit(1)
    else:
        print(f"Error: Received status code {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)

if __name__ == "__main__":
    test_get_pdf()
