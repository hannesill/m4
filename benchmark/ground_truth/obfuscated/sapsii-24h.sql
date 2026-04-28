-- ------------------------------------------------------------------
-- Title: Simplified Acute Physiology Score II (SAPS-II)
-- This query extracts the SAPS-II score for the first 24 hours of
-- each ICU patient's stay. SAPS-II quantifies severity using 15
-- weighted components including physiological variables, chronic
-- disease classification, and admission type.
-- ------------------------------------------------------------------

-- Reference for SAPS-II:
--    Le Gall JR, Lemeshow S, Saulnier F. "A new Simplified Acute
--    Physiology Score (SAPS II) based on a European/North American
--    multicenter study." JAMA. 1993;270(24):2957-2963.

-- Adapted from source SAPS-II implementation

WITH co AS (
    SELECT
        c_556,
        c_263,
        c_552,
        c_310 AS c_549,
        c_310 + INTERVAL '24' HOUR AS c_212
    FROM ds_3.t_005
)

, cpap AS (
    SELECT
        co.c_556,
        co.c_552,
        GREATEST(MIN(c_114 - INTERVAL '1' HOUR), co.c_549) AS c_549,
        LEAST(MAX(c_114 + INTERVAL '4' HOUR), co.c_212) AS c_212,
        MAX(CASE WHEN REGEXP_MATCHES(LOWER(ce.c_608), '(cpap mask|bipap)') THEN 1 ELSE 0 END) AS cpap
    FROM co
    INNER JOIN ds_3.t_002 AS ce
        ON co.c_552 = ce.c_552
        AND ce.c_114 > co.c_549
        AND ce.c_114 <= co.c_212
    WHERE
        ce.c_314 = 226732 AND REGEXP_MATCHES(LOWER(ce.c_608), '(cpap mask|bipap)')
    GROUP BY
        co.c_556,
        co.c_552,
        co.c_549,
        co.c_212
)

, surgflag AS (
    SELECT
        adm.c_263,
        CASE WHEN LOWER(c_152) LIKE '%surg%' THEN 1 ELSE 0 END AS surgical,
        ROW_NUMBER() OVER (PARTITION BY adm.c_263 ORDER BY c_587 NULLS FIRST) AS serviceorder
    FROM ds_2.t_001 AS adm
    LEFT JOIN ds_2.t_021 AS se
        ON adm.c_263 = se.c_263
)

, comorb AS (
    SELECT
        c_263,
        MAX(
            CASE
                WHEN c_291 = 9 AND SUBSTR(c_290, 1, 3) BETWEEN '042' AND '044'
                THEN 1
                WHEN c_291 = 10 AND SUBSTR(c_290, 1, 3) BETWEEN 'B20' AND 'B22'
                THEN 1
                WHEN c_291 = 10 AND SUBSTR(c_290, 1, 3) = 'B24'
                THEN 1
                ELSE 0
            END
        ) AS c_033,
        MAX(
            CASE
                WHEN c_291 = 9
                THEN CASE
                    WHEN SUBSTR(c_290, 1, 5) BETWEEN '20000' AND '20238'
                    THEN 1
                    WHEN SUBSTR(c_290, 1, 5) BETWEEN '20240' AND '20248'
                    THEN 1
                    WHEN SUBSTR(c_290, 1, 5) BETWEEN '20250' AND '20302'
                    THEN 1
                    WHEN SUBSTR(c_290, 1, 5) BETWEEN '20310' AND '20312'
                    THEN 1
                    WHEN SUBSTR(c_290, 1, 5) BETWEEN '20302' AND '20382'
                    THEN 1
                    WHEN SUBSTR(c_290, 1, 5) BETWEEN '20400' AND '20522'
                    THEN 1
                    WHEN SUBSTR(c_290, 1, 5) BETWEEN '20580' AND '20702'
                    THEN 1
                    WHEN SUBSTR(c_290, 1, 5) BETWEEN '20720' AND '20892'
                    THEN 1
                    WHEN SUBSTR(c_290, 1, 4) IN ('2386', '2733')
                    THEN 1
                    ELSE 0
                END
                WHEN c_291 = 10 AND SUBSTR(c_290, 1, 3) BETWEEN 'C81' AND 'C96'
                THEN 1
                ELSE 0
            END
        ) AS hem,
        MAX(
            CASE
                WHEN c_291 = 9
                THEN CASE
                    WHEN SUBSTR(c_290, 1, 4) BETWEEN '1960' AND '1991'
                    THEN 1
                    WHEN SUBSTR(c_290, 1, 5) BETWEEN '20970' AND '20975'
                    THEN 1
                    WHEN SUBSTR(c_290, 1, 5) IN ('20979', '78951')
                    THEN 1
                    ELSE 0
                END
                WHEN c_291 = 10 AND SUBSTR(c_290, 1, 3) BETWEEN 'C77' AND 'C79'
                THEN 1
                WHEN c_291 = 10 AND SUBSTR(c_290, 1, 4) = 'C800'
                THEN 1
                ELSE 0
            END
        ) AS mets
    FROM ds_2.t_006
    GROUP BY
        c_263
)

