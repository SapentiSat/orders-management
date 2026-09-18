# Nexo Connector

Program Windows łączący **Nexo Pro (SQL read-only)** z panelem **Orders Management**.

## Szybki start (demo — bez SQL)

```bat
cd connector
pip install -r requirements.txt
cd ..
python -m connector.server
```

1. Otwórz http://127.0.0.1:8765/setup  
2. Włącz **Tryb demo** → Zapisz  
3. W panelu web → **Integracje → Nexo Connector** → skopiuj token → wklej w /setup  
4. **Pobierz dane z łącznika**

## Produkcja (SQL Nexo)

1. Utwórz konto SQL z uprawnieniem **SELECT** na bazę Nexo  
2. W /setup podaj serwer, bazę, użytkownika (lub Windows Auth)  
3. Magazyny: symbole po przecinku lub puste = wszystkie  
4. Wyklucz typy: domyślnie `US` (usługi)

## Budowa EXE

```bat
connector\build.bat
```

Wynik: `connector\dist\NexoConnector.exe` — dostępny do pobrania z panelu web (`/downloads/nexo-connector`).

## API (lokalne)

| Endpoint | Opis |
|----------|------|
| `GET /setup` | Konfiguracja w przeglądarce |
| `GET /v1/health` | Status |
| `POST /v1/export` | Eksport 4 plików JSON |
| `GET /v1/files/{name}.json` | Pobranie pliku |

Nagłówek: `Authorization: Bearer <token>` (ten sam co w panelu web).

## Pliki eksportu

- `products.json` — kartoteka + stany  
- `sales.json` — sprzedaż FS/PA  
- `purchase_orders.json` — otwarte ZD  
- `stock_moves.json` — PZ/WZ  

Konfiguracja zapisana w: `%ProgramData%\OrdersManagement\connector.json`
