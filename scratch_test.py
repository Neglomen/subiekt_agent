import win32com.client
from app.sfera.sfera_instance import SferaInstance
from app.config import settings

sfera = SferaInstance(settings.sfera)
sfera.connect()

try:
    # Znajdź KFZ po numerze
    sql = "SELECT TOP 5 dok_Id, dok_NrPelny, dok_NrPelnyOryg, dok_Typ FROM dok__Dokument WHERE dok_NrPelny LIKE 'KFZ 44%'"
    rs, _ = sfera.ado_connection.Execute(sql)
    print("Istniejące KFZ:")
    while not rs.EOF:
        print(f"  ID={rs.Fields('dok_Id').Value}, NrPelny={rs.Fields('dok_NrPelny').Value}, "
              f"NrPelnyOryg={rs.Fields('dok_NrPelnyOryg').Value}, Typ={rs.Fields('dok_Typ').Value}")
        rs.MoveNext()
    rs.Close()

    print("\n--- Właściwości DodajKFZ ---")
    mgr = sfera.o_subiekt.SuDokumentyManager
    nowa_kfz = mgr.DodajKFZ()
    
    for prop in ['NumerOryginalny', 'NumerOryginalnyKorekty', 'FzId', 'DokumentKorygowanyId', 
                 'KontrahentId', 'NumerKSeF', 'DoNumerKSeF']:
        try:
            val = getattr(nowa_kfz, prop)
            print(f"  {prop} = '{val}'")
        except Exception as e:
            print(f"  {prop} -> BRAK")
    
    nowa_kfz.Zamknij()

except Exception as e:
    print("Blad:", e)
finally:
    sfera.disconnect()