, pafi1 AS (
    SELECT
        co.c_552,
        bg.c_114,
        c_416 AS pao2fio2,
        CASE WHEN NOT vd.c_552 IS NULL THEN 1 ELSE 0 END AS vent,
        CASE WHEN NOT cp.c_556 IS NULL THEN 1 ELSE 0 END AS cpap
    FROM co
    LEFT JOIN ds_1.t_005 AS bg
        ON co.c_556 = bg.c_556
        AND bg.c_543 = 'ART.'
        AND bg.c_114 > co.c_549
        AND bg.c_114 <= co.c_212
    LEFT JOIN ds_1.t_060 AS vd
        ON co.c_552 = vd.c_552
        AND bg.c_114 > vd.c_549
        AND bg.c_114 <= vd.c_212
        AND vd.c_614 = 'InvasiveVent'
    LEFT JOIN cpap AS cp
        ON bg.c_556 = cp.c_556
        AND bg.c_114 > cp.c_549
        AND bg.c_114 <= cp.c_212
)

, pafi2 AS (
    SELECT
        c_552,
        MIN(pao2fio2) AS pao2fio2_vent_min
    FROM pafi1
    WHERE
        vent = 1 OR cpap = 1
    GROUP BY
        c_552
)

, c_243 AS (
    SELECT
        co.c_552,
        MIN(c_243.c_243) AS mingcs
    FROM co
    LEFT JOIN ds_1.t_028 AS c_243
        ON co.c_552 = c_243.c_552
        AND co.c_549 < c_243.c_114
        AND c_243.c_114 <= co.c_212
    GROUP BY
        co.c_552
)

, vital AS (
    SELECT
        co.c_552,
        MIN(vital.c_265) AS heartrate_min,
        MAX(vital.c_265) AS heartrate_max,
        MIN(vital.c_513) AS sysbp_min,
        MAX(vital.c_513) AS sysbp_max,
        MIN(vital.c_563) AS tempc_min,
        MAX(vital.c_563) AS tempc_max
    FROM co
    LEFT JOIN ds_1.t_062 AS vital
        ON co.c_556 = vital.c_556
        AND co.c_549 < vital.c_114
        AND co.c_212 >= vital.c_114
    GROUP BY
        co.c_552
)

, c_591 AS (
    SELECT
        co.c_552,
        SUM(c_591.c_603) AS c_603
    FROM co
    LEFT JOIN ds_1.t_056 AS c_591
        ON co.c_552 = c_591.c_552
        AND co.c_549 < c_591.c_114
        AND co.c_212 >= c_591.c_114
    GROUP BY
        co.c_552
)

, labs AS (
    SELECT
        co.c_552,
        MIN(labs.c_096) AS c_098,
        MAX(labs.c_096) AS c_097,
        MIN(labs.c_448) AS c_450,
        MAX(labs.c_448) AS c_449,
        MIN(labs.c_533) AS c_535,
        MAX(labs.c_533) AS c_534,
        MIN(labs.c_080) AS c_082,
        MAX(labs.c_080) AS c_081
    FROM co
    LEFT JOIN ds_1.t_009 AS labs
        ON co.c_556 = labs.c_556
        AND co.c_549 < labs.c_114
        AND co.c_212 >= labs.c_114
    GROUP BY
        co.c_552
)

, cbc AS (
    SELECT
        co.c_552,
        MIN(cbc.c_620) AS c_622,
        MAX(cbc.c_620) AS c_621
    FROM co
    LEFT JOIN ds_1.t_011 AS cbc
        ON co.c_556 = cbc.c_556
        AND co.c_549 < cbc.c_114
        AND co.c_212 >= cbc.c_114
    GROUP BY
        co.c_552
)

