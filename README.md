# Orders Management

**Proprietary commercial software** — not open source. See [`LICENSE`](LICENSE).

Cotygodniowe propozycje zamówień na podstawie sprzedaży, bufora, lead time, MOQ / Order Increment, z własnym ABC/XYZ, Excelem, panelem i licencjonowaniem per klient.

## Co jest w wersji testowej (0.1.0-test)

- Panel WWW (dashboard, ustawienia, licencja)
- Pipeline: JSON produkty + sprzedaż → ABC/XYZ → sugestia ilości → Excel
- Tryby wiersza: `auto-ready` / `do weryfikacji` / `skip`
- Źródło danych: **Nexo Connector** (Windows, SQL → 4 JSON)
- Wysyłka raportu: **SMTP**
- Sample data / upload plików
- System kluczy licencyjnych HMAC (`OM1....`)
- Docker / docker-compose pod VPS
- Logi INFO/WARN/ERROR

**Na później:** cron/harmonogram produkcyjny, dopracowanie łącznika Nexo.

## Szybki start (lokalnie)

```powershell
cd C:\Users\valia\Desktop\Work\Suuhouse\Cursor\Ordersmanagment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Otwórz: http://127.0.0.1:8000 → **Przelicz raport**.

## Docker (serwer / VPS)

```bash
cp .env.example .env
# ustaw SECRET_KEY, LICENSE_SIGNING_SECRET, ADMIN_PASSWORD
docker compose up -d --build
```

Aplikacja: `http://SERWER:8000`  
Dane trwałe: volume `om_data` → `/app/data`.  
**Nexo Connector** działa osobno na Windows (przy bazie Nexo), nie w kontenerze — w panelu podajesz jego URL + token.

## Licencjonowanie (sprzedaż B2B)

| Element | Opis |
|---------|------|
| `LICENSE` | Umowa proprietary (nie OSS) |
| `LICENSE_SIGNING_SECRET` | Sekret **tylko u vendora** + na serwerze klienta (ten sam do weryfikacji) |
| Klucz `OM1.<payload>.<sig>` | Klient, edycja, expiry, max SKU, features |
| Bez klucza | Tryb testowy: max 50 SKU |

Wystawianie klucza (vendor):

```powershell
python scripts/generate_license.py `
  --secret "TWOJ_SEKRET" `
  --customer "Firma ABC" `
  --email "ops@firma.pl" `
  --edition standard `
  --expires 2027-12-31 `
  --max-skus 10000
```

Dev shortcut: `GET /vendor/issue-demo-key` (wyłączone gdy `APP_ENV=production`).

Klient wkleja klucz w panelu **Licencja**.

> Uwaga: to licencjonowanie offline (HMAC). Na produkcję sprzedażową warto dodać portal vendor + opcjonalny online check / revocation — zaplanowane później.

## GitHub (prywatne repo)

Kod jest prywatny. Po utworzeniu pustego private repo:

```powershell
git remote add origin https://github.com/TWOJ_USER/orders-management.git
git push -u origin main
```

## Struktura

```
app/                 # FastAPI + silnik + licencje
sample_data/         # CSV demo
scripts/             # generate_license.py
docs/                # plan / schematy / prezentacja
Dockerfile
docker-compose.yml
LICENSE              # proprietary
```

## Dokumentacja produktowa

- `docs/PLAN.md`
- `docs/SCHEMAT.md`
- `docs/schemat-wizualny.html`
- `docs/prezentacja.html`
