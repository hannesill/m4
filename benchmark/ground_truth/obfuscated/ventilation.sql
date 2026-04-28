-- ------------------------------------------------------------------
-- Title: Ventilation Classification
-- Classifies ventilation c_550 from charting data and groups
-- consecutive observations into episodes. Categories: InvasiveVent,
-- NonInvasiveVent, HFNC, SupplementalOxygen, Tracheostomy, None.
-- ------------------------------------------------------------------

-- Reference:
--    MIT-LCP mimic-c_134 ventilation concept definition.

-- Adapted from mimic-c_134 ventilation.sql
-- Adds ventilation_seq column for deterministic row matching.

WITH tm AS (
  SELECT
    c_552,
    c_114
  FROM ds_1.t_061
  UNION
  SELECT
    c_552,
    c_114
  FROM ds_1.t_047
), vs AS (
  SELECT
    tm.c_552,
    tm.c_114,
    c_390,
    COALESCE(c_615, c_616) AS vent_mode,
    CASE
      WHEN c_390 IN ('Tracheostomy tube', 'Trach mask ')
      THEN 'Tracheostomy'
      WHEN c_390 IN ('Endotracheal tube')
      OR c_615 IN ('(S) CMV', 'APRV', 'APRV/Biphasic+ApnPress', 'APRV/Biphasic+ApnVol', 'APV (cmv)', 'Ambient', 'Apnea Ventilation', 'CMV', 'CMV/ASSIST', 'CMV/ASSIST/AutoFlow', 'CMV/AutoFlow', 'CPAP/PPS', 'CPAP/PSV', 'CPAP/PSV+Apn TCPL', 'CPAP/PSV+ApnPres', 'CPAP/PSV+ApnVol', 'MMV', 'MMV/AutoFlow', 'MMV/PSV', 'MMV/PSV/AutoFlow', 'P-CMV', 'PCV+', 'PCV+/PSV', 'PCV+Assist', 'PRES/AC', 'PRVC/AC', 'PRVC/SIMV', 'PSV/SBT', 'SIMV', 'SIMV/AutoFlow', 'SIMV/PRES', 'SIMV/PSV', 'SIMV/PSV/AutoFlow', 'SIMV/VOL', 'SYNCHRON MASTER', 'SYNCHRON SLAVE', 'VOL/AC')
      OR c_616 IN ('APRV', 'APV (cmv)', 'Ambient', '(S) CMV', 'P-CMV', 'SIMV', 'APV (simv)', 'P-SIMV', 'VS', 'ASV')
      THEN 'InvasiveVent'
      WHEN c_390 IN ('Bipap mask ', 'CPAP mask ')
      OR c_616 IN ('DuoPaP', 'NIV', 'NIV-ST')
      THEN 'NonInvasiveVent'
      WHEN c_390 IN ('High flow nasal cannula')
      THEN 'HFNC'
      WHEN c_390 IN ('Non-rebreather', 'Face tent', 'Aerosol-cool', 'Venti mask ', 'Medium conc mask ', 'Ultrasonic neb', 'Vapomist', 'Oxymizer', 'High flow neb', 'Nasal cannula')
      THEN 'SupplementalOxygen'
      WHEN c_390 IN ('None')
      THEN 'None'
      ELSE NULL
    END AS c_614
  FROM tm
  LEFT JOIN ds_1.t_061 AS vs
    ON tm.c_552 = vs.c_552 AND tm.c_114 = vs.c_114
  LEFT JOIN ds_1.t_047 AS od
    ON tm.c_552 = od.c_552 AND tm.c_114 = od.c_114
), vd0 AS (
  SELECT
    c_552,
    c_114,
    LAG(c_114, 1) OVER (PARTITION BY c_552, c_614 ORDER BY c_114 NULLS FIRST) AS charttime_lag,
    LEAD(c_114, 1) OVER w AS charttime_lead,
    c_614,
    LAG(c_614, 1) OVER w AS ventilation_status_lag
  FROM vs
  WHERE
    NOT c_614 IS NULL
  WINDOW w AS (PARTITION BY c_552 ORDER BY c_114 NULLS FIRST)
), vd1 AS (
  SELECT
    c_552,
    c_114,
    charttime_lag,
    charttime_lead,
    c_614,
    DATE_DIFF('microseconds', charttime_lag, c_114)/60000000.0 / 60 AS ventduration,
    CASE
      WHEN ventilation_status_lag IS NULL
      THEN 1
      WHEN DATE_DIFF('microseconds', charttime_lag, c_114)/3600000000.0 >= 14
      THEN 1
      WHEN ventilation_status_lag <> c_614
      THEN 1
      ELSE 0
    END AS new_ventilation_event
  FROM vd0
), vd2 AS (
  SELECT
    vd1.c_552,
    vd1.c_114,
    vd1.charttime_lead,
    vd1.c_614,
    ventduration,
    new_ventilation_event,
    SUM(new_ventilation_event) OVER (PARTITION BY c_552 ORDER BY c_114 NULLS FIRST) AS vent_seq
  FROM vd1
), episodes AS (
  SELECT
    c_552,
    MIN(c_114) AS c_549,
    MAX(
      CASE
        WHEN charttime_lead IS NULL
        OR DATE_DIFF('microseconds', c_114, charttime_lead)/3600000000.0 >= 14
        THEN c_114
        ELSE charttime_lead
      END
    ) AS c_212,
    MAX(c_614) AS c_614
  FROM vd2
  GROUP BY
    c_552,
    vent_seq
  HAVING
    MIN(c_114) <> MAX(c_114)
)
SELECT
  c_552,
  ROW_NUMBER() OVER (PARTITION BY c_552 ORDER BY c_549) AS ventilation_seq,
  c_549,
  c_212,
  c_614
FROM episodes
