import win32com.client

conn = win32com.client.Dispatch("ADODB.Connection")
server = "SERVER\\SQL"
db = "PHU_PATRYK_SIKORA"
conn_str = f"Provider=SQLOLEDB;Data Source={server};Initial Catalog={db};Integrated Security=SSPI;"

try:
    conn.Open(conn_str)
    print("Connected successfully!")
    
    # Find standard products (tw_Rodzaj != 8)
    rs = win32com.client.Dispatch("ADODB.Recordset")
    rs.Open("SELECT TOP 5 tw_Symbol, tw_Nazwa FROM tw__Towar WHERE tw_Rodzaj != 8", conn)
    standard_symbols = []
    print("Standard Products:")
    while not rs.EOF:
        sym = rs.Fields("tw_Symbol").Value
        name = rs.Fields("tw_Nazwa").Value
        print(f"  Symbol: {sym}, Name: {name}")
        standard_symbols.append(sym)
        rs.MoveNext()
    rs.Close()

    # Find bundle products (tw_Rodzaj = 8)
    rs.Open("SELECT TOP 5 tw_Symbol, tw_Nazwa FROM tw__Towar WHERE tw_Rodzaj = 8", conn)
    bundle_symbols = []
    print("Bundle Products (Komplety):")
    while not rs.EOF:
        sym = rs.Fields("tw_Symbol").Value
        name = rs.Fields("tw_Nazwa").Value
        print(f"  Symbol: {sym}, Name: {name}")
        bundle_symbols.append(sym)
        rs.MoveNext()
    rs.Close()

    all_symbols = standard_symbols + bundle_symbols
    if not all_symbols:
        print("No products found to test.")
        exit()

    symbols_sql = ", ".join(f"'{s}'" for s in all_symbols)
    mag_id = 1

    sql_query = f"""
    WITH ProductInfo AS (
        SELECT 
            tw_Id, 
            tw_Symbol, 
            tw_Rodzaj
        FROM tw__Towar
        WHERE tw_Symbol IN ({symbols_sql})
    ),
    ComponentStocks AS (
        SELECT 
            pi.tw_Symbol AS BundleSymbol,
            pi.tw_Id AS BundleId,
            comp.tw_Symbol AS ComponentSymbol,
            k.kpl_Liczba AS RequiredQty,
            ISNULL((
                SELECT SUM(st_Stan - st_StanRez) 
                FROM tw_Stan 
                WHERE st_TowId = k.kpl_IdSkladnik AND st_MagId = {mag_id}
            ), 0) AS ComponentAvailableStock
        FROM ProductInfo pi
        INNER JOIN tw_Komplet k ON pi.tw_Id = k.kpl_IdKomplet
        INNER JOIN tw__Towar comp ON k.kpl_IdSkladnik = comp.tw_Id
        WHERE pi.tw_Rodzaj = 8
    ),
    BundleCalculatedStock AS (
        SELECT 
            BundleSymbol AS Symbol,
            MIN(FLOOR(ComponentAvailableStock / RequiredQty)) AS CalculatedStock
        FROM ComponentStocks
        GROUP BY BundleSymbol
    ),
    StandardProductStock AS (
        SELECT 
            pi.tw_Symbol AS Symbol,
            ISNULL((
                SELECT SUM(st_Stan - st_StanRez) 
                FROM tw_Stan 
                WHERE st_TowId = pi.tw_Id AND st_MagId = {mag_id}
            ), 0) AS CalculatedStock
        FROM ProductInfo pi
        WHERE pi.tw_Rodzaj != 8
    )
    SELECT Symbol, CalculatedStock
    FROM StandardProductStock
    UNION ALL
    SELECT Symbol, CalculatedStock
    FROM BundleCalculatedStock;
    """

    print("\nRunning the recommended SQL Query...")
    rs.Open(sql_query, conn)
    print("Results:")
    while not rs.EOF:
        sym = rs.Fields("Symbol").Value
        stock = rs.Fields("CalculatedStock").Value
        print(f"  Symbol: {sym}, Calculated Available Stock: {stock}")
        rs.MoveNext()
    rs.Close()

except Exception as e:
    print("Error:", e)
finally:
    if conn.State == 1:
        conn.Close()
