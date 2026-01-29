# OASIS Troubleshooting Guide

Common issues and solutions when working with OASIS scores.

## Table Not Found Errors

### Error: "Table mimiciv_derived.oasis does not exist"

**For BigQuery users:**

1. **Check access permissions:**
   ```sql
   -- Verify you can access MIMIC-IV
   SELECT COUNT(*) FROM `physionet-data.mimiciv_icu.icustays` LIMIT 1;
   ```

2. **Verify PhysioNet credentials:**
   - Ensure you completed PhysioNet credentialing
   - Signed MIMIC-IV data use agreement
   - Have proper BigQuery project permissions

3. **Check project configuration:**
   - Verify M4 is configured with correct project ID
   - Check if dataset reference is correct: `physionet-data.mimiciv_derived`

**For DuckDB users:**

1. **Run setup:**
   See [setup-duckdb.md](setup-duckdb.md) to create derived tables

2. **Check schema exists:**
   ```sql
   CREATE SCHEMA IF NOT EXISTS mimiciv_derived;
   ```

3. **Verify base tables available:**
   ```sql
   SHOW TABLES;
   -- Should see: icu_icustays, hosp_admissions, etc.
   ```

---

## Syntax Errors

### Error: "Syntax error near 'DATETIME_ADD'"

**Cause:** Running BigQuery SQL on DuckDB

**Solution:** Use DuckDB syntax or `oasis_duckdb.sql` file

**Example fix:**
```sql
-- Wrong (BigQuery)
WHERE intime <= DATETIME_ADD(intime, INTERVAL '1' DAY)

-- Correct (DuckDB)
WHERE intime <= intime + INTERVAL '1' DAY
```

### Error: "Invalid table reference"

**Cause:** Using wrong table naming convention

**BigQuery format:**
```sql
FROM `physionet-data.mimiciv_icu.icustays`
```

**DuckDB format:**
```sql
FROM icu_icustays
```

---

## Missing Data Issues

### Error: "Column 'age' does not exist"

**Cause:** Missing derived table `mimiciv_derived.age`

**Solution:** Create prerequisite tables before OASIS

**Correct order:**
1. `age.sql`
2. `first_day_gcs.sql`
3. `first_day_vitalsign.sql`
4. `first_day_urine_output.sql`
5. `ventilation.sql`
6. `oasis_duckdb.sql`

### Query returns empty results

**Possible causes:**

1. **No ICU stays in database:**
   ```sql
   -- Check base table
   SELECT COUNT(*) FROM icu_icustays;
   ```

2. **OASIS table is empty:**
   ```sql
   -- Check derived table
   SELECT COUNT(*) FROM mimiciv_derived.oasis;
   ```

3. **Filters too restrictive:**
   ```sql
   -- Try without WHERE clause
   SELECT * FROM mimiciv_derived.oasis LIMIT 10;
   ```

---

## Performance Issues

### Query takes 30+ seconds

**Cause:** Using on-the-fly calculation instead of pre-computed table

**Symptoms:**
- First query slow, subsequent queries also slow
- CPU usage high during query
- Query has multiple nested CTEs

**Solutions:**

1. **Best: Create pre-computed tables**
   - See [setup-duckdb.md](setup-duckdb.md)
   - One-time setup, fast forever
   - Query time: <1 second

2. **Quick: Limit results**
   ```sql
   SELECT * FROM mimiciv_derived.oasis
   WHERE oasis >= 40  -- Add filters
   LIMIT 100;         -- Limit rows
   ```

3. **Temporary: Add indexes**
   ```sql
   CREATE INDEX idx_oasis_stay ON mimiciv_derived.oasis(stay_id);
   ```

### Out of memory errors

**For DuckDB:**

```sql
-- Increase memory limit
SET memory_limit='4GB';

-- Or use streaming
SET streaming_mode=true;
```

**For BigQuery:**
- Use SELECT instead of SELECT *
- Add appropriate WHERE clauses
- Consider using LIMIT for testing

---

## Data Quality Issues

