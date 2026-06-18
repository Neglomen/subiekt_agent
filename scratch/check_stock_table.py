import logging
import sys
from app.sfera.sfera_instance import SferaInstance
from app.config import load_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_table():
    config = load_config()
    sfera = SferaInstance(config.sfera)
    sfera.connect()
    
    # Try querying table names matching stan or tw
    queries = [
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE '%stan%' OR TABLE_NAME LIKE '%Stan%'",
        "SELECT TOP 5 * FROM tw__Stan",
        "SELECT TOP 5 * FROM tw_Stan"
    ]
    
    for q in queries:
        print(f"\n--- Running query: {q} ---")
        try:
            rs, _ = sfera.ado_connection.Execute(q)
            # Print columns
            cols = [rs.Fields(i).Name for i in range(rs.Fields.Count)]
            print("Columns:", cols)
            
            # Print first 2 rows
            row_count = 0
            while not rs.EOF and row_count < 2:
                row_data = {col: rs.Fields(col).Value for col in cols}
                print(f"Row {row_count}:", row_data)
                rs.MoveNext()
                row_count += 1
            rs.Close()
        except Exception as e:
            print("Error:", e)
            
    sfera.disconnect()

if __name__ == "__main__":
    check_table()
