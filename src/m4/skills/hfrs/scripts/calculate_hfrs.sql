-- ============================================================================
-- Hospital Frailty Risk Score (HFRS) Calculator for MIMIC-IV
-- Based on: Gilbert T, et al. Lancet 2018; 391: 1775-82
--
-- METHODOLOGY:
-- The original HFRS uses diagnoses from:
--   1. The current (index) admission
--   2. All emergency admissions in the preceding 2 years
--
-- This implementation calculates HFRS for each admission using the patient's
-- cumulative diagnosis history (current + prior 2 years of emergency visits).
--
-- Supports both ICD-9 and ICD-10 codes (ICD-9 mapping added for MIMIC-IV
-- compatibility - not part of original publication which used UK NHS ICD-10 only)
-- ============================================================================

-- Step 1: Create HFRS weights lookup table with ICD-9 and ICD-10 mappings
WITH hfrs_weights AS (
    -- ICD-10 codes with weights (original HFRS - 109 codes)
    SELECT 'F00' AS icd_code, 10 AS icd_version, 7.1 AS weight UNION ALL
    SELECT 'G81', 10, 4.4 UNION ALL
    SELECT 'G30', 10, 4.0 UNION ALL
    SELECT 'I69', 10, 3.7 UNION ALL
    SELECT 'R29', 10, 3.6 UNION ALL
    SELECT 'N39', 10, 3.2 UNION ALL
    SELECT 'F05', 10, 3.2 UNION ALL
    SELECT 'W19', 10, 3.2 UNION ALL
    SELECT 'S00', 10, 3.2 UNION ALL
    SELECT 'R31', 10, 3.0 UNION ALL
    SELECT 'B96', 10, 2.9 UNION ALL
    SELECT 'R41', 10, 2.7 UNION ALL
    SELECT 'R26', 10, 2.6 UNION ALL
    SELECT 'I67', 10, 2.6 UNION ALL
    SELECT 'R56', 10, 2.6 UNION ALL
    SELECT 'R40', 10, 2.5 UNION ALL
    SELECT 'T83', 10, 2.4 UNION ALL
    SELECT 'S06', 10, 2.4 UNION ALL
    SELECT 'S42', 10, 2.3 UNION ALL
    SELECT 'E87', 10, 2.3 UNION ALL
    SELECT 'M25', 10, 2.3 UNION ALL
    SELECT 'E86', 10, 2.3 UNION ALL
    SELECT 'R54', 10, 2.2 UNION ALL
    SELECT 'Z50', 10, 2.1 UNION ALL
    SELECT 'F03', 10, 2.1 UNION ALL
    SELECT 'W18', 10, 2.1 UNION ALL
    SELECT 'Z75', 10, 2.0 UNION ALL
    SELECT 'F01', 10, 2.0 UNION ALL
    SELECT 'S80', 10, 2.0 UNION ALL
    SELECT 'L03', 10, 2.0 UNION ALL
    SELECT 'H54', 10, 1.9 UNION ALL
    SELECT 'E53', 10, 1.9 UNION ALL
    SELECT 'Z60', 10, 1.8 UNION ALL
    SELECT 'G20', 10, 1.8 UNION ALL
    SELECT 'R55', 10, 1.8 UNION ALL
    SELECT 'S22', 10, 1.8 UNION ALL
    SELECT 'K59', 10, 1.8 UNION ALL
    SELECT 'N17', 10, 1.8 UNION ALL
    SELECT 'L89', 10, 1.7 UNION ALL
    SELECT 'Z22', 10, 1.7 UNION ALL
    SELECT 'B95', 10, 1.7 UNION ALL
    SELECT 'L97', 10, 1.6 UNION ALL
    SELECT 'R44', 10, 1.6 UNION ALL
    SELECT 'K26', 10, 1.6 UNION ALL
    SELECT 'I95', 10, 1.6 UNION ALL
    SELECT 'N19', 10, 1.6 UNION ALL
    SELECT 'A41', 10, 1.6 UNION ALL
    SELECT 'Z87', 10, 1.5 UNION ALL
    SELECT 'J96', 10, 1.5 UNION ALL
    SELECT 'X59', 10, 1.5 UNION ALL
    SELECT 'M19', 10, 1.5 UNION ALL
    SELECT 'G40', 10, 1.5 UNION ALL
    SELECT 'M81', 10, 1.4 UNION ALL
    SELECT 'S72', 10, 1.4 UNION ALL
    SELECT 'S32', 10, 1.4 UNION ALL
    SELECT 'E16', 10, 1.4 UNION ALL
    SELECT 'R94', 10, 1.4 UNION ALL
    SELECT 'N18', 10, 1.4 UNION ALL
    SELECT 'R33', 10, 1.3 UNION ALL
    SELECT 'R69', 10, 1.3 UNION ALL
    SELECT 'N28', 10, 1.3 UNION ALL
    SELECT 'R32', 10, 1.2 UNION ALL
    SELECT 'G31', 10, 1.2 UNION ALL
    SELECT 'Y95', 10, 1.2 UNION ALL
    SELECT 'S09', 10, 1.2 UNION ALL
    SELECT 'R45', 10, 1.2 UNION ALL
    SELECT 'G45', 10, 1.2 UNION ALL
    SELECT 'Z74', 10, 1.1 UNION ALL
    SELECT 'M79', 10, 1.1 UNION ALL
    SELECT 'W06', 10, 1.1 UNION ALL
    SELECT 'S01', 10, 1.1 UNION ALL
    SELECT 'A04', 10, 1.1 UNION ALL
    SELECT 'A09', 10, 1.1 UNION ALL
    SELECT 'J18', 10, 1.1 UNION ALL
    SELECT 'J69', 10, 1.0 UNION ALL
    SELECT 'R47', 10, 1.0 UNION ALL
    SELECT 'E55', 10, 1.0 UNION ALL
    SELECT 'Z93', 10, 1.0 UNION ALL
    SELECT 'R02', 10, 1.0 UNION ALL
    SELECT 'R63', 10, 0.9 UNION ALL
    SELECT 'H91', 10, 0.9 UNION ALL
    SELECT 'W10', 10, 0.9 UNION ALL
    SELECT 'W01', 10, 0.9 UNION ALL
    SELECT 'E05', 10, 0.9 UNION ALL
    SELECT 'M41', 10, 0.9 UNION ALL
    SELECT 'R13', 10, 0.8 UNION ALL
    SELECT 'Z99', 10, 0.8 UNION ALL
    SELECT 'U80', 10, 0.8 UNION ALL
    SELECT 'M80', 10, 0.8 UNION ALL
    SELECT 'K92', 10, 0.8 UNION ALL
    SELECT 'I63', 10, 0.8 UNION ALL
    SELECT 'N20', 10, 0.7 UNION ALL
    SELECT 'F10', 10, 0.7 UNION ALL
    SELECT 'Y84', 10, 0.7 UNION ALL
    SELECT 'R00', 10, 0.7 UNION ALL
    SELECT 'J22', 10, 0.7 UNION ALL
    SELECT 'Z73', 10, 0.6 UNION ALL
    SELECT 'R79', 10, 0.6 UNION ALL
    SELECT 'Z91', 10, 0.5 UNION ALL
    SELECT 'S51', 10, 0.5 UNION ALL
    SELECT 'F32', 10, 0.5 UNION ALL
    SELECT 'M48', 10, 0.5 UNION ALL
    SELECT 'E83', 10, 0.4 UNION ALL
    SELECT 'M15', 10, 0.4 UNION ALL
    SELECT 'D64', 10, 0.4 UNION ALL
    SELECT 'L08', 10, 0.4 UNION ALL
    SELECT 'R11', 10, 0.3 UNION ALL
    SELECT 'K52', 10, 0.3 UNION ALL
    SELECT 'R50', 10, 0.1 UNION ALL

    -- ICD-9 codes mapped to HFRS weights (added for MIMIC-IV compatibility)
    -- Note: ICD-9 mapping is NOT part of the original Gilbert et al. publication
    -- Dementia in Alzheimer's (F00 -> 290.0-290.3)
    SELECT '2900', 9, 7.1 UNION ALL SELECT '2901', 9, 7.1 UNION ALL
    SELECT '2902', 9, 7.1 UNION ALL SELECT '2903', 9, 7.1 UNION ALL
    -- Hemiplegia (G81 -> 342.x)
    SELECT '3420', 9, 4.4 UNION ALL SELECT '3421', 9, 4.4 UNION ALL
    SELECT '3428', 9, 4.4 UNION ALL SELECT '3429', 9, 4.4 UNION ALL
    -- Alzheimer's (G30 -> 331.0)
    SELECT '3310', 9, 4.0 UNION ALL
    -- Sequelae of CVD (I69 -> 438.x)
    SELECT '4380', 9, 3.7 UNION ALL SELECT '4381', 9, 3.7 UNION ALL
    SELECT '4382', 9, 3.7 UNION ALL SELECT '4383', 9, 3.7 UNION ALL
    SELECT '4384', 9, 3.7 UNION ALL SELECT '4385', 9, 3.7 UNION ALL
    SELECT '4388', 9, 3.7 UNION ALL SELECT '4389', 9, 3.7 UNION ALL
    -- Nervous/musculoskeletal symptoms (R29 -> 781.x)
    SELECT '7812', 9, 3.6 UNION ALL SELECT '7813', 9, 3.6 UNION ALL SELECT '7819', 9, 3.6 UNION ALL
    -- UTI/Urinary disorders (N39 -> 599.x, 788.3)
    SELECT '5990', 9, 3.2 UNION ALL SELECT '5997', 9, 3.2 UNION ALL SELECT '7883', 9, 3.2 UNION ALL
    -- Delirium (F05 -> 293.x)
    SELECT '2930', 9, 3.2 UNION ALL SELECT '2931', 9, 3.2 UNION ALL
    -- Falls (W19 -> E888.9)
    SELECT 'E8889', 9, 3.2 UNION ALL
    -- Superficial head injury (S00 -> 920)
    SELECT '920', 9, 3.2 UNION ALL
    -- Bacterial agents (B96 -> 041.x)
    SELECT '0414', 9, 2.9 UNION ALL SELECT '0418', 9, 2.9 UNION ALL SELECT '0419', 9, 2.9 UNION ALL
    -- Cognitive symptoms (R41 -> 780.9x)
    SELECT '78093', 9, 2.7 UNION ALL SELECT '78097', 9, 2.7 UNION ALL
    -- Cerebrovascular disease (I67 -> 437.x)
    SELECT '4370', 9, 2.6 UNION ALL SELECT '4371', 9, 2.6 UNION ALL
    SELECT '4378', 9, 2.6 UNION ALL SELECT '4379', 9, 2.6 UNION ALL
    -- Convulsions (R56 -> 780.39)
    SELECT '78039', 9, 2.6 UNION ALL
    -- Somnolence/coma (R40 -> 780.0x)
    SELECT '78001', 9, 2.5 UNION ALL SELECT '78002', 9, 2.5 UNION ALL
    SELECT '78003', 9, 2.5 UNION ALL SELECT '78009', 9, 2.5 UNION ALL
    -- GU device complications (T83 -> 996.x)
    SELECT '9963', 9, 2.4 UNION ALL SELECT '9966', 9, 2.4 UNION ALL
    -- Intracranial injury (S06 -> 850-854)
    SELECT '850', 9, 2.4 UNION ALL SELECT '851', 9, 2.4 UNION ALL
    SELECT '852', 9, 2.4 UNION ALL SELECT '853', 9, 2.4 UNION ALL SELECT '854', 9, 2.4 UNION ALL
    -- Shoulder/arm fracture (S42 -> 810, 812)
    SELECT '810', 9, 2.3 UNION ALL SELECT '812', 9, 2.3 UNION ALL
    -- Fluid/electrolyte (E87 -> 276.x)
    SELECT '2760', 9, 2.3 UNION ALL SELECT '2761', 9, 2.3 UNION ALL
    SELECT '2762', 9, 2.3 UNION ALL SELECT '2763', 9, 2.3 UNION ALL
    SELECT '2764', 9, 2.3 UNION ALL SELECT '2765', 9, 2.3 UNION ALL
    SELECT '2766', 9, 2.3 UNION ALL SELECT '2767', 9, 2.3 UNION ALL
    SELECT '2768', 9, 2.3 UNION ALL SELECT '2769', 9, 2.3 UNION ALL
    -- Joint disorders (M25 -> 719.x)
    SELECT '7190', 9, 2.3 UNION ALL SELECT '7194', 9, 2.3 UNION ALL
    SELECT '7195', 9, 2.3 UNION ALL SELECT '7196', 9, 2.3 UNION ALL
    SELECT '7198', 9, 2.3 UNION ALL SELECT '7199', 9, 2.3 UNION ALL
    -- Senility (R54 -> 797)
    SELECT '797', 9, 2.2 UNION ALL
    -- Rehabilitation (Z50 -> V57)
    SELECT 'V57', 9, 2.1 UNION ALL
    -- Unspecified dementia (F03 -> 294.x)
    SELECT '2942', 9, 2.1 UNION ALL SELECT '2948', 9, 2.1 UNION ALL
    -- Fall same level (W18 -> E888.1)
    SELECT 'E8881', 9, 2.1 UNION ALL
    -- Medical facility problems (Z75 -> V63)
    SELECT 'V63', 9, 2.0 UNION ALL
    -- Vascular dementia (F01 -> 290.4)
    SELECT '2904', 9, 2.0 UNION ALL
    -- Superficial leg injury (S80 -> 916)
    SELECT '916', 9, 2.0 UNION ALL
    -- Cellulitis (L03 -> 681, 682)
    SELECT '681', 9, 2.0 UNION ALL SELECT '682', 9, 2.0 UNION ALL
    -- Blindness (H54 -> 369)
    SELECT '369', 9, 1.9 UNION ALL
    -- B vitamin deficiency (E53 -> 266)
    SELECT '266', 9, 1.9 UNION ALL
    -- Social environment (Z60 -> V62.x)
    SELECT 'V624', 9, 1.8 UNION ALL SELECT 'V628', 9, 1.8 UNION ALL
    -- Parkinson's (G20 -> 332.0)
    SELECT '3320', 9, 1.8 UNION ALL
    -- Syncope (R55 -> 780.2)
    SELECT '7802', 9, 1.8 UNION ALL
    -- Rib/spine fracture (S22 -> 807, 805.x)
    SELECT '807', 9, 1.8 UNION ALL SELECT '8052', 9, 1.8 UNION ALL SELECT '8053', 9, 1.8 UNION ALL
    -- Intestinal disorders (K59 -> 564.x)
    SELECT '5640', 9, 1.8 UNION ALL SELECT '5641', 9, 1.8 UNION ALL
    SELECT '5648', 9, 1.8 UNION ALL SELECT '5649', 9, 1.8 UNION ALL
    -- Acute renal failure (N17 -> 584)
    SELECT '584', 9, 1.8 UNION ALL
    -- Pressure ulcer (L89 -> 707.0)
    SELECT '7070', 9, 1.7 UNION ALL
    -- Infectious carrier (Z22 -> V02)
    SELECT 'V02', 9, 1.7 UNION ALL
    -- Strep/staph (B95 -> 041.0, 041.1)
    SELECT '0410', 9, 1.7 UNION ALL SELECT '0411', 9, 1.7 UNION ALL
    -- Lower limb ulcer (L97 -> 707.1)
    SELECT '7071', 9, 1.6 UNION ALL
    -- General sensations (R44 -> 780.1)
    SELECT '7801', 9, 1.6 UNION ALL
    -- Duodenal ulcer (K26 -> 532)
    SELECT '532', 9, 1.6 UNION ALL
    -- Hypotension (I95 -> 458)
    SELECT '458', 9, 1.6 UNION ALL
    -- Renal failure unspecified (N19 -> 586)
    SELECT '586', 9, 1.6 UNION ALL
    -- Septicemia (A41 -> 038)
    SELECT '038', 9, 1.6 UNION ALL
    -- Personal history (Z87 -> V12, V13)
    SELECT 'V12', 9, 1.5 UNION ALL SELECT 'V13', 9, 1.5 UNION ALL
    -- Respiratory failure (J96 -> 518.8x)
    SELECT '51881', 9, 1.5 UNION ALL SELECT '51883', 9, 1.5 UNION ALL SELECT '51884', 9, 1.5 UNION ALL
    -- Unspecified factor (X59 -> E928.9)
    SELECT 'E9289', 9, 1.5 UNION ALL
    -- Arthrosis (M19 -> 715.9)
    SELECT '7159', 9, 1.5 UNION ALL
    -- Epilepsy (G40 -> 345)
    SELECT '345', 9, 1.5 UNION ALL
    -- Osteoporosis (M81 -> 733.0)
    SELECT '7330', 9, 1.4 UNION ALL
    -- Femur fracture (S72 -> 820, 821)
    SELECT '820', 9, 1.4 UNION ALL SELECT '821', 9, 1.4 UNION ALL
    -- Lumbar/pelvis fracture (S32 -> 805.4, 805.5, 808)
    SELECT '8054', 9, 1.4 UNION ALL SELECT '8055', 9, 1.4 UNION ALL SELECT '808', 9, 1.4 UNION ALL
    -- Pancreatic secretion (E16 -> 251)
    SELECT '251', 9, 1.4 UNION ALL
    -- Function study abnormal (R94 -> 794)
    SELECT '794', 9, 1.4 UNION ALL
    -- Chronic renal failure (N18 -> 585)
    SELECT '585', 9, 1.4 UNION ALL
    -- Urine retention (R33 -> 788.2)
    SELECT '7882', 9, 1.3 UNION ALL
    -- Unknown morbidity (R69 -> 799.9)
    SELECT '7999', 9, 1.3 UNION ALL
    -- Kidney/ureter disorders (N28 -> 593)
    SELECT '593', 9, 1.3 UNION ALL
    -- Degenerative nervous system (G31 -> 331.x)
    SELECT '3311', 9, 1.2 UNION ALL SELECT '3312', 9, 1.2 UNION ALL
    SELECT '3317', 9, 1.2 UNION ALL SELECT '3318', 9, 1.2 UNION ALL SELECT '3319', 9, 1.2 UNION ALL
    -- Nosocomial (Y95 -> E879.8)
    SELECT 'E8798', 9, 1.2 UNION ALL
    -- Head injuries (S09 -> 959.01)
    SELECT '95901', 9, 1.2 UNION ALL
    -- Emotional state (R45 -> 799.2)
    SELECT '7992', 9, 1.2 UNION ALL
    -- TIA (G45 -> 435)
    SELECT '435', 9, 1.2 UNION ALL
    -- Care dependency (Z74 -> V60.4)
    SELECT 'V604', 9, 1.1 UNION ALL
    -- Soft tissue (M79 -> 729)
    SELECT '729', 9, 1.1 UNION ALL
    -- Fall from bed (W06 -> E884.4)
    SELECT 'E8844', 9, 1.1 UNION ALL
    -- Open head wound (S01 -> 873)
    SELECT '873', 9, 1.1 UNION ALL
    -- Bacterial intestinal (A04 -> 008.x)
    SELECT '0084', 9, 1.1 UNION ALL SELECT '0085', 9, 1.1 UNION ALL
    -- Diarrhoea (A09 -> 009.x)
    SELECT '0090', 9, 1.1 UNION ALL SELECT '0091', 9, 1.1 UNION ALL
    SELECT '0092', 9, 1.1 UNION ALL SELECT '0093', 9, 1.1 UNION ALL
    -- Pneumonia (J18 -> 486)
    SELECT '486', 9, 1.1 UNION ALL
    -- Aspiration pneumonia (J69 -> 507)
    SELECT '507', 9, 1.0 UNION ALL
    -- Speech disturbance (R47 -> 784.5)
    SELECT '7845', 9, 1.0 UNION ALL
    -- Vitamin D deficiency (E55 -> 268)
    SELECT '268', 9, 1.0 UNION ALL
    -- Artificial opening (Z93 -> V44)
    SELECT 'V44', 9, 1.0 UNION ALL
    -- Gangrene (R02 -> 785.4)
    SELECT '7854', 9, 1.0 UNION ALL
    -- Food/fluid symptoms (R63 -> 783.x)
    SELECT '7830', 9, 0.9 UNION ALL SELECT '7833', 9, 0.9 UNION ALL
    -- Hearing loss (H91 -> 389)
    SELECT '389', 9, 0.9 UNION ALL
    -- Fall from stairs (W10 -> E880.9)
    SELECT 'E8809', 9, 0.9 UNION ALL
    -- Fall slipping (W01 -> E885.9)
    SELECT 'E8859', 9, 0.9 UNION ALL
    -- Thyrotoxicosis (E05 -> 242)
    SELECT '242', 9, 0.9 UNION ALL
    -- Scoliosis (M41 -> 737.3)
    SELECT '7373', 9, 0.9 UNION ALL
    -- Dysphagia (R13 -> 787.2)
    SELECT '7872', 9, 0.8 UNION ALL
    -- Machine dependence (Z99 -> V46)
    SELECT 'V46', 9, 0.8 UNION ALL
    -- Antibiotic resistance (U80 -> V09.0)
    SELECT 'V090', 9, 0.8 UNION ALL
    -- Osteoporosis with fracture (M80 -> 733.1)
    SELECT '7331', 9, 0.8 UNION ALL
    -- Digestive system (K92 -> 578)
    SELECT '578', 9, 0.8 UNION ALL
    -- Cerebral infarction (I63 -> 434.91)
    SELECT '43491', 9, 0.8 UNION ALL
    -- Kidney stone (N20 -> 592)
    SELECT '592', 9, 0.7 UNION ALL
    -- Alcohol disorders (F10 -> 303, 305.0)
    SELECT '303', 9, 0.7 UNION ALL SELECT '3050', 9, 0.7 UNION ALL
    -- Medical procedures (Y84 -> E879)
    SELECT 'E879', 9, 0.7 UNION ALL
    -- Heart beat abnormal (R00 -> 785.0, 785.1)
    SELECT '7850', 9, 0.7 UNION ALL SELECT '7851', 9, 0.7 UNION ALL
    -- Lower respiratory infection (J22 -> 519.8)
    SELECT '5198', 9, 0.7 UNION ALL
    -- Life management (Z73 -> V62.89)
    SELECT 'V6289', 9, 0.6 UNION ALL
    -- Blood chemistry (R79 -> 790.6)
    SELECT '7906', 9, 0.6 UNION ALL
    -- Risk factors (Z91 -> V15)
    SELECT 'V15', 9, 0.5 UNION ALL
    -- Forearm wound (S51 -> 881)
    SELECT '881', 9, 0.5 UNION ALL
    -- Depression (F32 -> 296.2, 311)
    SELECT '2962', 9, 0.5 UNION ALL SELECT '311', 9, 0.5 UNION ALL
    -- Spinal stenosis (M48 -> 724.0)
    SELECT '7240', 9, 0.5 UNION ALL
    -- Mineral metabolism (E83 -> 275)
    SELECT '275', 9, 0.4 UNION ALL
    -- Polyarthrosis (M15 -> 715.0)
    SELECT '7150', 9, 0.4 UNION ALL
    -- Anaemia (D64 -> 285)
    SELECT '285', 9, 0.4 UNION ALL
    -- Skin infections (L08 -> 686)
    SELECT '686', 9, 0.4 UNION ALL
    -- Nausea/vomiting (R11 -> 787.0)
    SELECT '7870', 9, 0.3 UNION ALL
    -- Noninfective gastroenteritis (K52 -> 558)
    SELECT '558', 9, 0.3 UNION ALL
    -- Fever (R50 -> 780.6)
    SELECT '7806', 9, 0.1
),

