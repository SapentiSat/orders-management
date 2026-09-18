# Eksport danych z Nexo Pro → Orders Management

SDK: **Nexo 61.1.0.9431** (`NEXO PRO SDK`).  
Schemat bazy: `ModelDanychContainer` — plik `Dokumentacja_bazy_danych_nexo.htm`.

Odczyt SQL wyłącznie do eksportu (konto **SELECT**). Zmiany kartoteki, stanów i dokumentów — przez UI Nexo lub Sfera.

Szczegóły formuły prognozy: [`FORMULA.md`](FORMULA.md).

---

## Co wyciągamy (4 pliki)

| Plik JSON | Priorytet | Źródło Nexo | Rola w prognozie |
|-----------|-----------|-------------|------------------|
| `products.json` | **wymagany** | `Asortymenty` + `StanyMagazynowe` | Kartoteka, wolny stan, LT, MOQ |
| `sales.json` | **wymagany** | `PozycjeDokumentu` (FS, PA…) | Popyt, ABC, trend, sezon |
| `purchase_orders.json` | zalecany | `Dokumenty` (ZD) + `IlosciDoRealizacji` | Towar **w drodze** |
| `stock_moves.json` | zalecany | `Przyjecia`, `Wydania`, PZ/WZ | **Stockout** — brak towaru ≠ brak popytu |

**Nie eksportujemy osobno:**
- rezerwacji (kolumny w `products.json`: `available`, `reserved`)
- zamówień od klienta ZK (Nexo kreator ZD już uwzględnia kompletację — patrz niżej)

---

## Kreator ZD w Nexo (od wersji 57)