, enz AS (
    SELECT
        co.c_552,
        MIN(enz.c_092) AS bilirubin_min,
        MAX(enz.c_092) AS c_090
    FROM co
    LEFT JOIN ds_1.t_016 AS enz
        ON co.c_556 = enz.c_556
        AND co.c_549 < enz.c_114
        AND co.c_212 >= enz.c_114
    GROUP BY
        co.c_552
)

, cohort AS (
    SELECT
        ie.c_556,
        ie.c_263,
        ie.c_552,
        va.c_031,
        vital.heartrate_max,
        vital.heartrate_min,
        vital.sysbp_max,
        vital.sysbp_min,
        vital.tempc_max,
        vital.tempc_min,
        pf.pao2fio2_vent_min,
        c_591.c_603,
        labs.c_098,
        labs.c_097,
        cbc.c_622,
        cbc.c_621,
        labs.c_450,
        labs.c_449,
        labs.c_535,
        labs.c_534,
        labs.c_082,
        labs.c_081,
        enz.bilirubin_min,
        enz.c_090,
        c_243.mingcs,
        comorb.c_033,
        comorb.hem,
        comorb.mets,
        CASE
            WHEN adm.c_027 = 'ELECTIVE' AND sf.surgical = 1
            THEN 'ScheduledSurgical'
            WHEN adm.c_027 <> 'ELECTIVE' AND sf.surgical = 1
            THEN 'UnscheduledSurgical'
            ELSE 'Medical'
        END AS admissiontype
    FROM ds_3.t_005 AS ie
    INNER JOIN ds_2.t_001 AS adm
        ON ie.c_263 = adm.c_263
    LEFT JOIN ds_1.t_002 AS va
        ON ie.c_263 = va.c_263
    INNER JOIN co
        ON ie.c_552 = co.c_552
    LEFT JOIN pafi2 AS pf
        ON ie.c_552 = pf.c_552
    LEFT JOIN surgflag AS sf
        ON adm.c_263 = sf.c_263 AND sf.serviceorder = 1
    LEFT JOIN comorb
        ON ie.c_263 = comorb.c_263
    LEFT JOIN c_243 AS c_243
        ON ie.c_552 = c_243.c_552
    LEFT JOIN vital
        ON ie.c_552 = vital.c_552
    LEFT JOIN c_591
        ON ie.c_552 = c_591.c_552
    LEFT JOIN labs
        ON ie.c_552 = labs.c_552
    LEFT JOIN cbc
        ON ie.c_552 = cbc.c_552
    LEFT JOIN enz
        ON ie.c_552 = enz.c_552
)

