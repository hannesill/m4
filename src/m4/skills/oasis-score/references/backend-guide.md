# Backend Guide: BigQuery vs DuckDB

Detailed guide for using OASIS with different backends.

## Overview

| Feature | BigQuery | DuckDB |
|---------|----------|--------|
| **Setup Required** | No | Yes (one-time) |
| **Pre-computed Tables** | ✅ Available | ❌ Must create |
| **Query Performance** | Fast (~100ms) | Fast after setup (~100ms) |
| **Table Location** | `physionet-data.mimiciv_derived` | `mimiciv_derived` |
| **SQL Syntax** | BigQuery Standard SQL | PostgreSQL-compatible |
| **Best For** | Cloud, large datasets | Local, development |

---

## SQL Syntax Differences

### Table References

**BigQuery:**
```sql
FROM `physionet-data.mimiciv_icu.icustays`
FROM `physionet-data.mimiciv_derived.oasis`
```

**DuckDB:**
```sql
FROM icu_icustays
FROM mimiciv_derived.oasis
```

---

### Date/Time Operations

#### Date Addition

**BigQuery:**
```sql
DATETIME_ADD(intime, INTERVAL '1' DAY)
DATETIME_ADD(intime, INTERVAL 24 HOUR)
```

**DuckDB:**
```sql
intime + INTERVAL '1' DAY
intime + INTERVAL '24' HOUR
```

#### Date Difference

**BigQuery:**
```sql
DATETIME_DIFF(intime, admittime, MINUTE)
DATETIME_DIFF(intime, admittime, HOUR)
```

**DuckDB:**
```sql
DATEDIFF('minute', admittime, intime)  -- Note: reversed order!
DATEDIFF('hour', admittime, intime)
```

**⚠️ Important:** DuckDB DATEDIFF has reversed parameter order!

#### Date Extraction

**Same in both:**
```sql
EXTRACT(YEAR FROM admittime)
EXTRACT(MONTH FROM admittime)
EXTRACT(DAY FROM admittime)
```

---

### String Operations

#### LIKE (Case Sensitivity)

**BigQuery:**
```sql
-- Case-insensitive by default
WHERE service LIKE '%surg%'
```

**DuckDB:**
```sql
-- Case-sensitive by default, use LOWER/UPPER
WHERE LOWER(service) LIKE '%surg%'
```

#### String Functions

**Same in both:**
```sql
LOWER(text)
UPPER(text)
CONCAT(a, b)
SUBSTRING(text, start, length)
```

---

### Mathematical Functions

**Same in both:**
```sql
EXP(x)
LOG(x)
POWER(x, y)
SQRT(x)
ABS(x)
ROUND(x, decimals)
```

---

### Aggregation and NULL Handling

**Same in both:**
```sql
COALESCE(value, 0)
NULLIF(value, 0)
MAX(CASE WHEN condition THEN 1 ELSE 0 END)
```

---

### Window Functions

**Same in both:**
```sql
ROW_NUMBER() OVER (PARTITION BY stay_id ORDER BY time)
RANK() OVER (ORDER BY score DESC)
LAG(value, 1) OVER (PARTITION BY patient ORDER BY time)
```

---

## Complete Conversion Example

### BigQuery OASIS Query

```sql
WITH surgflag AS (
    SELECT ie.stay_id
        , MAX(CASE
            WHEN LOWER(curr_service) LIKE '%surg%' THEN 1
            WHEN curr_service = 'ORTHO' THEN 1
            ELSE 0 END) AS surgical
    FROM `physionet-data.mimiciv_icu.icustays` ie
    LEFT JOIN `physionet-data.mimiciv_hosp.services` se
        ON ie.hadm_id = se.hadm_id
            AND se.transfertime < DATETIME_ADD(ie.intime, INTERVAL '1' DAY)
    GROUP BY ie.stay_id
)
SELECT
    stay_id,
    DATETIME_DIFF(intime, admittime, MINUTE) AS preiculos
FROM `physionet-data.mimiciv_icu.icustays` ie
INNER JOIN `physionet-data.mimiciv_hosp.admissions` adm
    ON ie.hadm_id = adm.hadm_id;
```

### DuckDB OASIS Query

```sql
WITH surgflag AS (
    SELECT ie.stay_id
        , MAX(CASE
            WHEN LOWER(curr_service) LIKE '%surg%' THEN 1
            WHEN curr_service = 'ORTHO' THEN 1
            ELSE 0 END) AS surgical
    FROM icu_icustays ie
    LEFT JOIN hosp_services se
        ON ie.hadm_id = se.hadm_id
            AND se.transfertime < ie.intime + INTERVAL '1' DAY
    GROUP BY ie.stay_id
)
SELECT
    stay_id,
    DATEDIFF('minute', admittime, intime) AS preiculos
FROM icu_icustays ie
INNER JOIN hosp_admissions adm
    ON ie.hadm_id = adm.hadm_id;
```

**Key changes:**
1. Remove backticks from table names
2. Use short table names (icu_icustays vs mimiciv_icu.icustays)
3. `DATETIME_ADD(x, INTERVAL '1' DAY)` → `x + INTERVAL '1' DAY`
4. `DATETIME_DIFF(a, b, MINUTE)` → `DATEDIFF('minute', b, a)` (reversed!)

---

## Performance Optimization

### BigQuery Best Practices

1. **Use materialized tables when available:**
   ```sql
   -- Pre-computed tables are already optimized
   FROM `physionet-data.mimiciv_derived.oasis`
   ```

