Orders Management — wymagane dane wejściowe (JSON)
==================================================

Model pod Nexo Pro: **4 pliki** (łączone po ID towaru).

Wymagane do startu: 1) produkty + 2) sprzedaż.  
Zalecane: 3) ZD do dostawcy + 4) ruch magazynowy (stockout).

Rezerwacje NIE wymagają osobnego pliku — kolumny w produktach
(stan, rezerwacja, dostępne z Nexo: IloscDostepna).

Szczegóły Nexo: [NEXO_EKSPORT.md](NEXO_EKSPORT.md)  
Formuła prognozy: [FORMULA.md](FORMULA.md)


FORMAT
------
Każdy plik to:
  A) lista obiektów:
     [ { "id": "1001", ... }, ... ]

  albo B) obiekt z listą w jednym z kluczy:
     { "items": [ ... ] }
     dozwolone klucze: items / data / records / products / sales / rows


1) PRODUKTY (wymagane)
----------------------
  id, sku, ean, name/nazwa
  dostępne / stan + rezerwacja (Nexo: IloscDostepna)
    — jeśli masz „dostępne”, system użyje tego jako wolny stan;
    — jeśli nie, liczy: max(stan − rezerwacja, 0).

  opcjonalnie: product_type (KT=komplet), magazyn, producent, grupa,
               active, eol, min_qty, moq, order_increment, lead_time_days


2) SPRZEDAŻ (wymagane)
----------------------
  id, date/data, qty/ilosc, net_value/wartosc_netto, cost/koszt

  Komplety: liczone jak w Nexo (komplet = jedna pozycja, bez rozbijania BOM).


3) ZD DO DOSTAWCY (zalecane)
----------------------------
Otwarte pozycje ZD — „w drodze” w formule (inbound_qty).
Nexo kreator ZD (ZK→ZD) już uwzględnia kompletację stanów.

  id, qty_open (PozostalaIlosc), eta, status
  opcjonalnie: document_symbol, supplier, warehouse


4) RUCH MAGAZYNOWY (zalecane)
-----------------------------
Przyjęcia (PZ) i wydania (WZ) — wykrywanie stockout.
„Nie sprzedawało się” często = „nie było na stanie”.

  id, date, qty (+/- lub z move_type: receipt/issue)
  opcjonalnie: document_symbol, warehouse


ALGORYTM (skrót — pełny opis: FORMULA.md)
------------------------------------------
1. Baza popytu z historii sprzedaży (średnia 90 dni, trend 30/90)
2. Współczynniki:
   - dostępność (stockout z ruchów magazynowych → podnosi popyt)
   - spadek popytu (tylko gdy stan jest i NIE było stockout)
   - sezonowość (miesiąc vs średnia)
   - zmienność XYZ (powiększa bufor, nie cały popyt)
3. daily_demand_adj = baza × współczynniki
4. Formuła zamówienia:

   daily_demand_adj * (lead_time_days + buffer_days * volatility_factor)
   - free_stock - inbound_qty

5. Zaokrąglenie MOQ / Order Increment → tryb auto / weryfikacja / skip
6. Excel: kolumna „Szczegóły prognozy” — 10–20 punktów wyjaśnienia per SKU


MAPOWANIE
---------
Nazwy pól ERP mapujesz w: Reguły i dane → Mapowanie


PRZYKŁADY (sample_data/)
------------------------
products.json        — kartoteka: stan, rezerwacje, dostepne
sales.json           — historia pozycji
purchase_orders.json — otwarte ZD
stock_moves.json     — PZ/WZ (zalecane)
