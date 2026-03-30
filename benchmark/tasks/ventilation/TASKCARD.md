# Ventilation Classification

## What it is

Classifies each ICU charting observation into a ventilation status category and groups
consecutive observations into ventilation episodes. The ventilation concept is used by
SOFA (respiratory component requires invasive mechanical ventilation for scores 3-4),
OASIS, and many other severity scores and research definitions.

## The 5 categories (+ None)

| Category | Description |
|----------|-------------|
| Tracheostomy | Patient has a tracheostomy tube |
| InvasiveVent | Invasive mechanical ventilation via endotracheal tube or ventilator mode |
| NonInvasiveVent | Non-invasive positive pressure ventilation (BiPAP, CPAP mask, NIV) |
| HFNC | High-flow nasal cannula |
| SupplementalOxygen | Standard oxygen delivery (nasal cannula, non-rebreather, face tent, etc.) |
| None | No supplemental oxygen (room air) |

## Data sources in MIMIC-IV

- **Ventilator settings**: `mimiciv_derived.ventilator_setting` (standard) or
  `mimiciv_icu.chartevents` itemids 223849, 229314, 223848 + settings itemids (raw)
- **Oxygen delivery**: `mimiciv_derived.oxygen_delivery` (standard) or
  `mimiciv_icu.chartevents` itemid 226732 + flow itemids 223834, 227582, 227287 (raw)

## Why this tests different capabilities than severity scores

- **Temporal classification**: Tests classifying device/mode strings into categories
- **Episode detection**: Tests gap detection (14h threshold) and episode merging
- **Variable-length output**: Multiple rows per stay (one per episode), not one row per stay
- **Composite key**: `stay_id` + `ventilation_seq` (sequence number within stay)
- **String matching**: Classification depends on exact string matches against extensive
  lists of ventilator modes and oxygen delivery devices
- **No numeric scoring**: Output is categorical (ventilation status label)

## Why standard vs raw

- **Standard**: `mimiciv_derived.ventilator_setting` and `mimiciv_derived.oxygen_delivery`
  are available (already pivoted from chartevents)
- **Raw**: Both intermediate tables are dropped; agent must extract ventilator mode,
  oxygen device, and other settings directly from `mimiciv_icu.chartevents` using
  specific itemids

## Subtleties to watch for

- **Trailing spaces**: Several device values have trailing spaces (e.g., 'Trach mask ',
  'Bipap mask ', 'Venti mask ', 'Medium conc mask '). These must match exactly.
- **CPAP/PSV is InvasiveVent**: CPAP/PSV modes are recorded on patients with endotracheal
  tubes. Non-invasive CPAP is identified by the CPAP mask device, not the ventilator mode.
- **14-hour gap rule**: Consecutive observations of the same status > 14h apart are separate
  episodes. The LAG function partitions by `(stay_id, ventilation_status)`.
- **Single-observation episodes excluded**: Episodes where starttime == endtime are filtered
  out (HAVING MIN(charttime) <> MAX(charttime)).
- **Hamilton vs standard modes**: Two ventilator mode columns are combined with COALESCE.
  Hamilton modes like 'NIV', 'NIV-ST', 'DuoPaP' are NonInvasiveVent while other Hamilton
  modes are InvasiveVent.
- **Priority hierarchy**: Tracheostomy > InvasiveVent > NonInvasiveVent > HFNC >
  SupplementalOxygen > None. The CASE WHEN ordering implements this.
