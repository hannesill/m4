-- Derived table: ventilation
-- Source: MIT-LCP/mimic-code/mimic-iv/concepts/treatment/ventilation.sql
-- Converted from BigQuery to DuckDB syntax
--
-- This query classifies mechanical ventilation status based on
-- oxygen delivery devices and ventilator modes.
--
-- Classification hierarchy (highest to lowest priority):
-- 1. Tracheostomy
-- 2. InvasiveVent (mechanical ventilation)
-- 3. NonInvasiveVent (BiPAP, CPAP)
-- 4. HFNC (High Flow Nasal Cannula)
-- 5. SupplementalOxygen (nasal cannula, face mask, etc.)
-- 6. None
--
-- Depends on: mimiciv_derived.ventilator_setting, mimiciv_derived.oxygen_delivery

CREATE TABLE IF NOT EXISTS mimiciv_derived.ventilation AS
WITH tm AS (
    -- Combine all timestamps from both ventilator settings and oxygen delivery
    SELECT stay_id, charttime
    FROM mimiciv_derived.ventilator_setting
    UNION DISTINCT
    SELECT stay_id, charttime
    FROM mimiciv_derived.oxygen_delivery
)

, vs AS (
    SELECT
        tm.stay_id
        , tm.charttime
        , od.o2_delivery_device_1
        , COALESCE(vset.ventilator_mode, vset.ventilator_mode_hamilton) AS vent_mode
        , CASE
            -- Tracheostomy
            WHEN od.o2_delivery_device_1 IN ('Tracheostomy tube', 'Trach mask ')
                THEN 'Tracheostomy'
            -- Invasive mechanical ventilation
            WHEN od.o2_delivery_device_1 IN ('Endotracheal tube')
                OR vset.ventilator_mode IN (
                    '(S) CMV', 'APRV', 'APRV/Biphasic+ApnPress', 'APRV/Biphasic+ApnVol',
                    'APV (cmv)', 'Ambient', 'Apnea Ventilation', 'CMV', 'CMV/ASSIST',
                    'CMV/ASSIST/AutoFlow', 'CMV/AutoFlow', 'CPAP/PPS', 'CPAP/PSV',
                    'CPAP/PSV+Apn TCPL', 'CPAP/PSV+ApnPres', 'CPAP/PSV+ApnVol', 'MMV',
                    'MMV/AutoFlow', 'MMV/PSV', 'MMV/PSV/AutoFlow', 'P-CMV', 'PCV+',
                    'PCV+/PSV', 'PCV+Assist', 'PRES/AC', 'PRVC/AC', 'PRVC/SIMV',
                    'PSV/SBT', 'SIMV', 'SIMV/AutoFlow', 'SIMV/PRES', 'SIMV/PSV',
                    'SIMV/PSV/AutoFlow', 'SIMV/VOL', 'SYNCHRON MASTER', 'SYNCHRON SLAVE',
                    'VOL/AC'
                )
                OR vset.ventilator_mode_hamilton IN (
                    'APRV', 'APV (cmv)', 'Ambient', '(S) CMV', 'P-CMV', 'SIMV',
                    'APV (simv)', 'P-SIMV', 'VS', 'ASV'
                )
                THEN 'InvasiveVent'
            -- Non-invasive ventilation (BiPAP, CPAP)
            WHEN od.o2_delivery_device_1 IN ('Bipap mask ', 'CPAP mask ')
                OR vset.ventilator_mode_hamilton IN ('DuoPaP', 'NIV', 'NIV-ST')
                THEN 'NonInvasiveVent'
            -- High flow nasal cannula
            WHEN od.o2_delivery_device_1 IN ('High flow nasal cannula')
                THEN 'HFNC'
            -- Supplemental oxygen
            WHEN od.o2_delivery_device_1 IN (
                'Non-rebreather', 'Face tent', 'Aerosol-cool', 'Venti mask ',
                'Medium conc mask ', 'Ultrasonic neb', 'Vapomist', 'Oxymizer',
                'High flow neb', 'Nasal cannula'
            )
                THEN 'SupplementalOxygen'
            -- None
            WHEN od.o2_delivery_device_1 IN ('None')
                THEN 'None'
            ELSE NULL
        END AS ventilation_status
    FROM tm
    LEFT JOIN mimiciv_derived.ventilator_setting vset
        ON tm.stay_id = vset.stay_id AND tm.charttime = vset.charttime
    LEFT JOIN mimiciv_derived.oxygen_delivery od
        ON tm.stay_id = od.stay_id AND tm.charttime = od.charttime
)

, vd0 AS (
    SELECT
        stay_id
        , charttime
        , LAG(charttime, 1) OVER (
            PARTITION BY stay_id, ventilation_status ORDER BY charttime
        ) AS charttime_lag
        , LEAD(charttime, 1) OVER w AS charttime_lead
        , ventilation_status
        , LAG(ventilation_status, 1) OVER w AS ventilation_status_lag
    FROM vs
    WHERE ventilation_status IS NOT NULL
    WINDOW w AS (PARTITION BY stay_id ORDER BY charttime)
)

, vd1 AS (
    SELECT
        stay_id
        , charttime
        , charttime_lag
        , charttime_lead
        , ventilation_status
        , DATE_DIFF('minute', charttime_lag, charttime) / 60.0 AS ventduration
        -- New ventilation event if:
        -- 1. First record for patient
        -- 2. Gap > 14 hours from previous record
        -- 3. Ventilation status changed
        , CASE
            WHEN ventilation_status_lag IS NULL THEN 1
            WHEN DATE_DIFF('hour', charttime_lag, charttime) >= 14 THEN 1
            WHEN ventilation_status_lag != ventilation_status THEN 1
            ELSE 0
        END AS new_ventilation_event
    FROM vd0
)

, vd2 AS (
    SELECT
        vd1.stay_id
        , vd1.charttime
        , vd1.charttime_lead
        , vd1.ventilation_status
        , ventduration
        , new_ventilation_event
        , SUM(new_ventilation_event) OVER (
            PARTITION BY stay_id ORDER BY charttime
        ) AS vent_seq
    FROM vd1
)

SELECT
    stay_id
    , MIN(charttime) AS starttime
    , MAX(CASE
        WHEN charttime_lead IS NULL
            OR DATE_DIFF('hour', charttime, charttime_lead) >= 14
            THEN charttime
        ELSE charttime_lead
    END) AS endtime
    , MAX(ventilation_status) AS ventilation_status
FROM vd2
GROUP BY stay_id, vent_seq
HAVING MIN(charttime) != MAX(charttime)
;
