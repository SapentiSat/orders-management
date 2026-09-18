# Faza A — aktualizacja `/docs` (panel web)

Plik do wdrożenia w następnej fazie implementacji: [`app/templates/docs.html`](../app/templates/docs.html).

---

## Sekcja „Sens” — bilans wizualny

**Zmiana:** zamiast osobnej kafelki „Rezerwacje” → **Wolny stan (dostępne)** już po rezerwacji.

```
Potrzeba − Wolny stan − W drodze = Sugestia → MOQ/OI
```

Tekst pod diagramem:
> Rezerwacja jest w kolumnie „dostępne” z Nexo — nie odejmujemy jej drugi raz.

---

## Sekcja „Jak korzystać” — krok 1

```
Wgraj produkty (stan · rezerwacja · dostępne) i sprzedaż (wymagane).
Zalecane: ZD do dostawcy (w drodze) oraz ruch magazynowy (stockout w historii).
```

---

## Sekcja „Logika” — warstwa 2

Doprecyzować współczynnik **Dostępność**:
> Wymaga pliku ruchów magazynowych (PZ/WZ). Bez niego współczynnik = 1,0.

Warstwa 4 bilans:
> Minus wolny stan (dostępne), minus w drodze (ZD) → MOQ.

---

## Sekcja „Dane” — 4 kafelki

| Plik | Badge | Opis |
|------|-------|------|
| Produkty | wymagane | Kartoteka + dostępne/rezerwacja, MOQ, LT. Opcj. `product_type` (KT=komplet). |
| Sprzedaż | wymagane | FS/PA — tempo, ABC, trend, sezon. |
| ZD do dostawcy | zalecane | Otwarte ZD — w drodze. Nexo kreator ZK→ZD już odejmuje stan. |
| Ruch magazynowy | zalecane | PZ/WZ — stockout. „Nie sprzedawało się” ≠ „brak popytu”. |

Callout:
> **4 pliki z Nexo.** Rezerwacje w produktach. Szczegóły: `docs/NEXO_EKSPORT.md`, formuła: `docs/FORMULA.md`.

---

## Sekcja „Raport”

Dopisać przy Excel:
> Kolumna **Szczegóły prognozy** — rozbudowane wyjaśnienie (10–20 punktów): bilans krok po kroku, stockout, ZD, MOQ, klasa ABC/XYZ.

---

## Nowy przykład F — komplet (KT)

```
Komplet sprzedany jako zestaw — prognoza na poziomie kompletu, nie składników.
Jeśli kupujecie składniki osobno, weryfikacja ręczna.
```

---

## Link do kreatora Nexo

W sekcji Dane lub Logika — krótka wzmianka:
[Kreator zamówień do dostawców (InsERT)](https://www.insert.com.pl/dla_uzytkownikow/e-pomoc_techniczna/13970,subiekt-nexo-%E2%80%93-nowy-kreator-zamowien-do-dostawcow.html) — ZK→ZD z kompletacją stanów; eksportujemy otwarte ZD.
