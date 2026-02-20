WITH
  cohorts AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      MAX(CASE
          WHEN d.icd_code LIKE '410%' OR d.icd_code LIKE 'I21%' THEN 1
          ELSE 0
      END) AS is_ami_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    LEFT JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 38 AND 48
    GROUP BY
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
  ),
  lab_events_72h AS (
    SELECT
      c.hadm_id,
      c.is_ami_admission,
      le.itemid,
      le.valuenum
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN
      cohorts AS c
      ON le.hadm_id = c.hadm_id
    WHERE
      le.itemid IN (
        50912,
        51003,
        50983,
        50971,
        50931,
        51006
      )
      AND le.valuenum IS NOT NULL
      AND le.charttime BETWEEN c.admittime AND DATETIME_ADD(c.admittime, INTERVAL 72 HOUR)
  ),
  instability_calculation AS (
    SELECT
      hadm_id,
      is_ami_admission,
      CASE
        WHEN itemid = 50912 AND valuenum > 1.2  THEN 1
        WHEN itemid = 51003 AND valuenum > 0.01 THEN 1
        WHEN itemid = 50983 AND (valuenum < 135 OR valuenum > 145) THEN 1
        WHEN itemid = 50971 AND (valuenum < 3.5 OR valuenum > 5.2) THEN 1
        WHEN itemid = 50931 AND (valuenum < 70 OR valuenum > 180) THEN 1
        WHEN itemid = 51006 AND valuenum > 20  THEN 1
        ELSE 0
      END AS is_critical
    FROM
      lab_events_72h
  ),
  ami_patient_quartiles AS (
    SELECT
      hadm_id,
      instability_score,
      NTILE(4) OVER (ORDER BY instability_score) AS score_quartile
    FROM (
      SELECT
        hadm_id,
        100.0 * SUM(is_critical) / NULLIF(COUNT(is_critical), 0) AS instability_score
      FROM
        instability_calculation
      WHERE
        is_ami_admission = 1
      GROUP BY
        hadm_id
      )
    WHERE instability_score IS NOT NULL
  ),
  final_ami_stats AS (
    SELECT
      q.score_quartile,
      COUNT(DISTINCT c.hadm_id) AS num_patients,
      AVG(q.instability_score) AS avg_instability_score,
      AVG(DATETIME_DIFF(c.dischtime, c.admittime, DAY)) AS avg_los_days,
      AVG(c.hospital_expire_flag) AS mortality_rate
    FROM
      ami_patient_quartiles AS q
    INNER JOIN
      cohorts AS c
      ON q.hadm_id = c.hadm_id
    GROUP BY
      q.score_quartile
  ),
  comparison_rates AS (
    SELECT
      AVG(CASE WHEN is_ami_admission = 1 THEN is_critical ELSE NULL END) AS ami_group_critical_rate,
      AVG(CASE WHEN is_ami_admission = 0 THEN is_critical ELSE NULL END) AS control_group_critical_rate
    FROM
      instability_calculation
  )
SELECT
  s.score_quartile,
  s.num_patients,
  ROUND(s.avg_instability_score, 2) AS avg_instability_score_0_100,
  ROUND(s.avg_los_days, 1) AS avg_los_days,
  ROUND(s.mortality_rate, 3) AS mortality_rate,
  ROUND(r.ami_group_critical_rate, 3) AS ami_group_critical_rate,
  ROUND(r.control_group_critical_rate, 3) AS control_group_critical_rate
FROM
  final_ami_stats AS s
CROSS JOIN
  comparison_rates AS r
ORDER BY
  s.score_quartile;
