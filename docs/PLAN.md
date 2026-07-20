# Orders Management — Plan modułu zamawiania towaru

**Projekt:** Orders Management  
**Cel:** Cotygodniowa propozycja zamówień na podstawie sprzedaży, bufora, czasu realizacji oraz danych master (MOQ, OI, LT), z klasyfikacją ABC/XYZ, raportem Excel, panelem i opcjonalną analizą AI.  
**Odbiorca biznesowy:** Jacek Piotrowski / zespół operacyjny  
**Status dokumentu:** plan + schematy (bez implementacji)

---

## 1. Problem biznesowy

Chcemy wiedzieć **co i ile zamawiać**, bazując na:

- sprzedaży historycznej,
- stanie / rezerwacjach,
- buforze bezpieczeństwa,
- czasie realizacji zamówienia (często 3–6 miesięcy),
- ograniczeniach dostawcy (MOQ, Order Increment),
- sezonowości.

ERP zwykle nie daje tego wygodnie (ABC/XYZ braki / procedury). Moduł ma to liczyć **poza ERP**, na plikach z FTP, i dostarczać wynik ludziom.

---

## 2. Zakres MVP

### Robimy

1. Pobieranie **2 plików** z SFTP/FTPS (produkty + sprzedaż).
2. Mapowanie kolumn (konfiguracja w ustawieniach).
3. Wyliczenie:
   - wolnego stanu,
   - tempa sprzedaży / pokrycia w dniach,
   - **sugerowanej ilości zamówienia** (z MOQ / OI / LT / buforem),
   - **ABC/XYZ** (własne, z ustawień),
   - trybu wiersza: `auto-ready` / `do weryfikacji` / `skip`.
4. Jeden plik Excel — **jedna tabela** (formatowanie, ikony, kolory).
5. Upload Excela do chmury (Google Drive / OneDrive).
6. Mail cotygodniowy (harmonogram: dzień + godzina) z podsumowaniem + linkami.
7. Panel WWW: ostatni raport, historia, ustawienia, logi.
8. AI **po** wygenerowaniu raportu — tylko podsumowanie + statystyki tygodnia (bez ponownego liczenia zamówień).
9. Logi WARN/ERROR (14 dni) + osobny mail alert przy awarii flow.

### Nie w MVP (v1.1+)

- Automatyczne wysyłanie zamówień do dostawcy / ERP.
- Pełny forecasting ML.
- Zaawansowana sezonowość per SKU (na start prosty indeks / flaga grupy).
- Multi-magazyn / multi-firma (chyba że od razu wymagane).

---

## 3. Dane wejściowe — 2 pliki FTP

Mapowanie po **ID towaru**. W Excelu końcowym muszą być też **SKU** i **EAN** (osoba operacyjna na tym pracuje).

### Plik A — Produkty (snapshot)

Jedna linia = jeden towar. Zawartość m.in.:

| Pole | Opis |
|------|------|
| `id` | Klucz łączący ze sprzedażą |
| `sku` | Kod handlowy |
| `ean` | EAN / kod kreskowy |
| `nazwa` | Nazwa towaru |
| `producent` | Producent |
| `grupa` | Grupa / kategoria |
| `aktywny` | Flaga aktywności |
| `koniec_zycia` | Flaga EOL |
| `stan` | Stan magazynowy |
| `rezerwacje` | Ilość zarezerwowana |
| `ilosc_min` / bufor | Minimum / reorder / bufor |
| `moq` | Minimum Order Quantity |
| `order_increment` | Wielokrotność zamówienia |
| `czas_dostawy_dni` | Lead time (LT) |
| opcjonalnie: cena / koszt kartotekowy | Uzupełniająco |

**Wolny stan** = `stan - rezerwacje` (nie ujemny w prezentacji — flaga ostrzeżenia jeśli rezerwacje > stan).

### Plik B — Sprzedaż (historia, np. ~12 miesięcy)