### OASIS scores seem wrong

**Check component values:**

```sql
SELECT
    stay_id,
    oasis,
    age, age_score,
    gcs, gcs_score,
    heartrate, heart_rate_score
FROM mimiciv_derived.oasis
WHERE oasis > 50  -- Unusually high
LIMIT 10;
```

**Verify against manual calculation:**

```sql
-- Compare computed score vs manual sum
SELECT
    stay_id,
    oasis AS computed_score,
    COALESCE(age_score, 0) +
    COALESCE(preiculos_score, 0) +
    COALESCE(gcs_score, 0) +
    COALESCE(heart_rate_score, 0) +
    COALESCE(mbp_score, 0) +
    COALESCE(resp_rate_score, 0) +
    COALESCE(temp_score, 0) +
    COALESCE(urineoutput_score, 0) +
    COALESCE(mechvent_score, 0) +
    COALESCE(electivesurgery_score, 0) AS manual_score
FROM mimiciv_derived.oasis
LIMIT 10;
```

### Missing component scores

**Check for NULL values:**

```sql
SELECT
    COUNT(*) AS total_stays,
    SUM(CASE WHEN age IS NULL THEN 1 ELSE 0 END) AS missing_age,
    SUM(CASE WHEN gcs IS NULL THEN 1 ELSE 0 END) AS missing_gcs,
    SUM(CASE WHEN heartrate IS NULL THEN 1 ELSE 0 END) AS missing_hr,
    SUM(CASE WHEN urineoutput IS NULL THEN 1 ELSE 0 END) AS missing_uo
FROM mimiciv_derived.oasis;
```

**Note:** Some missing values are expected. OASIS uses COALESCE to score missing components as 0.

---

## Backend-Specific Issues

### BigQuery: Access Denied

**Error message:** "Access Denied: Dataset physionet-data:mimiciv_derived"

**Solutions:**

1. **Complete PhysioNet process:**
   - Register at https://physionet.org/
   - Complete required training
   - Sign MIMIC-IV data use agreement

2. **Link PhysioNet to Google Cloud:**
   - Follow instructions at https://physionet.org/settings/cloud/

3. **Check BigQuery permissions:**
   - Verify project has access to PhysioNet data
   - Ensure service account has correct roles

### DuckDB: File Permission Errors

**Error:** "IO Error: Cannot open file"

**Solutions:**

```bash
# Check database file permissions
ls -la /path/to/database.duckdb

# Ensure write access
chmod 644 /path/to/database.duckdb

# Check parent directory permissions
chmod 755 /path/to/directory
```

---

## M4-Specific Issues

### M4 not detecting OASIS table

**Check current backend:**
```python
# M4 should show current backend
# Backend: DuckDB or Backend: BigQuery
```

**Verify table in correct location:**

- **BigQuery:** `physionet-data.mimiciv_derived.oasis`
- **DuckDB:** `mimiciv_derived.oasis`

### M4 using wrong SQL syntax

**Symptom:** Query works in SQL client but fails in M4

**Solution:** Ensure M4 is using backend-appropriate SQL

- Check which SQL file M4 is executing
- Verify `oasis_duckdb.sql` is used for DuckDB
- Verify `oasis.sql` is used for BigQuery

---

## Getting Help

If issues persist:

1. **Check M4 logs** for detailed error messages

2. **Verify MIMIC-IV version compatibility:**
   - This skill is tested with MIMIC-IV v3.1
   - Older versions may have schema differences

3. **Test with minimal query:**
   ```sql
   SELECT COUNT(*) FROM mimiciv_derived.oasis LIMIT 1;
   ```

4. **Compare with MIT-LCP reference:**
   - Source: https://github.com/MIT-LCP/mimic-code
   - Check if issue exists in original SQL

5. **Review [backend-guide.md](backend-guide.md)** for detailed backend differences

6. **Consult MIMIC-IV documentation:**
   - https://mimic.mit.edu/docs/iv/
   - Community forum: https://github.com/MIT-LCP/mimic-code/discussions
