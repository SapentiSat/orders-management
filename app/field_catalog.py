"""System field catalog for ERP column mapping UI."""

from __future__ import annotations

from typing import Any


PRODUCT_FIELDS: list[dict[str, Any]] = [
    {"key": "id", "label": "ID produktu", "required": True, "hint": "Unikalny identyfikator z Nexo (Asortymenty.Id). Łączy kartotekę ze sprzedażą i ZD."},
    {"key": "sku", "label": "SKU / Symbol", "required": True, "hint": "Kod magazynowy (Asortymenty.Symbol)."},
    {"key": "ean", "label": "EAN", "required": True, "hint": "Kod kreskowy (KodyKreskowe). Może być pusty, ale pole musi być zmapowane."},
    {"key": "name", "label": "Nazwa produktu", "required": True, "hint": "Nazwa handlowa (Asortymenty.Nazwa)."},
    {"key": "stock", "label": "Stan magazynowy", "required": False, "hint": "Stan fizyczny / ilość na magazynie. Opcjonalne, jeśli podajesz „dostępne” z Nexo."},
    {"key": "reserved", "label": "Rezerwacja", "required": False, "hint": "Ilość zarezerwowana (StanyMagazynowe.IloscZarezerwowanaIlosciowo). Snapshot — bez osobnego pliku rezerwacji."},
    {"key": "available", "label": "Dostępne", "required": False, "hint": "Wolna ilość (StanyMagazynowe.IloscDostepna). Jeśli podane — używane jako free_stock zamiast stan − rezerwacja."},
    {"key": "inbound_qty", "label": "W drodze (suma)", "required": False, "hint": "Opcjonalnie z agregatu ZD w eksporcie produktów. Alternatywa: osobny plik purchase_orders."},
    {"key": "warehouse", "label": "Magazyn", "required": False, "hint": "Symbol magazynu (Magazyny.Symbol), gdy eksport per magazyn lub filtr."},
    {"key": "producer", "label": "Dostawca / producent", "required": False, "hint": "Cecha, pole własne lub nazwa z kartoteki — do filtrów Dashboard."},
    {"key": "group", "label": "Grupa towarowa", "required": False, "hint": "GrupyAsortymentu.Nazwa"},
    {"key": "active", "label": "Aktywny", "required": False, "hint": "Czy produkt jest aktywny. Domyślnie: tak (nie w koszu)."},
    {"key": "eol", "label": "EOL", "required": False, "hint": "End of Life / wycofanie. Domyślnie: nie."},
    {"key": "min_qty", "label": "Ilość minimalna", "required": False, "hint": "StanMinimalny (StanWMagazynieZakresy) lub pole własne."},
    {"key": "moq", "label": "MOQ", "required": False, "hint": "Minimalna ilość zamówienia u dostawcy — często pole własne (brak natywnego w Nexo)."},
    {"key": "order_increment", "label": "Order Increment", "required": False, "hint": "Krok zamówienia. Domyślnie: 1."},
    {"key": "lead_time_days", "label": "Lead time (dni)", "required": False, "hint": "LiczbaDniDoRealizacjiDostawcy lub DaneAsortymentuDlaPodmiotow.SredniCzasDostawy."},
]

SALES_FIELDS: list[dict[str, Any]] = [
    {"key": "id", "label": "ID produktu", "required": True, "hint": "AsortymentAktualnyId — musi zgadzać się z kartoteką."},
    {"key": "date", "label": "Data sprzedaży", "required": True, "hint": "Data dokumentu sprzedaży (FS/PA…) — okna historii, trend, sezon."},
    {"key": "qty", "label": "Ilość (szt.)", "required": True, "hint": "IloscWJednostceBazowej z PozycjeDokumentu."},
    {"key": "net_value", "label": "Wartość netto (PLN)", "required": True, "hint": "Wartosc netto po rabacie — ABC i KPI."},
    {"key": "cost", "label": "Koszt", "required": True, "hint": "Koszt ewidencyjny / magazynowy pozycji. Marża = netto − koszt."},
]