-- Step 2: Get index admissions (the admissions we want to calculate HFRS for)
index_admissions AS (
    SELECT
        subject_id,
        hadm_id,
        admittime
    FROM mimiciv_hosp.admissions
    -- Optional: Filter by specific patient or admission
    -- WHERE subject_id = {subject_id}
    -- WHERE hadm_id = {hadm_id}
),

-- Step 3: Identify eligible prior admissions (emergency admissions within 2 years)
-- Per Gilbert et al.: "current admission and any previous emergency admissions
-- occurring in the preceding 2 years"
eligible_admissions AS (
    SELECT
        idx.subject_id,
        idx.hadm_id AS index_hadm_id,
        idx.admittime AS index_admittime,
        prior.hadm_id AS source_hadm_id,
        'prior_emergency' AS source_type
    FROM index_admissions idx
    INNER JOIN mimiciv_hosp.admissions prior
        ON idx.subject_id = prior.subject_id
        AND prior.admittime < idx.admittime
        AND prior.admittime >= idx.admittime - INTERVAL '2 years'
        -- MIMIC-IV admission_type values that correspond to emergency admissions:
        -- 'EMERGENCY', 'URGENT', 'EW EMER.' (Emergency Ward)
        AND prior.admission_type IN ('EMERGENCY', 'URGENT', 'EW EMER.')

    UNION ALL

    -- Include the current (index) admission itself
    SELECT
        subject_id,
        hadm_id AS index_hadm_id,
        admittime AS index_admittime,
        hadm_id AS source_hadm_id,
        'current' AS source_type
    FROM index_admissions
),

