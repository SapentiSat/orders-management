# Formuła prognozy zakupowej (v2)

Dokument dla zespołu zakupów — jak system liczy sugerowaną ilość.  
Wersja zgodna z modelem **4 plików** z Nexo Pro.

---

## 1. Sens w jednym zdaniu

**Ile zamówić = ile potrzeba na czas dostawy + bufor, minus to co już masz dostępne i minus to co już jedzie od dostawcy — z korektą, gdy w historii brakowało towaru.**

---

## 2. Wejścia (4 pliki)

| Źródło | Co daje |
|--------|---------|
| **Produkty** | Wolny stan (`dostępne`), LT, MOQ, min. stan |
| **Sprzedaż** | Tempo sprzedaży, trend, sezon, klasy ABC/XYZ |
| **ZD** | Ilość w drodze (`inbound_qty`) |
| **Ruch magazynowy** | Czy w historii brakowało towaru (stockout) |

Rezerwacja jest **w produktach** (kolumna dostępne już ją uwzględnia).

---

## 3. Warstwa 1 — baza popytu

```
średnia_90d     = suma sprzedaży (90 dni) / 90
trend           = średnia_30d / średnia_90d
daily_demand_base = średnia_90d  (lub średnia z dni „na stanie” — gdy mamy ruchy)
```

**Przykład:** 270 szt. w 90 dni → baza **3 szt./dzień**.

---

## 4. Warstwa 2 — współczynniki

### 4a. Dostępność (stockout) — z ruchów magazynowych

**Problem:** Gdy towaru nie było, sprzedaż spada — ale to nie znaczy, że klientów nie było.

```
stockout_share = dni_bez_towaru / dni_ze_sprzedażą   (0..1)

availability_factor = min(1 + stockout_share × siła, max)
```

Domyślnie: **siła = 0,8**, **max = 2,0**.

**Przykład:** W 40% dni aktywnej sprzedaży brakowało towaru:
- `availability_factor = 1 + 0,4 × 0,8 = 1,32`
- Baza 3 → skorygowany popyt **3,96 szt./dzień**

**Ważne:** Gdy `stockout_share` jest wysoki, **nie stosujemy spadku popytu** (patrz 4b).

### 4b. Spadek popytu (decay)

**Problem:** Sprzedaż spada, a towar leży — rynek stygnie.

Stosujemy **tylko gdy:**
- wolny stan **teraz** > 0
- trend 30/90 < próg (domyślnie **0,75**)
- stockout_share < **0,25** (inaczej winny brak towaru, nie rynek)

```
demand_decay_factor = trend / próg   (ograniczone do 0,35..1,0)
```

**Przykład:** Ostatnie 30 dni = połowa poprzednich 90, stan pełny, brak stockout:
- decay ≈ **0,67** → mniej zamawiamy.

### 4c. Sezonowość

```
seasonality_factor = sprzedaż_bieżący_miesiąc / średnia_miesięczna
                     (ograniczone do 0,6..1,6)
```

**Przykład:** Sierpień zwykle +25% → mnożnik **1,25**.

### 4d. Zmienność (XYZ)

Nie mnoży całego popytu — tylko **bufor bezpieczeństwa**:

| Klasa XYZ | Mnożnik buforu |
|-----------|----------------|
| X (stabilny) | 1,0 |
| Y | 1,1 |
| Z (nieregularny) | 1,25 |

---

## 5. Popyt dzienny skorygowany

```
daily_demand_adj = daily_demand_base
                   × availability_factor
                   × demand_decay_factor
                   × seasonality_factor
```

**Przykład łączony (stockout + sezon):**
- Baza 3, availability 1,32, decay 1,0, sezon 1,25
- Wynik: **3 × 1,32 × 1,25 = 4,95 szt./dzień**

---

## 6. Warstwa 3 — formuła zamówienia

```
okno_pokrycia = lead_time_days + buffer_days × volatility_factor

potrzeba = daily_demand_adj × okno_pokrycia

surowa_potrzeba = max(
  potrzeba − wolny_stan − w_drodze,
  min_stan − wolny_stan,
  0
)

sugerowana_ilość = zaokrąglenie_do_MOQ_i_OI(surowa_potrzeba)
```