PURCHASE_ORDER_FIELDS: list[dict[str, Any]] = [
    {"key": "id", "label": "ID produktu", "required": True, "hint": "Asortyment z pozycji ZD (zamówienie do dostawcy)."},
    {"key": "qty", "label": "Ilość zamówiona", "required": False, "hint": "Ilość na dokumencie ZD."},
    {"key": "qty_open", "label": "Ilość otwarta / w drodze", "required": True, "hint": "PozostalaIlosc (IlosciDoRealizacji) lub ilość − zrealizowano."},
    {"key": "eta", "label": "Termin realizacji", "required": False, "hint": "Dokumenty.TerminRealizacji lub termin pozycji."},
    {"key": "status", "label": "Status", "required": False, "hint": "open / closed — tylko otwarte wliczane do inbound_qty."},
    {"key": "document_symbol", "label": "Numer ZD", "required": False, "hint": "Symbol dokumentu, np. ZD 16/MAG/08/2026 — do raportu."},
    {"key": "supplier", "label": "Dostawca", "required": False, "hint": "Nazwa kontrahenta z nagłówka ZD."},
    {"key": "warehouse", "label": "Magazyn", "required": False, "hint": "Magazyn docelowy z pozycji ZD."},
]

# Legacy loaders only — nie ma osobnych plików w UI
STOCK_MOVE_FIELDS: list[dict[str, Any]] = []
RESERVATION_FIELDS: list[dict[str, Any]] = []

