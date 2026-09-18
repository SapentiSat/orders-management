-- Nexo Pro 61.x — ruch magazynowy → stock_moves.json
-- Schemat: ModelDanychContainer (SDK: Dokumentacja_bazy_danych_nexo.htm)
--
-- DIAGNOZA (odpal najpierw, jeśli główne zapytanie zwraca 0 wierszy):
--
-- 1) Magazyny
-- SELECT Id, Symbol, Nazwa FROM ModelDanychContainer.Magazyny ORDER BY Symbol;
--
-- 2) Jakie typy dokumentów magazynowych masz w bazie?
-- SELECT d.KlasaDokumentu, d.Symbol, COUNT(*) AS cnt
-- FROM ModelDanychContainer.Dokumenty d
-- WHERE d.KlasaDokumentu IN ('DokumentPZ','DokumentPW','DokumentWZ','DokumentRW','DokumentMMW','DokumentMMP')
--    OR d.Symbol IN ('PZ','PW','WZ','RW','MMW','MMP')
-- GROUP BY d.KlasaDokumentu, d.Symbol
-- ORDER BY cnt DESC;
--
-- 3) MagazynId — pozycja vs nagłówek (tu często jest problem!)
-- SELECT
--   COUNT(*) AS linie,
--   SUM(CASE WHEN pd.MagazynId IS NOT NULL THEN 1 ELSE 0 END) AS pozycja_ma_magazyn,
--   SUM(CASE WHEN pd.MagazynId IS NULL AND d.MagazynId IS NOT NULL THEN 1 ELSE 0 END) AS tylko_naglowek
-- FROM ModelDanychContainer.PozycjeDokumentu pd
-- JOIN ModelDanychContainer.Dokumenty d ON d.Id = pd.Dokument_Id
-- WHERE d.KlasaDokumentu IN ('DokumentPZ','DokumentPW','DokumentWZ','DokumentRW');

DECLARE @MagazynSymbol varchar(32) = 'MAG';   -- twój symbol z tabeli Magazyny
DECLARE @DniWstecz int = 365;

SELECT
  id,
  [date],
  qty,
  move_type,
  document_symbol,
  warehouse,
  doc_type,
  doc_class
FROM (
  -- PRZYJĘCIA (+): PZ, PW
  SELECT
    CAST(pd.AsortymentAktualnyId AS varchar(32)) AS id,
    CAST(d.DataWprowadzenia AS date) AS [date],
    ABS(pd.IloscWJednostceBazowej) AS qty,
    'receipt' AS move_type,
    d.NumerWewnetrzny_PelnaSygnatura AS document_symbol,
    mg.Symbol AS warehouse,
    COALESCE(d.SymbolRzeczywisty, d.Symbol) AS doc_type,
    d.KlasaDokumentu AS doc_class
  FROM ModelDanychContainer.PozycjeDokumentu pd
  INNER JOIN ModelDanychContainer.Dokumenty d ON d.Id = pd.Dokument_Id
  INNER JOIN ModelDanychContainer.Magazyny mg
    ON mg.Id = COALESCE(pd.MagazynId, d.MagazynId)   -- SDK: MagazynId na pozycji LUB nagłówku
  WHERE mg.Symbol = @MagazynSymbol
    AND d.DataWprowadzenia >= DATEADD(day, -@DniWstecz, CAST(GETDATE() AS date))
    AND (
      d.KlasaDokumentu IN ('DokumentPZ', 'DokumentPW')
      OR d.Symbol IN ('PZ', 'PW')
    )
    AND pd.AsortymentAktualnyId IS NOT NULL
    AND pd.IloscWJednostceBazowej <> 0

  UNION ALL

  -- WYDANIA (-): WZ, RW
  SELECT
    CAST(pd.AsortymentAktualnyId AS varchar(32)) AS id,
    CAST(d.DataWprowadzenia AS date) AS [date],
    -ABS(pd.IloscWJednostceBazowej) AS qty,
    'issue' AS move_type,
    d.NumerWewnetrzny_PelnaSygnatura AS document_symbol,
    mg.Symbol AS warehouse,
    COALESCE(d.SymbolRzeczywisty, d.Symbol) AS doc_type,
    d.KlasaDokumentu AS doc_class
  FROM ModelDanychContainer.PozycjeDokumentu pd
  INNER JOIN ModelDanychContainer.Dokumenty d ON d.Id = pd.Dokument_Id
  INNER JOIN ModelDanychContainer.Magazyny mg
    ON mg.Id = COALESCE(pd.MagazynId, d.MagazynId)
  WHERE mg.Symbol = @MagazynSymbol
    AND d.DataWprowadzenia >= DATEADD(day, -@DniWstecz, CAST(GETDATE() AS date))
    AND (
      d.KlasaDokumentu IN ('DokumentWZ', 'DokumentRW')
      OR d.Symbol IN ('WZ', 'RW')
    )
    AND pd.AsortymentAktualnyId IS NOT NULL
    AND pd.IloscWJednostceBazowej <> 0
) moves
ORDER BY [date], document_symbol;

-- Uwagi (SDK):
-- • KlasaDokumentu — kolumna wyliczana, pewniejsza niż sam Symbol (Symbol z Konfiguracje).
-- • MagazynId — na PozycjeDokumentu LUB Dokumenty; pd.MagazynId bywa NULL → stąd 0 wyników.
-- • DataWprowadzenia — data zapisu dokumentu (kolumna na bazowej tabeli Dokumenty).
-- • DataWystawienia NIE istnieje na Dokumenty — jest na tabelach rozszerzeń (np. handlowe).
-- • Przesunięcia MM (DokumentMMW/MMP) — dodaj osobno jeśli potrzebne.
-- • Sprzedaż FS generuje WZ pod spodem — tu celowo tylko dokumenty magazynowe.