Domyślny bufor: **30 dni** (ustawienie w panelu).

### Przykład A — standard

| Składnik | Wartość |
|----------|---------|
| Popyt skorygowany | 2 szt./dzień |
| LT + bufor | 30 + 14 = 44 dni |
| Potrzeba | 88 |
| Dostępne | 40 |
| W drodze | 0 |
| **Sugestia** | **48** |

### Przykład B — w drodze (ZD)

| Potrzeba | 88 |
| Dostępne | 40 |
| W drodze | 48 |
| **Sugestia** | **0** |

Bez pliku ZD system mógłby zamówić drugi raz.

### Przykład C — stockout w historii

| Baza | 1,5/dzień |
| Dostępność | ×1,4 |
| Popyt skorygowany | 2,1/dzień |
| Efekt | Wyższa sugestia niż „goła średnia” |

---

## 7. Nexo — kreator ZD a nasza prognoza

Nexo (od wersji 57) przy **ZK → ZD** pyta o kompletację — odejmuje stan przed generowaniem ZD.

**W praktyce:**
- Eksportujemy **otwarte ZD** → to już jest „w drodze”.
- Nie importujemy ZK — unikamy podwójnego liczenia.
- Jeśli Nexo wygenerowało ZD na całą brakującą ilość, nasza sugestia = 0.

Źródło: [InsERT — kreator zamówień do dostawców](https://www.insert.com.pl/dla_uzytkownikow/e-pomoc_techniczna/13970,subiekt-nexo-%E2%80%93-nowy-kreator-zamowien-do-dostawcow.html)

---

## 8. Komplety

Strategia v1: **sprzedaż jak w Nexo** (bez rozbijania BOM).

- Komplet sprzedany jako zestaw → prognoza na **poziomie kompletu**.
- Składnik sprzedany osobno → prognoza na **składniku**.
- W Excelu: uwaga dla `product_type = KT`.

Jeśli kupujecie składniki, a sprzedajecie zestawy — rozważcie fazę 2 (rozbijanie `SkladnikiKompletu`).

---

## 9. Tryby wyniku

| Tryb | Znaczenie |
|------|-----------|
| **auto-ready** | Stabilny ruch (A/B + X), komplet danych, sensowna ilość |
| **do weryfikacji** | Warto sprawdzić ręcznie (graniczne wartości, słaby ruch, braki LT/MOQ) |
| **skip** | Brak potrzeby, EOL, nieaktywny, rynek stygnie |

---

## 10. Uwagi w Excelu (docelowo 10–20 punktów)

Dla każdego SKU system generuje **Szczegóły prognozy**, m.in.:

1. Baza popytu (90 dni) i trend 30/90
2. Udział dni stockout (jeśli ruchy mag.)
3. Współczynnik dostępności i uzasadnienie
4. Czy zastosowano / pominięto spadek popytu
5. Sezon — bieżący miesiąc vs średnia
6. Okno pokrycia (LT + bufor × zmienność)
7. Potrzeba brutto (szt.)
8. Odejmowanie: dostępne, w drodze (z numerami ZD)
9. Podbicie do min. stanu (jeśli dotyczy)
10. Zaokrąglenie MOQ / OI
11. Klasa ABC/XYZ i tryb
12. Typ towaru (komplet KT)
13. Ostrzeżenia o brakujących danych

Krótki skrót trafia do kolumny **Uwagi**; pełna lista do **Szczegóły prognozy**.

---

## 11. Parametry w panelu (Reguły → Algorytm)

| Parametr | Domyślnie | Po co |
|----------|-----------|-------|
| `buffer_days` | 30 | Dodatkowe dni zapasu |
| `decay_threshold` | 0,75 | Próg spadku trendu |
| `availability_strength` | 0,8 | Siła korekty stockout |
| `stockout_cap` | 2,0 | Maks. mnożnik dostępności |
| `stockout_gap_days` | 7 | Dni ciszy po wyczerpaniu = stockout |
| `seasonality_enabled` | tak | Włącza sezon |
| Okno historii | 365 dni | Zakres sprzedaży i stockout |

Formułę można edytować w zakładce **Formuła** — domyślna jak w sekcji 6.
