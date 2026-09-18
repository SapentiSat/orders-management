/*
================================================================================
Nazwa:        nexo_sql_purchase_orders.sql
Opis:         Procedura — otwarte zamówienia do dostawcy (ZD) z Nexo Pro
              jako JSON (nagłówek + pozycje zagnieżdżone, bez dublowania).
              JM podstawowa, EAN, pozostała ilość (w drodze).
              Filtr: Symbol='ZD', status Do realizacji (StatusDokumentuId=1).
Autor:        Walenty Lupach
Kontakt:      walenty@suuhouse.pl  |  jaskinia@jaskinia.eu

Użycie:
  EXEC dbo.P_ZamowieniaDoDostawcyWdrodze;
================================================================================
*/

CREATE OR ALTER PROCEDURE dbo.P_ZamowieniaDoDostawcyWdrodze
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH dokumenty_zd AS (
        SELECT
            d.Id,
            d.NumerWewnetrzny_PelnaSygnatura,
            d.NumerZewnetrzny,
            d.PodmiotId,
            d.DataWprowadzenia,
            d.DataWydaniaWystawienia,
            d.TerminRealizacji,
            d.Wartosc_NettoPoRabacie,
            d.Dokument_Waluta_Id,
            d.Dokument_FlagaWlasna_Id,
            d.StatusDokumentuId,
            d.Uwagi
        FROM ModelDanychContainer.Dokumenty AS d WITH (NOLOCK)
        WHERE
            d.Symbol = N'ZD'
            AND d.StatusDokumentuId = 1
    ),
    jm_bazowa AS (
        SELECT
            jm_a.AsortymentPodstawowej_Id AS asortyment_id,
            j.Symbol                      AS jm
        FROM ModelDanychContainer.JednostkiMiarAsortymentow AS jm_a WITH (NOLOCK)
        INNER JOIN ModelDanychContainer.JednostkiMiar AS j WITH (NOLOCK)
            ON j.Id = jm_a.JednostkaMiary_Id
        WHERE jm_a.AsortymentPodstawowej_Id IS NOT NULL
    ),
    ean_cte AS (
        SELECT
            jma.AsortymentPodstawowej_Id AS asortyment_id,
            kk.Kod                       AS ean
        FROM ModelDanychContainer.JednostkiMiarAsortymentow AS jma WITH (NOLOCK)
        INNER JOIN ModelDanychContainer.KodyKreskowe AS kk WITH (NOLOCK)
            ON jma.Id = kk.JednostkaMiaryAsortymentuZKodemPodstawowym_Id
        WHERE jma.AsortymentPodstawowej_Id IS NOT NULL
    ),
    pozycje AS (
        SELECT
            pd.Dokument_Id                             AS dokument_id,
            pd.Id                                      AS pozycja_id,
            pd.AsortymentAktualnyId                    AS asortyment_id,
            a.Symbol                                   AS sku,
            a.Nazwa                                    AS asortyment_nazwa,
            e.ean                                      AS ean,
            jm.jm                                      AS jm,
            CAST(pd.Ilosc AS DECIMAL(18, 4))           AS ilosc,
            CAST(pd.IloscWJednostceBazowej AS DECIMAL(18, 4)) AS ilosc_bazowa,
            CAST(
                ISNULL(idr.PozostalaIlosc, pd.IloscWJednostceBazowej)
                AS DECIMAL(18, 4)
            )                                          AS pozostalo,
            CAST(
                pd.IloscWJednostceBazowej
                - ISNULL(idr.PozostalaIlosc, pd.IloscWJednostceBazowej)
                AS DECIMAL(18, 4)
            )                                          AS zrealizowane,
            CAST(pd.Cena_NettoPoRabacie AS DECIMAL(18, 4))  AS cena_netto,
            CAST(pd.Cena_BruttoPoRabacie AS DECIMAL(18, 4)) AS cena_brutto,
            COALESCE(w_cennik.Symbol, w_koszt.Symbol, w_dok.Symbol) AS waluta,
            CAST(pd.Wartosc_NettoPoRabacie AS DECIMAL(18, 4))  AS wartosc_netto,
            CAST(pd.Wartosc_BruttoPoRabacie AS DECIMAL(18, 4)) AS wartosc_brutto,
            CAST(pd.Termin AS date)                    AS termin_pozycji
        FROM dokumenty_zd AS d
        INNER JOIN ModelDanychContainer.PozycjeDokumentu AS pd WITH (NOLOCK)
            ON pd.Dokument_Id = d.Id
        LEFT JOIN ModelDanychContainer.IlosciDoRealizacji AS idr WITH (NOLOCK)
            ON idr.PozycjaDokumentuRealizowanego_Id = pd.Id
        LEFT JOIN ModelDanychContainer.Asortymenty AS a WITH (NOLOCK)
            ON a.Id = pd.AsortymentAktualnyId
        LEFT JOIN ModelDanychContainer.Waluty AS w_dok WITH (NOLOCK)
            ON w_dok.Id = d.Dokument_Waluta_Id
        LEFT JOIN ModelDanychContainer.Waluty AS w_cennik WITH (NOLOCK)
            ON w_cennik.Id = pd.WalutaZCennikaId
        LEFT JOIN ModelDanychContainer.Waluty AS w_koszt WITH (NOLOCK)
            ON w_koszt.Id = pd.WalutaKosztowId
        LEFT JOIN jm_bazowa AS jm
            ON jm.asortyment_id = pd.AsortymentAktualnyId
        LEFT JOIN ean_cte AS e
            ON e.asortyment_id = a.Id
        WHERE
            pd.AsortymentAktualnyId IS NOT NULL
            AND ISNULL(idr.PozostalaIlosc, pd.IloscWJednostceBazowej) > 0
    )
    SELECT
        d.Id                                          AS dokument_id,
        d.NumerWewnetrzny_PelnaSygnatura               AS numer_zd,
        d.NumerZewnetrzny                              AS numer_zewn,
        p.Sygnatura_PelnaSygnatura                     AS symbol_dostawcy,
        p.NazwaSkrocona                                AS dostawca,
        CAST(d.DataWprowadzenia AS date)               AS data_wystawienia,
        CAST(d.DataWydaniaWystawienia AS date)         AS data_potwierdzenia,
        CAST(d.TerminRealizacji AS date)               AS termin_realizacji,
        CAST(d.Wartosc_NettoPoRabacie AS DECIMAL(18, 4)) AS wartosc_netto_dok,
        w_dok.Symbol                                   AS waluta_dok,
        ISNULL(f.Nazwa, N'Brak')                       AS flaga,
        sd.Nazwa                                       AS status_dok,
        d.Uwagi                                        AS uwagi,
        (
            SELECT
                p2.pozycja_id,
                p2.asortyment_id,
                p2.sku,
                p2.asortyment_nazwa,
                p2.ean,
                p2.jm,
                p2.ilosc,
                p2.ilosc_bazowa,
                p2.pozostalo,
                p2.zrealizowane,
                p2.cena_netto,
                p2.cena_brutto,
                p2.waluta,
                p2.wartosc_netto,
                p2.wartosc_brutto,
                p2.termin_pozycji
            FROM pozycje AS p2
            WHERE p2.dokument_id = d.Id
            FOR JSON PATH
        ) AS pozycje
    FROM dokumenty_zd AS d
    LEFT JOIN ModelDanychContainer.Podmioty AS p WITH (NOLOCK)
        ON p.Id = d.PodmiotId
    LEFT JOIN ModelDanychContainer.Waluty AS w_dok WITH (NOLOCK)
        ON w_dok.Id = d.Dokument_Waluta_Id
    LEFT JOIN ModelDanychContainer.FlagiWlasne AS f WITH (NOLOCK)
        ON f.Id = d.Dokument_FlagaWlasna_Id
    LEFT JOIN ModelDanychContainer.StatusyDokumentow AS sd WITH (NOLOCK)
        ON sd.Id = d.StatusDokumentuId
    WHERE EXISTS (
        SELECT 1 FROM pozycje AS px WHERE px.dokument_id = d.Id
    )
    ORDER BY
        d.TerminRealizacji,
        d.NumerWewnetrzny_PelnaSygnatura
    FOR JSON PATH, ROOT('zamowienia');
END;
GO
