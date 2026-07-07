import win32com.client
import sys

def get_base_price(c, level):
    p = c["price_brutto"].get(level, 0.0)
    if p > 0:
        return p
    p = c["price_brutto"].get(1, 0.0)
    if p > 0:
        return p
    for lvl in sorted(c["price_brutto"].keys()):
        p_val = c["price_brutto"][lvl]
        if p_val > 0:
            return p_val
    return 1.0

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

    # 1. Test repository method
    sys.path.append(".")
    from app.repositories.product_repository import ProductRepository
    
    # Initialize repository
    repo = ProductRepository(mock_sfera)
    bundle_id = 3902
    components = repo.get_bundle_components(bundle_id)
    
    print(f"Components for bundle ID={bundle_id}:")
    for comp in components:
        print(f"  Symbol: {comp['symbol']} (ID: {comp['id']}), Qty: {comp['quantity']}, "
              f"Price Brutto Level 1: {comp['price_brutto'].get(1)}")
    
    # 2. Test pricing calculation logic
    item_gross_price = 1572.00
    bundle_qty = 1.0
    price_level = 1
    
    total_catalog_price = sum(get_base_price(comp, price_level) * comp["quantity"] for comp in components)
    target_total_gross = round(item_gross_price * bundle_qty, 2)
    
    print(f"\nCalculations (Target Total Gross: {target_total_gross}, Total Catalog Price: {total_catalog_price}):")
    
    sum_assigned_values = 0.0
    for idx, comp in enumerate(components):
        comp_qty = comp["quantity"] * bundle_qty
        
        if idx == len(components) - 1:
            item_gross_value = round(target_total_gross - sum_assigned_values, 2)
        else:
            share = (get_base_price(comp, price_level) * comp["quantity"]) / total_catalog_price
            item_gross_value = round(share * target_total_gross, 2)
            sum_assigned_values += item_gross_value
        
        comp_unit_price = round(item_gross_value / comp_qty, 4) if comp_qty > 0 else 0.0
        print(f"  Component {comp['symbol']}:")
        print(f"    Quantity: {comp_qty}")
        print(f"    Calculated Gross Value: {item_gross_value:.2f}")
        print(f"    Unit Price: {comp_unit_price:.4f}")
        
    conn.Close()
    print("\nVerification completed successfully!")

except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