| Pole | Opis |
|------|------|
| `id` | ID towaru |
| `data` | Data sprzedaży |
| `ilosc` | Sztuki |
| `wartosc_netto` | Wartość netto |
| `koszt` | Koszt |

Uwagi:

- Zwroty: ustalić regułę (ujemne ilości wliczane / osobno).
- Agregat dzień×towar vs linie dokumentów — przy agregacie bez `liczba_dok` „liczba transakcji” liczona z dni z ruchem lub trzeba dodać kolumnę.
- Waluta: jedna, spójna.

---

## 4. Logika biznesowa

### 4.1 Sugerowana ilość (rdzeń)

Uproszczony model:

```
okno_pokrycia_dni = lead_time_dni + bufor_dni

zapotrzebowanie =
  prognoza_sprzedazy_na_okno_pokrycia
  × współczynnik_sezonowosci
  − wolny_stan
  (+ ewentualnie dogonienie do ilości_min)

jeśli zapotrzebowanie > 0:
  sugerowana_ilosc = zaokrąglij_w_górę_do_order_increment(
                      max(zapotrzebowanie, moq_jeśli_wymagane)
                    )
else:
  sugerowana_ilosc = 0
```

Przy LT 90–180 dni średnia „z całego roku” bez sezonowości jest ryzykowna — na start: tempo z porównywalnego okresu / prosty indeks miesięczny / flaga sezonowa z grupy.

### 4.2 ABC / XYZ (liczymy sami)

Konfigurowalne progi w ustawieniach (np. A = top X% obrotu, X = niski CV zmienności).

Służy do:

- priorytetyzacji w Excelu,
- przypisania trybu (`auto-ready` vs `do weryfikacji`),
- formatowania warunkowego.

### 4.3 Tryb wiersza (jedna tabela — bez dwóch światów)

| Tryb | Sens |
|------|------|
| `auto-ready` | Stabilna sprzedaż, komplet danych (MOQ/OI/LT), sensowny ABC/XYZ (np. A/B + X) |
| `do weryfikacji` | Ważne lub niepewne (np. AZ, sezon, braki master data, mało historii) |
| `skip` | Nieaktywny, EOL, brak sprzedaży + brak sensu zamówienia, braki krytyczne |

**Nie** robimy dwóch osobnych pipeline’ów „automat vs słabe” — jedna lista + kolumna trybu + filtry.

### 4.4 AI (po raporcie)

Wejście: gotowy wynik (tabela / skrót), nie surowy dump.

Wyjście:

1. Krótkie podsumowanie tygodnia (ryzyka, overstock/understock, braki danych).
2. Osobno: **statystyki sprzedaży** od daty z ustawień → dziś oraz **porównanie z poprzednim miesiącem**.

AI **nie przelicza** sugerowanych ilości w MVP.

---

## 5. Wynik — Excel

- **Jeden plik, jedna tabela.**
- Kolumny m.in.: ID, SKU, EAN, nazwa, producent, grupa, aktywny/EOL, stan, rezerwacje, wolny stan, sprzedaż (okno), transakcje/tempo, pokrycie dni, LT, MOQ, OI, bufor, sugerowana ilość, wartość sugestii, ABC, XYZ, tryb, uwagi.
- Formatowanie warunkowe + ikony (tryb, braki, ryzyko stockout przy długim LT).
- Nazwa pliku: `zamowienia_YYYY-MM-DD.xlsx` (archiwum w chmurze, bez ślepego nadpisywania).

---

## 6. Flow cotygodniowy

```
[Harmonogram] lub [Uruchom teraz]
        │
        ▼
 Pobierz 2 pliki (SFTP/FTPS)
        │
        ▼
 Walidacja + mapowanie kolumn
        │
        ▼
 Pandas: join, agregacje, ABC/XYZ, sugestie, tryby
        │
        ▼
 Excel (openpyxl) — format, ikony
        │
        ▼
 Upload do chmury (Google / OneDrive)
        │
        ▼
 AI: podsumowanie + stats tygodnia (opcjonalnie włączone)
        │
        ▼
 Mail do odbiorców raportu (link Excel + skrót + AI)
        │
        ▼
 Zapis wyniku w panelu + logi
```