FORMULA_VARIABLES: list[dict[str, Any]] = [
    {
        "key": "daily_demand_adj",
        "kind": "variable",
        "hint": "Skorygowany popyt dzienny",
        "label": "Popyt dzienny (po korektach)",
        "description": "Ile sztuk dziennie „widzi” system po uwzględnieniu dostępności, spadku i sezonu. To baza do mnożenia przez dni pokrycia.",
        "when": "Zawsze — to serce formuły. Bez tego nie ma sensownej sugestii.",
        "example": "Baza 2 szt./dzień × dostępność 1,2 × spadek 0,8 × sezon 1,0 = 1,92 szt./dzień.",
        "calc": "baza × availability × decay × season",
    },
    {
        "key": "lead_time_days",
        "kind": "variable",
        "hint": "Czas dostawy",
        "label": "Lead time (dni)",
        "description": "Ile dni czeka się na dostawę od złożenia zamówienia. Im dłużej, tym większe pokrycie trzeba trzymać.",
        "when": "Gdy dostawca ma realny czas realizacji (z kartoteki produktu).",
        "example": "LT = 30 → liczysz zapas na ok. miesiąc + bufor.",
        "calc": "Z pliku produktów; domyślnie 30",
    },
    {
        "key": "buffer_days",
        "kind": "variable",
        "hint": "Bufor bezpieczeństwa",
        "label": "Bufor (dni)",
        "description": "Dodatkowe dni zapasu „na wszelki wypadek” ponad lead time. Ustawiasz w Algorytmie.",
        "when": "Gdy chcesz większy zapas bezpieczeństwa (opóźnienia, weekendy, wahań).",
        "example": "LT 30 + bufor 14 = 44 dni surowego horyzontu (zanim dojdzie zmienność).",
        "calc": "Ustawienie w Reguły → Algorytm",
    },
    {
        "key": "free_stock",
        "kind": "variable",
        "hint": "Wolny stan",
        "label": "Wolny stan (bilans)",
        "description": "Ilość dostępna do sprzedaży — z kolumny „dostępne” (Nexo) albo stan − rezerwacja.",
        "when": "Zawsze — odejmujesz od potrzeby w formule.",
        "example": "Dostępne 35 szt. → free_stock=35. Potrzeba 88 → sugestia przed MOQ = 53.",
        "calc": "available LUB max(stan − rezerwacja, 0)",
    },
    {
        "key": "inbound_qty",
        "kind": "variable",
        "hint": "W drodze",
        "label": "W drodze (PO)",
        "description": "Ilość już zamówiona u dostawcy, jeszcze nie przyjęta. Chroni przed podwójnym zamówieniem.",
        "when": "Gdy masz plik zamówień do dostawcy (PO) albo wiesz, że towar jedzie.",
        "example": "Potrzeba 88, stan 40, w drodze 48 → 88−40−48 = 0 (nic nie zamawiasz).",
        "calc": "Suma otwartych PO",
    },
    {
        "key": "backlog_qty",
        "kind": "variable",
        "hint": "Zaległości",
        "label": "Zaległości / backorder",
        "description": "Zaległe zobowiązania wobec klientów — zwiększa potrzebę zakupu.",
        "when": "Gdy masz zaległe zamówienia klientów, których jeszcze nie zrealizowano.",
        "example": "Bilans wychodzi 10, backlog 8 → potrzebujesz łącznie 18.",
        "calc": "0, jeśli brak źródła zaległości",
    },
    {
        "key": "reserved_horizon",
        "kind": "variable",
        "hint": "Legacy",
        "label": "Rezerwacja w horyzoncie (legacy)",
        "description": "W modelu Nexo rezerwacja jest już uwzględniona w „wolnym stanie” (kolumna dostępne). Ta zmienna pozostaje w formule dla kompatybilności — zawsze 0.",
        "when": "Nie używaj osobno — eksportuj rezerwację w pliku produktów.",
        "example": "Rezerwacja 5 szt. → free_stock już to odejmuje; reserved_horizon=0.",
        "calc": "0 (rezerwacja w free_stock)",
    },
    {
        "key": "min_qty",
        "kind": "variable",
        "hint": "Stan minimalny",
        "label": "Stan minimalny",
        "description": "Próg „nie schodź poniżej”. Jeśli wolny stan jest za niski, doganiamy do minimum.",
        "when": "Dla SKU z ustaloną półką minimalną / reorder point.",
        "example": "Min = 20, wolny stan = 12 → trzeba dogonić co najmniej 8 szt.",
        "calc": "Z kartoteki; domyślnie 0",
    },
    {
        "key": "volatility_factor",
        "kind": "coefficient",
        "hint": "Współczynnik zmienności",
        "label": "Zmienność (XYZ)",
        "description": "Powiększa bufor, gdy sprzedaż skacze (klasa Y/Z). Nie mnoży całego popytu — tylko bufor w formule.",
        "when": "Przy nieregularnym popycie (promocje, sezonowe skoki, B2B „paczkami”).",
        "example": "Bufor 30 dni × 1,25 (klasa Z) = 37,5 dnia efektywnego buforu.",
        "calc": "X≈1,0 · Y≈1,1 · Z≈1,25",
    },
    {
        "key": "availability_factor",
        "kind": "coefficient",
        "hint": "Współczynnik dostępności",
        "label": "Dostępność (stockout)",
        "description": "Podnosi popyt, gdy w historii wygląda na to, że towaru brakowało. Słaba sprzedaż ≠ brak zainteresowania.",
        "when": "Gdy bywały braki na stanie (pomaga plik przyjęć/ruchów).",
        "example": "Baza 1,5/dzień × 1,4 = 2,1/dzień → wyższa sugestia, bo wcześniej „nie było czym sprzedawać”.",
        "calc": "1 + udział_stockout × siła (z ustawień)",
    },
    {
        "key": "demand_decay_factor",
        "kind": "coefficient",
        "hint": "Współczynnik spadku",
        "label": "Spadek popytu",
        "description": "Obniża popyt, gdy sprzedaż spada, a towar leży na półce — rynek stygnie.",
        "when": "Gdy ostatnie tygodnie są wyraźnie słabsze mimo dostępnego stanu.",
        "example": "Ostatnie 30 dni = połowa z 90 dni, próg 0,75 → mnożnik ≈ 0,67 → mniej zamawiasz.",
        "calc": "trend 30/90 vs próg spadku",
    },
    {
        "key": "seasonality_factor",
        "kind": "coefficient",
        "hint": "Współczynnik sezonowości",
        "label": "Sezonowość",
        "description": "Porównuje bieżący miesiąc do typowego miesiąca tego SKU.",
        "when": "Gdy asortyment ma sezon (lato/zima, święta). Wyłączasz checkboxem w Algorytmie.",
        "example": "Sierpień zwykle 1,3× średniej → popyt × 1,3.",
        "calc": "miesiąc bieżący / średnia miesięcy",
    },
]


def field_catalog() -> dict[str, list[dict[str, Any]]]:
    return {
        "products": PRODUCT_FIELDS,
        "sales": SALES_FIELDS,
        "purchase_orders": PURCHASE_ORDER_FIELDS,
    }


def dataset_labels() -> dict[str, str]:
    return {
        "products": "Produkty (wymagane)",
        "sales": "Sprzedaż (wymagane)",
        "purchase_orders": "Zamówienia do dostawcy — ZD (opcjonalne)",
    }
