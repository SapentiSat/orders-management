import pyodbc
import json
import os
import logging
import sys

# =============================================================================
# KONFIGURACJA
# =============================================================================
SERVER = r"MKSUUHOUSE01\INSERTNEXO"
DATABASE = "Nexo_SUUHOUSE"
OUTPUT_DIR = r"C:\Users\suuhouse01_admin\Desktop\CLOUD"
OUTPUT_FILENAME = "ZamowieniaDoDostawcy.json"

LOG_FILE = r"C:\Users\suuhouse01_admin\Desktop\CLOUD\LOG\logi_nexo.log"

FULL_OUTPUT_PATH = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)

# Procedura SQL (zwraca już gotowy JSON: {"zamowienia":[...]} )
SQL_PROC = "EXEC dbo.P_ZamowieniaDoDostawcyWdrodze"


# =============================================================================
# LOGOWANIE (TYLKO BŁĘDY)
# =============================================================================
def setup_logger():
    script_name = os.path.basename(sys.argv[0])
    logger = logging.getLogger(script_name)
    logger.setLevel(logging.ERROR)

    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(file_handler)

    return logger


log = setup_logger()


# =============================================================================
# GŁÓWNY KOD
# =============================================================================
def main():
    if not os.path.exists(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR)
        except OSError as e:
            log.error(f"Nie można utworzyć folderu {OUTPUT_DIR}. System zwrócił: {e}")
            return

    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except OSError as e:
            # bez loga i tak nie zapiszemy błędu — wypisz na stderr
            print(f"Nie można utworzyć folderu logów {log_dir}: {e}", file=sys.stderr)

    conn_str = (
        f"DRIVER={{SQL Server}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"Trusted_Connection=yes;"
    )

    try:
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            cursor.execute(SQL_PROC)

            # FOR JSON bywa pocięty na kilka wierszy NVARCHAR — sklejamy
            chunks = []
            for row in cursor.fetchall():
                if row and row[0] is not None:
                    chunks.append(row[0])

            json_text = "".join(chunks).strip()

            if not json_text:
                log.error(
                    "Procedura P_ZamowieniaDoDostawcyWdrodze zwróciła pusty wynik. "
                    "Plik JSON nie został zaktualizowany."
                )
                return

            # walidacja — czy to poprawny JSON
            try:
                data = json.loads(json_text)
            except json.JSONDecodeError as e:
                log.error(f"Wynik procedury nie jest poprawnym JSON: {e}")
                return

            zamowienia = data.get("zamowienia") if isinstance(data, dict) else None
            if isinstance(zamowienia, list) and len(zamowienia) == 0:
                log.error(
                    "Zapytanie zwróciło 0 zamówień (zamowienia=[]). "
                    "Plik JSON nie został zaktualizowany."
                )
                return

            with open(FULL_OUTPUT_PATH, "w", encoding="utf-8") as f:
                # ładny zapis (procedura nie daje indent)
                json.dump(data, f, indent=4, ensure_ascii=False)

    except pyodbc.Error as e:
        log.error(f"Błąd SQL: {e}")
    except Exception as e:
        log.error(f"Błąd krytyczny: {e}")


if __name__ == "__main__":
    main()
