-- Derived table: ventilator_setting
-- Source: MIT-LCP/mimic-code/mimic-iv/concepts/measurement/ventilator_setting.sql
-- Converted from BigQuery to DuckDB syntax
--
-- This query extracts ventilator settings from chartevents, including:
-- respiratory rate, tidal volume, minute volume, PEEP, FiO2, flow rate,
-- and ventilator mode.

CREATE TABLE IF NOT EXISTS mimiciv_derived.ventilator_setting AS
WITH ce AS (
    SELECT
        ce.subject_id
        , ce.stay_id
        , ce.charttime
        , itemid
        , value
        , CASE
            -- FiO2 (itemid 223835): handle different input formats
            WHEN itemid = 223835
                THEN
                CASE
                    -- values 0.20-1.0 are fractions, convert to percentage
                    WHEN valuenum >= 0.20 AND valuenum <= 1
                        THEN valuenum * 100
                    -- values 1-20 are invalid
                    WHEN valuenum > 1 AND valuenum < 20
                        THEN NULL
                    -- values 20-100 are already percentages
                    WHEN valuenum >= 20 AND valuenum <= 100
                        THEN valuenum
                    ELSE NULL END
            -- PEEP (itemids 220339, 224700): filter invalid values
            WHEN itemid IN (220339, 224700)
                THEN
                CASE
                    WHEN valuenum > 100 THEN NULL
                    WHEN valuenum < 0 THEN NULL
                    ELSE valuenum END
            ELSE valuenum END AS valuenum
        , valueuom
        , storetime
    FROM icu_chartevents ce
    WHERE ce.value IS NOT NULL
        AND ce.stay_id IS NOT NULL
        AND ce.itemid IN (
            224688,   -- Respiratory Rate (Set)
            224689,   -- Respiratory Rate (spontaneous)
            224690,   -- Respiratory Rate (Total)
            224687,   -- Minute Volume
            224685,   -- Tidal Volume (observed)
            224684,   -- Tidal Volume (set)
            224686,   -- Tidal Volume (spontaneous)
            224696,   -- Plateau Pressure
            220339,   -- PEEP set
            224700,   -- PEEP (Total)
            223835,   -- FiO2
            223849,   -- Ventilator Mode
            229314,   -- Ventilator Mode (Hamilton)
            223848,   -- Ventilator Type
            224691    -- Flow Rate (L/min)
        )
)

SELECT
    subject_id
    , MAX(stay_id) AS stay_id
    , charttime
    , MAX(CASE WHEN itemid = 224688 THEN valuenum ELSE NULL END) AS respiratory_rate_set
    , MAX(CASE WHEN itemid = 224690 THEN valuenum ELSE NULL END) AS respiratory_rate_total
    , MAX(CASE WHEN itemid = 224689 THEN valuenum ELSE NULL END) AS respiratory_rate_spontaneous
    , MAX(CASE WHEN itemid = 224687 THEN valuenum ELSE NULL END) AS minute_volume
    , MAX(CASE WHEN itemid = 224684 THEN valuenum ELSE NULL END) AS tidal_volume_set
    , MAX(CASE WHEN itemid = 224685 THEN valuenum ELSE NULL END) AS tidal_volume_observed
    , MAX(CASE WHEN itemid = 224686 THEN valuenum ELSE NULL END) AS tidal_volume_spontaneous
    , MAX(CASE WHEN itemid = 224696 THEN valuenum ELSE NULL END) AS plateau_pressure
    , MAX(CASE WHEN itemid IN (220339, 224700) THEN valuenum ELSE NULL END) AS peep
    , MAX(CASE WHEN itemid = 223835 THEN valuenum ELSE NULL END) AS fio2
    , MAX(CASE WHEN itemid = 224691 THEN valuenum ELSE NULL END) AS flow_rate
    , MAX(CASE WHEN itemid = 223849 THEN value ELSE NULL END) AS ventilator_mode
    , MAX(CASE WHEN itemid = 229314 THEN value ELSE NULL END) AS ventilator_mode_hamilton
    , MAX(CASE WHEN itemid = 223848 THEN value ELSE NULL END) AS ventilator_type
FROM ce
GROUP BY subject_id, charttime
;
