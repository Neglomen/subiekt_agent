# -*- coding: utf-8 -*-
import win32com.client
from app.config import settings

try:
    gt = win32com.client.Dispatch("InsERT.GT")
    gt.Produkt = 1
    gt.Autentykacja = 0
    gt.Serwer = settings.sfera.db_server_name
    gt.Baza = settings.sfera.db_name
    gt.Operator = settings.sfera.sfera_operator
    gt.OperatorHaslo = settings.sfera.sfera_operator_password
    
    subiekt = gt.Uruchom(6)
    
    nowa_fs = subiekt.SuDokumentyManager.DodajFS()
    try:
        print("NumerPelny przed Zapisz:", nowa_fs.NumerPelny)
    except Exception as e:
        print("Blad przy pobieraniu NumerPelny:", e)
    nowa_fs.Zamknij()
    subiekt.Zakoncz()
except Exception as e:
    print("Blad:", e)
