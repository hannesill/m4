# DuckDB Setup Guide for OASIS

This guide walks through setting up the OASIS derived tables in DuckDB.

## Prerequisites

- MIMIC-IV data loaded in DuckDB
- Base tables available: `icu_icustays`, `hosp_admissions`, `hosp_patients`, `hosp_services`, etc.

## Overview

DuckDB does not include pre-computed derived tables. You need to create:

1. `mimiciv_derived.age`
2. `mimiciv_derived.first_day_gcs`
3. `mimiciv_derived.first_day_vitalsign`
4. `mimiciv_derived.first_day_urine_output`
5. `mimiciv_derived.ventilation`
6. `mimiciv_derived.oasis`

**Estimated time:** 1 hour one-time setup

## Quick Setup

### Step 1: Create Schema

```sql
CREATE SCHEMA IF NOT EXISTS mimiciv_derived;
```

### Step 2: Create Derived Tables

Run the SQL files in this order:

```bash
# 1. Age calculation
duckdb your_database.db < age.sql

# 2. First day GCS
duckdb your_database.db < first_day_gcs.sql

# 3. First day vital signs
duckdb your_database.db < first_day_vitalsign.sql

# 4. First day urine output
duckdb your_database.db < first_day_urine_output.sql

# 5. Ventilation periods
duckdb your_database.db < ventilation.sql

# 6. Finally, OASIS
duckdb your_database.db < scripts/oasis_duckdb.sql
```

### Step 3: Verify Setup

```sql
-- Check all derived tables exist
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'mimiciv_derived'
ORDER BY table_name;

-- Expected output:
-- age
-- first_day_gcs
-- first_day_vitalsign
-- first_day_urine_output
-- oasis
-- ventilation

-- Check OASIS table has data
SELECT COUNT(*) AS total_stays FROM mimiciv_derived.oasis;
```

## Detailed Setup Instructions

### Option 1: Using Pre-converted SQL Files

If `scripts/oasis_duckdb.sql` and dependency files are available:

```bash
# Run in order
duckdb /path/to/mimic_iv.duckdb < age.sql
duckdb /path/to/mimic_iv.duckdb < first_day_gcs.sql
duckdb /path/to/mimic_iv.duckdb < first_day_vitalsign.sql
duckdb /path/to/mimic_iv.duckdb < first_day_urine_output.sql
duckdb /path/to/mimic_iv.duckdb < ventilation.sql
duckdb /path/to/mimic_iv.duckdb < scripts/oasis_duckdb.sql
```

### Option 2: Converting from BigQuery SQL

If starting from BigQuery SQL files:

1. Download source files from MIT-LCP/mimic-code:
   - https://github.com/MIT-LCP/mimic-code/tree/main/mimic-iv/concepts

2. Convert syntax (see [backend-guide.md](backend-guide.md) for conversion rules)

3. Run converted files in dependency order

## Common Setup Issues

### Issue: "Table does not exist"

**Cause:** Running OASIS before creating dependency tables

**Solution:** Create tables in correct order (age → firstday tables → ventilation → oasis)

### Issue: "Syntax error near DATETIME_ADD"

**Cause:** Using BigQuery SQL instead of DuckDB SQL

**Solution:** Use `scripts/oasis_duckdb.sql` or convert syntax

### Issue: Long execution time

**Expected:** First-time table creation can take 5-10 minutes for full MIMIC-IV

**Normal timing:**
- age: ~1 minute
- first_day_gcs: ~2 minutes
- first_day_vitalsign: ~3 minutes
- first_day_urine_output: ~2 minutes
- ventilation: ~5 minutes
- oasis: ~2 minutes

## Performance Optimization

### Create Indexes (Optional)

After creating tables, add indexes for better query performance:

```sql
-- Index on stay_id for joins
CREATE INDEX idx_oasis_stay ON mimiciv_derived.oasis(stay_id);
CREATE INDEX idx_oasis_subject ON mimiciv_derived.oasis(subject_id);
CREATE INDEX idx_oasis_hadm ON mimiciv_derived.oasis(hadm_id);

-- Index on score for filtering
CREATE INDEX idx_oasis_score ON mimiciv_derived.oasis(oasis);
CREATE INDEX idx_oasis_prob ON mimiciv_derived.oasis(oasis_prob);
```

### Materialize Tables (Optional)

For fastest queries, materialize derived tables:

```sql
-- Create materialized table
CREATE TABLE mimiciv_derived.oasis_mat AS 
SELECT * FROM mimiciv_derived.oasis;

-- Use materialized version
SELECT * FROM mimiciv_derived.oasis_mat WHERE oasis >= 30;
```

## Alternative: On-the-fly Calculation

If you cannot create derived tables, use on-the-fly calculation with `scripts/oasis_duckdb.sql`:

```sql
-- Run scripts/oasis_duckdb.sql as a single query
-- Note: This is slow (30+ seconds) but doesn't require setup
```

**Pros:**
- No setup required
- Always up-to-date

**Cons:**
- 30-100x slower than pre-computed tables
- Recomputes on every query
- Not practical for production use

## Maintenance

### Updating Data

When MIMIC-IV data is updated:

```sql
-- Drop existing derived tables
DROP TABLE IF EXISTS mimiciv_derived.oasis CASCADE;
DROP TABLE IF EXISTS mimiciv_derived.ventilation CASCADE;
-- ... (drop all derived tables)

-- Re-run setup from Step 2
```

### Checking Table Freshness

```sql
-- Check when OASIS table was created
SELECT 
    table_name,
    table_type
FROM information_schema.tables 
WHERE table_schema = 'mimiciv_derived'
    AND table_name = 'oasis';
```

## Next Steps

After setup:
- Run example queries from SKILL.md
- See [troubleshooting.md](troubleshooting.md) if issues arise
- Check [backend-guide.md](backend-guide.md) for query optimization tips
