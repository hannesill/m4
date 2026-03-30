# Task: Classify Ventilation Status (Raw Tables)

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp` and `mimiciv_icu`.
Note: `mimiciv_derived.ventilator_setting` and `mimiciv_derived.oxygen_delivery`
are NOT available. Extract data directly from `mimiciv_icu.chartevents`.

Classify ventilation status from charting data and group consecutive
observations into ventilation episodes for each ICU stay.

### Ventilation Categories

Classify each charting observation into one of these categories, in priority order:

| Priority | Category | Criteria |
|----------|----------|----------|
| 1 | Tracheostomy | O2 device = 'Tracheostomy tube' or 'Trach mask ' |
| 2 | InvasiveVent | O2 device = 'Endotracheal tube', OR any invasive ventilator mode present |
| 3 | NonInvasiveVent | O2 device = 'Bipap mask ' or 'CPAP mask ', OR Hamilton modes: DuoPaP, NIV, NIV-ST |
| 4 | HFNC | O2 device = 'High flow nasal cannula' |
| 5 | SupplementalOxygen | O2 device = Non-rebreather, Face tent, Aerosol-cool, Venti mask, Medium conc mask, Ultrasonic neb, Vapomist, Oxymizer, High flow neb, Nasal cannula |
| 6 | None | O2 device = 'None' |

**Invasive ventilator modes** (from itemid 223849 — Ventilator Mode):
(S) CMV, APRV, APRV/Biphasic+ApnPress, APRV/Biphasic+ApnVol, APV (cmv), Ambient, Apnea Ventilation, CMV, CMV/ASSIST, CMV/ASSIST/AutoFlow, CMV/AutoFlow, CPAP/PPS, CPAP/PSV, CPAP/PSV+Apn TCPL, CPAP/PSV+ApnPres, CPAP/PSV+ApnVol, MMV, MMV/AutoFlow, MMV/PSV, MMV/PSV/AutoFlow, P-CMV, PCV+, PCV+/PSV, PCV+Assist, PRES/AC, PRVC/AC, PRVC/SIMV, PSV/SBT, SIMV, SIMV/AutoFlow, SIMV/PRES, SIMV/PSV, SIMV/PSV/AutoFlow, SIMV/VOL, SYNCHRON MASTER, SYNCHRON SLAVE, VOL/AC

**Invasive Hamilton modes** (from itemid 229314 — Ventilator Mode Hamilton):
APRV, APV (cmv), Ambient, (S) CMV, P-CMV, SIMV, APV (simv), P-SIMV, VS, ASV

**Non-invasive Hamilton modes** (from itemid 229314):
DuoPaP, NIV, NIV-ST

### Raw Data Extraction

Extract from `mimiciv_icu.chartevents`:

**Ventilator settings** (pivot by charttime):
- 223849: Ventilator Mode (text `value`)
- 229314: Ventilator Mode Hamilton (text `value`)

**Oxygen delivery device** (from chartevents):
- 226732: O2 Delivery Device (text `value`)

**Additional ventilator presence itemids** (used to create the timeline):
- 224688, 224689, 224690, 224687, 224685, 224684, 224686, 224696: Respiratory parameters
- 220339, 224700: PEEP
- 223835: FiO2
- 224691: Flow Rate
- 223848: Ventilator Type
- 223834, 227582: O2 Flow
- 227287: O2 Flow (additional)

Create a combined timeline from all ventilator setting and oxygen delivery
observations, then classify each timepoint.

### Episode Detection

Group individual observations into episodes using these rules:

1. **New episode starts when**:
   - First observation for a stay
   - Gap of >= 14 hours between consecutive same-status observations
   - Ventilation status changes from the previous observation

2. **14-hour gap**: The LAG for gap detection partitions by
   `(stay_id, ventilation_status)`, not just `stay_id`

3. **Episode boundaries**:
   - `starttime` = earliest charttime in the episode
   - `endtime` = latest charttime (or next observation's charttime if within 14h gap)

4. **Exclude single-observation episodes**: Filter out episodes where
   starttime equals endtime

5. **Exclude NULL status**: Observations with no classification are dropped

### Output

`ventilation_seq` = ROW_NUMBER() within each stay, ordered by starttime.

Output a CSV file to `{output_path}` with these exact columns:
stay_id, ventilation_seq, starttime, endtime, ventilation_status

One row per ventilation episode. Multiple rows per ICU stay.
