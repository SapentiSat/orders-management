# Orders Management — Schematy

Do prezentacji Jackowi. Diagramy w Mermaid (podgląd w VS Code / GitHub / wielu viewerach Markdown).

---

## 1. Architektura ogólna

```mermaid
flowchart LR
  ERP[ERP / eksport] -->|2 pliki| FTP[(SFTP / FTPS)]
  FTP --> APP[Orders Management]
  APP --> XLSX[Excel 1 tabela]
  APP --> CLOUD[(Google Drive / OneDrive)]
  APP --> AI[Model AI]
  APP --> MAIL[SMTP]
  APP --> UI[Panel WWW]
  XLSX --> CLOUD
  CLOUD --> MAIL
  AI --> MAIL
  AI --> UI
  XLSX --> UI
```

---

## 2. Dwa pliki wejściowe

```mermaid
flowchart TB
  subgraph P1[Plik A — Produkty]
    A1[id, sku, ean, nazwa]
    A2[producent, grupa]
    A3[aktywny, koniec życia]
    A4[stan, rezerwacje, ilość min]
    A5[MOQ, Order Increment, LT dni]
  end

  subgraph P2[Plik B — Sprzedaż]
    B1[id]
    B2[data]
    B3[ilość szt.]
    B4[wartość netto]
    B5[koszt]
  end

  P1 -->|join po id| JOIN[Pandas join + obliczenia]
  P2 --> JOIN
  JOIN --> OUT[Excel + panel + AI]
```

---

## 3. Flow cotygodniowy (szczegół)

```mermaid
sequenceDiagram
  participant Sch as Harmonogram
  participant FTP as SFTP/FTPS
  participant Eng as Silnik (pandas)
  participant X as Excel
  participant C as Chmura
  participant AI as AI
  participant M as Mail
  participant L as Logi

  Sch->>FTP: Pobierz produkty + sprzedaż
  FTP-->>Eng: 2 pliki
  Eng->>Eng: Mapowanie + walidacja
  alt Błąd mapowania / pliku
    Eng->>L: ERROR
    Eng->>M: Alert ops
  else OK
    Eng->>Eng: ABC/XYZ, sugestia, tryby
    Eng->>X: Jedna tabela + format
    X->>C: Upload
    Eng->>AI: Raport gotowy (skrót)
    AI-->>Eng: Podsumowanie + stats tygodnia
    Eng->>M: Mail raportowy + linki
    Eng->>L: INFO / WARN
  end
```

---

## 4. Logika decyzji na wierszu (tryb)

```mermaid
flowchart TD
  START[SKU po join] --> EOL{Aktywny i nie EOL?}
  EOL -->|nie| SKIP[skip]
  EOL -->|tak| DATA{Komplet MOQ / OI / LT?}
  DATA -->|nie| WER[do weryfikacji]
  DATA -->|tak| HIST{Wystarczająca historia / stabilność?}
  HIST -->|nie| WER
  HIST -->|tak| ABC{ABC/XYZ + progi auto?}
  ABC -->|tak np. A/B + X| AUTO[auto-ready]
  ABC -->|nie np. AZ / C| WER
```

---

## 5. Od danych do sugerowanej ilości

```mermaid
flowchart LR
  S[Sprzedaż historia] --> T[Tempo / prognoza na LT+bufor]
  SE[Sezonowość] --> T
  P[Stan − rezerwacje] --> Z[Zapotrzebowanie]
  T --> Z
  M[MOQ + Order Increment] --> Q[Sugerowana ilość]
  Z --> Q
  Q --> R[Wiersz w Excelu + tryb + ABC/XYZ]
```

---

## 6. Ustawienia (mapa ekranów)

```mermaid
mindmap
  root((Ustawienia))
    Harmonogram
      Dzień i godzina
      Uruchom teraz
    FTP
      SFTP/FTPS
      Ścieżki 2 plików
    Chmura
      Google / OneDrive
      Folder + retencja
    Mail
      Odbiorcy raportu
      Odbiorca alertów
    Panel
      Dostęp użytkowników
    Mapowanie
      Kolumny produktów
      Kolumny sprzedaży
    ABC/XYZ
      Progi i metryki
    Algorytm
      Bufor LT sezon
      Reguły trybów
    AI
      Provider model klucz
    Testy
      FTP SMTP Chmura AI
```

---

## 7. Co dostaje odbiorca maila

```mermaid
flowchart TB
  MAIL[Mail cotygodniowy]
  MAIL --> S1[Skrót liczb: auto / weryfikacja / skip / wartość]
  MAIL --> S2[Link do Excela w chmurze]
  MAIL --> S3[Link / wejście do panelu]
  MAIL --> S4[Podsumowanie AI]
  MAIL --> S5[Stats: tydzień vs poprzedni miesiąc]
```