InsERT udostępnił [kreator zamówień do dostawców](https://www.insert.com.pl/dla_uzytkownikow/e-pomoc_techniczna/13970,subiekt-nexo-%E2%80%93-nowy-kreator-zamowien-do-dostawcow.html):

- **ZK → ZD** z pytaniem o **kompletację** (wykorzystanie aktualnych stanów magazynowych).
- Dostępny m.in. z modułu Zamówienia → Operacje → *Przetwórz w zamówienie do dostawcy*.

**Dla Orders Management:**
- Eksportujemy **otwarte ZD** (`purchase_orders.json`) — to, co Nexo uznało za brakujące po kompletacji.
- **Nie** importujemy ZK jako osobnego pliku (ryzyko podwójnego liczenia z ZD).
- W Excelu: uwaga, gdy ZD pokrywa całą potrzebę.

---

## Komplety (asortyment typu KT)

W Nexo komplet ma składniki w `SkladnikiKompletu`, ale **w v1 liczymy sprzedaż tak, jak w Nexo**:

- Sprzedany komplet = jedna pozycja w `sales.json`.
- Sprzedany składnik = osobna pozycja.
- W `products.json` opcjonalnie pole `product_type` (`KT`, `TW`, … z `RodzajeAsortymentu.Symbol`) — filtry i uwagi w Excelu.

**Świadomy trade-off:** sprzedaż kompletu **nie** generuje automatycznie popytu na składnikach. Jeśli kupujecie składniki, a sprzedajecie zestawy — w przyszłości tryb rozbijania BOM (faza 2).

---

## 1. Produkty (`products.json`)

### Tabele

| Tabela | Rola |
|--------|------|
| `Asortymenty` | Kartoteka: Id, Symbol, Nazwa, Rodzaj_Id |
| `RodzajeAsortymentu` | Typ towaru: Symbol (`TW`, `KT`, …) |
| `StanyMagazynowe` | Stan per magazyn + rezerwacje + dostępne |
| `KodyKreskowe` | EAN (kod domyślny) |
| `GrupyAsortymentu` | Grupa towarowa |
| `Magazyny` | Symbol magazynu |
| `DaneAsortymentuDlaPodmiotow` | Lead time u dostawcy |

### Mapowanie pól

| Pole JSON | Kolumna Nexo | Uwagi |
|-----------|--------------|-------|
| `id` | `Asortymenty.Id` | Klucz łączenia |
| `sku` | `Asortymenty.Symbol` | |
| `ean` | `KodyKreskowe.Kod` | `Domyslny = 1` |
| `name` | `Asortymenty.Nazwa` | |
| `product_type` | `RodzajeAsortymentu.Symbol` | Opcj.: `KT` = komplet |
| `group` | `GrupyAsortymentu.Nazwa` | |
| `stock` | stan fizyczny | Brak jednej kolumny „stan” — patrz uwaga poniżej |
| `reserved` | `IloscZarezerwowanaIlosciowo` + opcj. `IloscZarezerwowanaDostawowo` | Snapshot |
| `available` | `IloscDostepna` | **Preferowane** — wolny stan |
| `warehouse` | `Magazyny.Symbol` | Gdy eksport per magazyn |
| `lead_time_days` | `LiczbaDniDoRealizacjiDostawcy` | Często pole własne / Excel |
| `moq`, `order_increment` | brak natywnego | Pola własne Nexo |
| `active` | flagi aktywności / kosz | |

**Uwaga o stanie:** W `StanyMagazynowe` Nexo nie ma jednej kolumny „stan fizyczny”. Typowy mapping:
- **dostępne** → `IloscDostepna`
- **rezerwacja** → suma rezerwacji ilościowych i dostawowych
- **stock** (opcjonalnie) → szacunek: dostępne + rezerwacje (+ ewent. `IloscZadysponowana`)

### Logika w aplikacji

```
free_stock = available
          LUB max(stock - reserved, 0)
```

Rezerwacja jest już uwzględniona w `free_stock` — nie odejmujemy jej drugi raz w formule.

### Przykładowe SQL

```sql
SELECT
  a.Id AS id,
  a.Symbol AS sku,
  k.Kod AS ean,
  a.Nazwa AS name,
  ra.Symbol AS product_type,
  g.Nazwa AS [group],
  m.Symbol AS warehouse,
  sm.IloscDostepna AS available,
  sm.IloscZarezerwowanaIlosciowo
    + ISNULL(sm.IloscZarezerwowanaDostawowo, 0) AS reserved,
  sm.IloscDostepna
    + sm.IloscZarezerwowanaIlosciowo
    + ISNULL(sm.IloscZarezerwowanaDostawowo, 0) AS stock
FROM ModelDanychContainer.Asortymenty a
JOIN ModelDanychContainer.StanyMagazynowe sm ON sm.Asortyment_Id = a.Id
JOIN ModelDanychContainer.Magazyny m ON m.Id = sm.Magazyn_Id
LEFT JOIN ModelDanychContainer.KodyKreskowe k
  ON k.Asortyment_Id = a.Id AND k.Domyslny = 1
LEFT JOIN ModelDanychContainer.RodzajeAsortymentu ra ON ra.Id = a.Rodzaj_Id
LEFT JOIN ModelDanychContainer.GrupyAsortymentu g ON g.Id = a.GrupaAsortymentu_Id
WHERE m.Symbol = 'MAG'   -- filtr magazynu głównego
```

---

## 2. Sprzedaż (`sales.json`)

### Tabele

- `PozycjeDokumentu` — ilości, wartości, asortyment
- `Dokumenty` — daty, typ (FS, PA…)
- Enum `TypDokumentu` w SDK — filtr dokumentów sprzedaży

### Mapowanie

| Pole JSON | Kolumna Nexo |
|-----------|--------------|
| `id` | `PozycjeDokumentu.AsortymentAktualnyId` |
| `date` | `Dokumenty.DataWprowadzenia` |
| `qty` | `PozycjeDokumentu.IloscWJednostceBazowej` |
| `net_value` | wartość netto pozycji (PLN) |
| `cost` | koszt ewidencyjny pozycji |

**Filtr:** tylko dokumenty sprzedaży, okno **12–24 miesięcy** wstecz (zgodnie z ustawieniem okna w panelu).

**Komplety:** pozycja kompletu eksportowana jak w dokumencie — bez rozbijania na składniki.

---

## 3. ZD — zamówienia do dostawcy (`purchase_orders.json`)

### Tabele

- `Dokumenty` — nagłówek ZD (`Symbol`, `TerminRealizacji`, kontrahent)
- `PozycjeDokumentu` — linie ZD
- `IlosciDoRealizacji` — `PozostalaIlosc`
- Enum: `TypDokumentu.ZamowienieDoDostawcy`

### Mapowanie

| Pole JSON | Kolumna Nexo |
|-----------|--------------|
| `id` | ID asortymentu z pozycji ZD |
| `qty_open` | `IlosciDoRealizacji.PozostalaIlosc` |
| `qty` | ilość na pozycji |
| `eta` | `Dokumenty.TerminRealizacji` |
| `status` | open / closed / anulowane |
| `document_symbol` | pełna sygnatura dokumentu |
| `supplier` | nazwa dostawcy |
| `warehouse` | magazyn docelowy |

**Filtr:** `PozostalaIlosc > 0`, status ≠ zamknięte / anulowane.

Alternatywa: kolumna `inbound_qty` zagregowana w `products.json` (wtedy plik ZD opcjonalny).

---

## 4. Ruch magazynowy (`stock_moves.json`)

W Nexo **nie ma** tabeli `RuchyMagazynowe`. Ruchy to m.in.:

| Tabela | Rola |
|--------|------|
| `Przyjecia` | Przyjęcia towaru (+) |
| `Wydania` | Wydania towaru (−) |
| `PartiePozycji` | Partie na pozycjach dokumentów |
| `Dokumenty` | PZ, WZ, PW, RW, MM… |

### Mapowanie logiczne (plik JSON)

| Pole JSON | Źródło | Uwagi |
|-----------|--------|-------|
| `id` | `Asortyment_Id` | |
| `date` | data dokumentu / operacji | |
| `qty` | ilość (+ przyjęcie, − wydanie) | Znak lub `move_type` |
| `move_type` | `receipt` / `issue` | Domyślnie `receipt` |
| `document_symbol` | symbol PZ/WZ | Opcjonalnie |
| `warehouse` | symbol magazynu | Opcjonalnie |

### Po co aplikacji

Z ruchów i sprzedaży rekonstruujemy **dni bez towaru** (stockout). Gdy w historii brakowało stanu, sprzedaż była zaniżona — współczynnik **dostępności** podnosi prognozę. Szczegóły: [`FORMULA.md`](FORMULA.md).

### Przykładowe SQL (szkic — union PZ/WZ)

```sql
-- Przyjęcia (PZ) — qty dodatnie
SELECT
  p.Asortyment_Id AS id,
  d.DataWprowadzenia AS [date],
  ABS(p.IloscWJednostceBazowej) AS qty,
  'receipt' AS move_type,
  d.NumerWewnetrzny_PelnaSygnatura AS document_symbol
FROM ModelDanychContainer.PozycjeDokumentu p
JOIN ModelDanychContainer.Dokumenty d ON d.Id = p.Dokument_Id
WHERE d.Symbol IN ('PZ')  -- doprecyzuj KonfiguracjaId / KlasaDokumentu

UNION ALL

-- Wydania (WZ) — qty ujemne lub move_type=issue
SELECT
  p.Asortyment_Id AS id,
  d.DataWprowadzenia AS [date],
  -ABS(p.IloscWJednostceBazowej) AS qty,
  'issue' AS move_type,
  d.NumerWewnetrzny_PelnaSygnatura AS document_symbol
FROM ModelDanychContainer.PozycjeDokumentu p
JOIN ModelDanychContainer.Dokumenty d ON d.Id = p.Dokument_Id
WHERE d.Symbol IN ('WZ')
```

Im pełniejsza historia PZ/WZ, tym trafniejsza detekcja stockout.

---

## Czego świadomie nie pobieramy (v1)

| Dane | Powód |
|------|-------|
| Rezerwacje z datami | Snapshot w `StanyMagazynowe` wystarczy |
| ZK (zamówienia od klienta) | Pokryte przez otwarte ZD po kreatorze Nexo |
| Rozbijanie kompletów (BOM) | Strategia `as_sold` — sprzedaż jak w Nexo |
| MOQ natywnie | Pola własne / Excel master |

---

## Harmonogram eksportu

1. Cotygodniowy job (SQL / Sfera) → **4 pliki JSON** na FTP/SFTP (Integracje w panelu).
2. Upload ręczny: **Reguły i dane → Pliki danych**.
3. Mapowanie kolumn (jednorazowo).
4. **Run** → Excel z sugestiami + szczegółowymi uwagami + opcjonalnie mail.

---

## Bezpieczeństwo

- Konto SQL: tylko **SELECT** na widokach eksportowych.
- Nie modyfikuj danych Nexo przez ten pipeline.
- Hasła FTP/SMTP w `.env`, nie w repo.
