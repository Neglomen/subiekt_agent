# -*- coding: utf-8 -*-
import win32com.client
from app.config import settings

try:
    sfera = win32com.client.Dispatch("InsERT.GT")
    sfera.Produkt = 1
    sfera.Serwer = settings.sfera.db_server_name
    sfera.Baza = settings.sfera.db_name
    sfera.Autentykacja = 0
    sfera.Uzytkownik = settings.sfera.sfera_operator
    sfera.UzytkownikHaslo = settings.sfera.sfera_operator_password
    sfera.Operator = settings.sfera.sfera_operator
    sfera.OperatorHaslo = settings.sfera.sfera_operator_password
    
    subiekt = sfera.Uruchom(0, 4)
    print("Sfera uruchomiona")
    
    # We load a document to see how Drukuj behaves or we just create a small one
    nowa_fs = subiekt.SuDokumentyManager.DodajFS()
    nowa_fs.KontrahentId = 1 # Oby jakis istnieje
    pozycja = nowa_fs.Pozycje.Dodaj(1) # Oby jakis towar istnieje
    pozycja.IloscJm = 1
    pozycja.CenaBruttoPrzedRabatem = 10.00
    
    nowa_fs.RejestrujNaUF = True
    nowa_fs.DrukarkaFiskalnaId = 2
    
    print("Zapisywanie...")
    nowa_fs.Zapisz()
    print("Zapisane. Proba odczytu ID:")
    try:
        doc_id = nowa_fs.Id
        print("Id =", doc_id)
    except Exception as ex:
        print("Blad przy pobieraniu Id:", ex)
        
    try:
        print("NumerPelny:", nowa_fs.NumerPelny)
    except Exception as ex:
        print("Blad przy pobieraniu NumerPelny:", ex)
        
    print("Drukuj na UF?")
    # nowa_fs.Drukuj(True) # True means showDialog=False? Or wait, printing standard doc vs fiscal receipt.
    # Actually if RejestrujNaUF is true, Drukuj might print fiscal. But the user said: Zapisz fails to get ID.
    nowa_fs.Zamknij()
except Exception as e:
    print("Blad COM calkowity:", e)