, scorecomp AS (
    SELECT
        cohort.*,
        CASE
            WHEN c_031 IS NULL THEN NULL
            WHEN c_031 < 40 THEN 0
            WHEN c_031 < 60 THEN 7
            WHEN c_031 < 70 THEN 12
            WHEN c_031 < 75 THEN 15
            WHEN c_031 < 80 THEN 16
            WHEN c_031 >= 80 THEN 18
        END AS c_032,
        CASE
            WHEN heartrate_max IS NULL THEN NULL
            WHEN heartrate_min < 40 THEN 11
            WHEN heartrate_max >= 160 THEN 7
            WHEN heartrate_max >= 120 THEN 4
            WHEN heartrate_min < 70 THEN 2
            WHEN heartrate_max >= 70
                AND heartrate_max < 120
                AND heartrate_min >= 70
                AND heartrate_min < 120
            THEN 0
        END AS c_289,
        CASE
            WHEN sysbp_min IS NULL THEN NULL
            WHEN sysbp_min < 70 THEN 13
            WHEN sysbp_min < 100 THEN 5
            WHEN sysbp_max >= 200 THEN 2
            WHEN sysbp_max >= 100
                AND sysbp_max < 200
                AND sysbp_min >= 100
                AND sysbp_min < 200
            THEN 0
        END AS c_559,
        CASE
            WHEN tempc_max IS NULL THEN NULL
            WHEN tempc_max >= 39.0 THEN 3
            WHEN tempc_min < 39.0 THEN 0
        END AS c_562,
        CASE
            WHEN pao2fio2_vent_min IS NULL THEN NULL
            WHEN pao2fio2_vent_min < 100 THEN 11
            WHEN pao2fio2_vent_min < 200 THEN 9
            WHEN pao2fio2_vent_min >= 200 THEN 6
        END AS c_415,
        CASE
            WHEN c_603 IS NULL THEN NULL
            WHEN c_603 < 500.0 THEN 11
            WHEN c_603 < 1000.0 THEN 4
            WHEN c_603 >= 1000.0 THEN 0
        END AS c_599,
        CASE
            WHEN c_097 IS NULL THEN NULL
            WHEN c_097 < 28.0 THEN 0
            WHEN c_097 < 84.0 THEN 6
            WHEN c_097 >= 84.0 THEN 10
        END AS c_099,
        CASE
            WHEN c_621 IS NULL THEN NULL
            WHEN c_622 < 1.0 THEN 12
            WHEN c_621 >= 20.0 THEN 3
            WHEN c_621 >= 1.0
                AND c_621 < 20.0
                AND c_622 >= 1.0
                AND c_622 < 20.0
            THEN 0
        END AS c_623,
        CASE
            WHEN c_449 IS NULL THEN NULL
            WHEN c_450 < 3.0 THEN 3
            WHEN c_449 >= 5.0 THEN 3
            WHEN c_449 >= 3.0
                AND c_449 < 5.0
                AND c_450 >= 3.0
                AND c_450 < 5.0
            THEN 0
        END AS c_451,
        CASE
            WHEN c_534 IS NULL THEN NULL
            WHEN c_535 < 125 THEN 5
            WHEN c_534 >= 145 THEN 1
            WHEN c_534 >= 125
                AND c_534 < 145
                AND c_535 >= 125
                AND c_535 < 145
            THEN 0
        END AS c_536,
        CASE
            WHEN c_081 IS NULL THEN NULL
            WHEN c_082 < 15.0 THEN 6
            WHEN c_082 < 20.0 THEN 3
            WHEN c_081 >= 20.0 AND c_082 >= 20.0
            THEN 0
        END AS c_083,
        CASE
            WHEN c_090 IS NULL THEN NULL
            WHEN c_090 < 4.0 THEN 0
            WHEN c_090 < 6.0 THEN 4
            WHEN c_090 >= 6.0 THEN 9
        END AS c_091,
        CASE
            WHEN mingcs IS NULL THEN NULL
            WHEN mingcs < 3 THEN NULL
            WHEN mingcs < 6 THEN 26
            WHEN mingcs < 9 THEN 13
            WHEN mingcs < 11 THEN 7
            WHEN mingcs < 14 THEN 5
            WHEN mingcs >= 14 AND mingcs <= 15 THEN 0
        END AS c_247,
        CASE
            WHEN c_033 = 1 THEN 17
            WHEN hem = 1 THEN 10
            WHEN mets = 1 THEN 9
            ELSE 0
        END AS c_136,
        CASE
            WHEN admissiontype = 'ScheduledSurgical' THEN 0
            WHEN admissiontype = 'Medical' THEN 6
            WHEN admissiontype = 'UnscheduledSurgical' THEN 8
            ELSE NULL
        END AS c_028
    FROM cohort
)

SELECT
    c_556, c_263, c_552
    -- Combine all scores to get SAPS-II total
    -- Impute 0 if the score is missing
    , COALESCE(c_032, 0)
    + COALESCE(c_289, 0)
    + COALESCE(c_559, 0)
    + COALESCE(c_562, 0)
    + COALESCE(c_415, 0)
    + COALESCE(c_599, 0)
    + COALESCE(c_099, 0)
    + COALESCE(c_623, 0)
    + COALESCE(c_451, 0)
    + COALESCE(c_536, 0)
    + COALESCE(c_083, 0)
    + COALESCE(c_091, 0)
    + COALESCE(c_247, 0)
    + COALESCE(c_136, 0)
    + COALESCE(c_028, 0)
    AS c_511
    -- DEVIATION from source implementation: COALESCE component scores to 0.
    -- See sofa-24h.sql for rationale.
    , COALESCE(c_032, 0) AS c_032
    , COALESCE(c_289, 0) AS c_289
    , COALESCE(c_559, 0) AS c_559
    , COALESCE(c_562, 0) AS c_562
    , COALESCE(c_415, 0) AS c_415
    , COALESCE(c_599, 0) AS c_599
    , COALESCE(c_099, 0) AS c_099
    , COALESCE(c_623, 0) AS c_623
    , COALESCE(c_451, 0) AS c_451
    , COALESCE(c_536, 0) AS c_536
    , COALESCE(c_083, 0) AS c_083
    , COALESCE(c_091, 0) AS c_091
    , COALESCE(c_247, 0) AS c_247
    , COALESCE(c_136, 0) AS c_136
    , COALESCE(c_028, 0) AS c_028
FROM scorecomp
;
