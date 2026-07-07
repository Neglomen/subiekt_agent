import win32com.client
import sys

class MockSfera:
    def __init__(self, conn):
        self.ado_connection = conn

try:
    # Set up ADODB connection
    conn = win32com.client.Dispatch("ADODB.Connection")
    server = r"SERVER\SQL"
    db = "PHU_PATRYK_SIKORA"
    conn_str = f"Provider=SQLOLEDB;Data Source={server};Initial Catalog={db};Integrated Security=SSPI;"
    conn.Open(conn_str)
    
    mock_sfera = MockSfera(conn)

    sys.path.append(".")
    from app.repositories.product_repository import ProductRepository
    
    repo = ProductRepository(mock_sfera)
    
    # Let's test with a list of symbols:
    # ZEST_BM_CZARNY_WPB is bundle 3902
    test_symbols = ["ZEST_BM_CZARNY_WPB", "SOME_INVALID_SYMBOL"]
    print(f"Querying components for: {test_symbols}...")
    res = repo.get_bulk_components(test_symbols)
    
    import json
    print("Result:")
    print(json.dumps(res, indent=2))
    
    # Assertions
    assert "ZEST_BM_CZARNY_WPB" in res
    assert len(res["ZEST_BM_CZARNY_WPB"]) == 3
    assert "SOME_INVALID_SYMBOL" in res
    assert len(res["SOME_INVALID_SYMBOL"]) == 0
    
    conn.Close()
    print("\nVerification completed successfully!")

except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
