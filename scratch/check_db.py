import logging
import sys
from app.sfera.sfera_instance import SferaInstance
from app.repositories.document_repository import DocumentRepository
from app.config import load_config
import os

logging.basicConfig(level=logging.DEBUG)

def test_find_document():
    # Load config
    config = load_config()
    
    # SferaInstance expects SferaSettings, not AppConfig
    sfera = SferaInstance(config.sfera)
    sfera.connect()
    
    doc_repo = DocumentRepository(sfera)
    
    target_number = "I2553291"
    print(f"Searching for original number: {target_number}")
    
    results = doc_repo.find_by_original_number(target_number)
    print(f"Results: {results}")
    
    sfera.disconnect()

if __name__ == "__main__":
    test_find_document()