-- Step 4: Get all diagnoses from eligible admissions
patient_diagnoses AS (
    SELECT DISTINCT
        ea.subject_id,
        ea.index_hadm_id,
        -- Standardize ICD code: remove dots and uppercase
        UPPER(REPLACE(d.icd_code, '.', '')) AS icd_code_clean,
        d.icd_version
    FROM eligible_admissions ea
    INNER JOIN mimiciv_hosp.diagnoses_icd d
        ON ea.source_hadm_id = d.hadm_id
),

-- Step 5: Match diagnoses to HFRS weights
matched_diagnoses AS (
    SELECT
        pd.subject_id,
        pd.index_hadm_id,
        pd.icd_code_clean,
        pd.icd_version,
        hw.weight,
        hw.icd_code AS matched_code
    FROM patient_diagnoses pd
    INNER JOIN hfrs_weights hw
        ON pd.icd_version = hw.icd_version
        AND (
            -- Exact match
            pd.icd_code_clean = hw.icd_code
            -- Or prefix match (first 3 characters for ICD-10, varies for ICD-9)
            OR (pd.icd_version = 10 AND LEFT(pd.icd_code_clean, 3) = hw.icd_code)
            OR (pd.icd_version = 9 AND LEFT(pd.icd_code_clean, LENGTH(hw.icd_code)) = hw.icd_code)
        )
),

-- Step 6: Aggregate scores per index admission
-- Each unique HFRS code is counted only once, even if it appears in multiple admissions
hfrs_scores AS (
    SELECT
        subject_id,
        index_hadm_id AS hadm_id,
        ROUND(SUM(DISTINCT weight)::numeric, 1) AS hfrs_score,
        COUNT(DISTINCT matched_code) AS num_frailty_codes
    FROM matched_diagnoses
    GROUP BY subject_id, index_hadm_id
)

-- Final output: HFRS with risk category for each admission
SELECT
    h.subject_id,
    h.hadm_id,
    h.hfrs_score,
    h.num_frailty_codes,
    CASE
        WHEN h.hfrs_score < 5 THEN 'Low'
        WHEN h.hfrs_score >= 5 AND h.hfrs_score < 15 THEN 'Intermediate'
        ELSE 'High'
    END AS risk_category,
    CASE
        WHEN h.hfrs_score < 5 THEN 1
        WHEN h.hfrs_score >= 5 AND h.hfrs_score < 15 THEN 2
        ELSE 3
    END AS risk_level
FROM hfrs_scores h
ORDER BY h.hfrs_score DESC;