Przy błędzie (mapowanie / plik / chmura / SMTP / AI krytyczne): log ERROR + mail do odbiorcy alertów.

---

## 7. Ustawienia systemu

| Sekcja | Zawartość |
|--------|-----------|
| Harmonogram | Dzień tygodnia, godzina; przycisk „Uruchom teraz” |
| SFTP/FTPS | Host, port, login, hasło/klucz, ścieżki i nazwy 2 plików |
| Chmura | Provider (Google Drive / OneDrive), folder, retencja |
| SMTP / mail raportowy | Serwer, nadawca, lista odbiorców cotygodniowych |
| Alerty | Osobny odbiorca przy ERROR w flow |
| Dostęp do panelu | Użytkownicy mający wgląd w UI |
| Mapowanie kolumn | Mapowanie pól plik A / plik B → pola systemu (zapis trwały) |
| ABC/XYZ | Progi, metryka (obrót / marża / ilość), okno czasu |
| Algorytm | Bufor (dni/%), okno sprzedaży, reguły trybów, sezonowość (prosto) |
| AI | Provider, model, klucz API, włącz/wyłącz |
| Testy połączeń | Test SFTP, SMTP, chmura, AI |

Sekrety: nie trzymać w plain text na dysku (env / szyfrowany store).

---

## 8. Panel WWW

- Dashboard: status ostatniego runu, skrót liczb (auto / weryfikacja / skip, wartość sugestii).
- Podgląd / pobranie ostatniego Excela + historia cotygodniowa.
- Tekst AI (jeśli był).
- Statystyki sprzedaży tygodnia vs poprzedni miesiąc.
- Ustawienia (sekcje jak wyżej).
- Logi WARN/ERROR — ostatnie 14 dni.

---

## 9. Stack (propozycja techniczna)

| Element | Propozycja |
|---------|------------|
| Przetwarzanie / Excel | Python, **pandas**, **openpyxl** |
| SFTP / FTPS | paramiko / FTPS TLS |
| Harmonogram | cron / scheduler w usłudze |
| Panel + API | np. FastAPI + proste UI |
| Mail | SMTP |
| Chmura | Google Drive API / Microsoft Graph |
| AI | abstrakcja providera (OpenAI / Anthropic / inny) |

---

## 10. Kryteria sukcesu

1. Co tydzień w ustalonym dniu jest Excel w chmurze + mail z linkiem.
2. Osoba końcowa pracuje na SKU/EAN i widzi sensowną sugerowaną ilość.
3. ABC/XYZ i tryby są zrozumiałe bez wejścia w ERP.
4. Awaria flow = mail alert + log, nie „cicha śmierć”.
5. AI skraca czytanie raportu, nie zastępuje liczb.

---

## 11. Otwarte decyzje (do Jacka)

1. Zwroty w pliku sprzedaży — jak traktować?
2. Sprzedaż = linie dokumentów czy agregat dzień×towar? (ew. kolumna liczby transakcji)
3. Bufor: w dniach czy % sprzedaży? Domyślnie per grupa czy per SKU?
4. Sezonowość v1: flaga grupy vs prosty indeks miesięcy?
5. Google Drive czy OneDrive na start (czy oba)?
6. Czy koszt w sprzedaży to koszt własny sprzedaży (COGS) — do ABC po marży?

---

## 12. Pliki w tym folderze

| Plik | Opis |
|------|------|
| `PLAN.md` | Ten plan |
| `SCHEMAT.md` | Schematy Mermaid (do wklejenia / podglądu w Markdown) |
| `prezentacja.html` | Prosta prezentacja do otwarcia w przeglądarce dla Jacka |

---

*Dokument roboczy — Orders Management. Tylko plan i schematy.*
