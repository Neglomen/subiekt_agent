import logging
import sys
from app.sfera.sfera_instance import SferaInstance
from app.repositories.product_repository import ProductRepository
from app.config import load_config

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_bulk_stock():
    config = load_config()
    sfera = SferaInstance(config.sfera)
    sfera.connect()
    
    try:
        prod_repo = ProductRepository(sfera)
        
        # 1. Search for some products to get real symbols
        print("\nSearching for some products...")
        products = prod_repo.search()
        symbols = [p["symbol"] for p in products[:5]]
        print(f"Found symbols for testing: {symbols}")
        
        if not symbols:
            print("No symbols found in DB, using a fallback dummy symbol 'TEST'")
            symbols = ["TEST"]
            
        # 2. Get bulk stock
        print(f"\nQuerying bulk stock for symbols: {symbols}...")
        stock_results = prod_repo.get_bulk_stock(symbols)
        print("Bulk stock results:")
        for symbol, stock in stock_results.items():
            print(f"  Symbol: {symbol} -> Available Stock: {stock}")
            
    except Exception as e:
        logger.exception("Error during test:")
    finally:
        sfera.disconnect()

if __name__ == "__main__":
    test_bulk_stock()