2. **Partition filtering:**
   ```sql
   -- Use partitioned columns efficiently
   WHERE DATE(intime) >= '2020-01-01'
   ```

3. **SELECT specific columns:**
   ```sql
   -- Avoid SELECT *
   SELECT stay_id, oasis, oasis_prob
   FROM `physionet-data.mimiciv_derived.oasis`
   ```

4. **Use LIMIT for exploration:**
   ```sql
   SELECT * FROM `physionet-data.mimiciv_derived.oasis`
   LIMIT 1000;
   ```

### DuckDB Best Practices

1. **Create indexes:**
   ```sql
   CREATE INDEX idx_oasis_stay ON mimiciv_derived.oasis(stay_id);
   CREATE INDEX idx_oasis_score ON mimiciv_derived.oasis(oasis);
   ```

2. **Set memory limit:**
   ```sql
   SET memory_limit='4GB';
   ```

3. **Use EXPLAIN for query planning:**
   ```sql
   EXPLAIN SELECT * FROM mimiciv_derived.oasis WHERE oasis >= 30;
   ```

4. **Materialize complex views:**
   ```sql
   CREATE TABLE oasis_high_risk AS
   SELECT * FROM mimiciv_derived.oasis WHERE oasis >= 40;
   ```

---

## Common Patterns

### Pattern 1: Find High-Risk Patients

**BigQuery:**
```sql
SELECT
    stay_id,
    oasis,
    oasis_prob
FROM `physionet-data.mimiciv_derived.oasis`
WHERE oasis_prob >= 0.5
ORDER BY oasis_prob DESC
LIMIT 100;
```

**DuckDB:**
```sql
SELECT
    stay_id,
    oasis,
    oasis_prob
FROM mimiciv_derived.oasis
WHERE oasis_prob >= 0.5
ORDER BY oasis_prob DESC
LIMIT 100;
```

**Only difference:** Table path

---

### Pattern 2: Join with ICU Stays

**BigQuery:**
```sql
SELECT
    o.stay_id,
    o.oasis,
    ie.intime,
    ie.outtime,
    ie.los
FROM `physionet-data.mimiciv_derived.oasis` o
INNER JOIN `physionet-data.mimiciv_icu.icustays` ie
    ON o.stay_id = ie.stay_id
WHERE o.oasis >= 30;
```

**DuckDB:**
```sql
SELECT
    o.stay_id,
    o.oasis,
    ie.intime,
    ie.outtime,
    ie.los
FROM mimiciv_derived.oasis o
INNER JOIN icu_icustays ie
    ON o.stay_id = ie.stay_id
WHERE o.oasis >= 30;
```

**Only difference:** Table paths

---

### Pattern 3: Aggregate Statistics

**Same in both (just change table paths):**

```sql
SELECT
    CASE
        WHEN oasis < 20 THEN 'Low'
        WHEN oasis < 30 THEN 'Moderate'
        WHEN oasis < 40 THEN 'High'
        ELSE 'Very High'
    END AS risk_category,
    COUNT(*) AS num_patients,
    AVG(oasis) AS avg_score,
    AVG(oasis_prob) AS avg_mortality,
    MIN(oasis) AS min_score,
    MAX(oasis) AS max_score
FROM [TABLE_PATH]
GROUP BY risk_category
ORDER BY avg_score;
```

---

## Migration Guide

### Moving from BigQuery to DuckDB

1. **Export data from BigQuery:**
   ```sql
   EXPORT DATA OPTIONS(
     uri='gs://your-bucket/oasis-*.parquet',
     format='PARQUET'
   ) AS
   SELECT * FROM `physionet-data.mimiciv_derived.oasis`;
   ```

2. **Load into DuckDB:**
   ```sql
   CREATE TABLE mimiciv_derived.oasis AS
   SELECT * FROM read_parquet('oasis-*.parquet');
   ```

3. **Update queries:**
   - Change table references
   - Fix syntax differences (DATETIME_ADD, DATEDIFF)

### Moving from DuckDB to BigQuery

1. **Export from DuckDB:**
   ```sql
   COPY mimiciv_derived.oasis
   TO 'oasis.parquet' (FORMAT PARQUET);
   ```

2. **Upload to Google Cloud Storage:**
   ```bash
   gsutil cp oasis.parquet gs://your-bucket/
   ```

3. **Load into BigQuery:**
   ```sql
   LOAD DATA INTO `your-project.your-dataset.oasis`
   FROM FILES (
     format = 'PARQUET',
     uris = ['gs://your-bucket/oasis.parquet']
   );
   ```

---

## Testing Queries

### Validate Query Works on Both Backends

**1. Test on small dataset first:**
```sql
-- BigQuery
SELECT * FROM `physionet-data.mimiciv_derived.oasis` LIMIT 10;

-- DuckDB
SELECT * FROM mimiciv_derived.oasis LIMIT 10;
```

**2. Compare results:**
```sql
-- Should return same stay_ids
SELECT stay_id, oasis, oasis_prob
FROM [TABLE_PATH]
WHERE stay_id = 30000032;
```

**3. Check aggregates match:**
```sql
SELECT
    COUNT(*) AS total,
    AVG(oasis) AS avg_score,
    MIN(oasis) AS min_score,
    MAX(oasis) AS max_score
FROM [TABLE_PATH];
```

---

## Troubleshooting

See [troubleshooting.md](troubleshooting.md) for common issues and solutions.

For setup help, see [setup-duckdb.md](setup-duckdb.md).
