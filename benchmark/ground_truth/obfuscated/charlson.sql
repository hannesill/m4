-- ------------------------------------------------------------------
-- Title: Charlson Comorbidity Index
-- Calculates the Charlson Comorbidity Index (CCI) for each hospital
-- admission using ICD-9 and ICD-10 diagnosis codes. Includes 17
-- comorbidity conditions with original Charlson weights and age score.
-- ------------------------------------------------------------------

-- Reference:
--    Charlson ME et al. "A new method of classifying prognostic
--    comorbidity in longitudinal studies." J Chronic Dis. 1987;40(5):373-83.

-- ICD mapping reference:
--    Quan H et al. "Coding algorithms for defining comorbidities in
--    ICD-9-CM and ICD-10 administrative data." Med Care. 2005;43(11):1130-9.

-- Adapted from mimic-code charlson.sql

WITH diag AS (
  SELECT
    c_263,
    CASE WHEN c_291 = 9 THEN c_290 ELSE NULL END AS icd9_code,
    CASE WHEN c_291 = 10 THEN c_290 ELSE NULL END AS icd10_code
  FROM ds_2.t_006
), com AS (
  SELECT
    ad.c_263,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) IN ('410', '412')
        OR SUBSTR(icd10_code, 1, 3) IN ('I21', 'I22')
        OR SUBSTR(icd10_code, 1, 4) = 'I252'
        THEN 1
        ELSE 0
      END
    ) AS c_376,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) = '428'
        OR SUBSTR(icd9_code, 1, 5) IN ('39891', '40201', '40211', '40291', '40401', '40403', '40411', '40413', '40491', '40493')
        OR SUBSTR(icd9_code, 1, 4) BETWEEN '4254' AND '4259'
        OR SUBSTR(icd10_code, 1, 3) IN ('I43', 'I50')
        OR SUBSTR(icd10_code, 1, 4) IN ('I099', 'I110', 'I130', 'I132', 'I255', 'I420', 'I425', 'I426', 'I427', 'I428', 'I429', 'P290')
        THEN 1
        ELSE 0
      END
    ) AS c_139,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) IN ('440', '441')
        OR SUBSTR(icd9_code, 1, 4) IN ('0930', '4373', '4471', '5571', '5579', 'V434')
        OR SUBSTR(icd9_code, 1, 4) BETWEEN '4431' AND '4439'
        OR SUBSTR(icd10_code, 1, 3) IN ('I70', 'I71')
        OR SUBSTR(icd10_code, 1, 4) IN ('I731', 'I738', 'I739', 'I771', 'I790', 'I792', 'K551', 'K558', 'K559', 'Z958', 'Z959')
        THEN 1
        ELSE 0
      END
    ) AS c_430,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) BETWEEN '430' AND '438'
        OR SUBSTR(icd9_code, 1, 5) = '36234'
        OR SUBSTR(icd10_code, 1, 3) IN ('G45', 'G46')
        OR SUBSTR(icd10_code, 1, 3) BETWEEN 'I60' AND 'I69'
        OR SUBSTR(icd10_code, 1, 4) = 'H340'
        THEN 1
        ELSE 0
      END
    ) AS c_111,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) = '290'
        OR SUBSTR(icd9_code, 1, 4) IN ('2941', '3312')
        OR SUBSTR(icd10_code, 1, 3) IN ('F00', 'F01', 'F02', 'F03', 'G30')
        OR SUBSTR(icd10_code, 1, 4) IN ('F051', 'G311')
        THEN 1
        ELSE 0
      END
    ) AS c_163,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) BETWEEN '490' AND '505'
        OR SUBSTR(icd9_code, 1, 4) IN ('4168', '4169', '5064', '5081', '5088')
        OR SUBSTR(icd10_code, 1, 3) BETWEEN 'J40' AND 'J47'
        OR SUBSTR(icd10_code, 1, 3) BETWEEN 'J60' AND 'J67'
        OR SUBSTR(icd10_code, 1, 4) IN ('I278', 'I279', 'J684', 'J701', 'J703')
        THEN 1
        ELSE 0
      END
    ) AS c_118,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) = '725'
        OR SUBSTR(icd9_code, 1, 4) IN ('4465', '7100', '7101', '7102', '7103', '7104', '7140', '7141', '7142', '7148')
        OR SUBSTR(icd10_code, 1, 3) IN ('M05', 'M06', 'M32', 'M33', 'M34')
        OR SUBSTR(icd10_code, 1, 4) IN ('M315', 'M351', 'M353', 'M360')
        THEN 1
        ELSE 0
      END
    ) AS c_508,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) IN ('531', '532', '533', '534')
        OR SUBSTR(icd10_code, 1, 3) IN ('K25', 'K26', 'K27', 'K28')
        THEN 1
        ELSE 0
      END
    ) AS c_429,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) IN ('570', '571')
        OR SUBSTR(icd9_code, 1, 4) IN ('0706', '0709', '5733', '5734', '5738', '5739', 'V427')
        OR SUBSTR(icd9_code, 1, 5) IN ('07022', '07023', '07032', '07033', '07044', '07054')
        OR SUBSTR(icd10_code, 1, 3) IN ('B18', 'K73', 'K74')
        OR SUBSTR(icd10_code, 1, 4) IN ('K700', 'K701', 'K702', 'K703', 'K709', 'K713', 'K714', 'K715', 'K717', 'K760', 'K762', 'K763', 'K764', 'K768', 'K769', 'Z944')
        THEN 1
        ELSE 0
      END
    ) AS c_371,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 4) IN ('2500', '2501', '2502', '2503', '2508', '2509')
        OR SUBSTR(icd10_code, 1, 4) IN ('E100', 'E101', 'E106', 'E108', 'E109', 'E110', 'E111', 'E116', 'E118', 'E119', 'E120', 'E121', 'E126', 'E128', 'E129', 'E130', 'E131', 'E136', 'E138', 'E139', 'E140', 'E141', 'E146', 'E148', 'E149')
        THEN 1
        ELSE 0
      END
    ) AS c_166,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 4) IN ('2504', '2505', '2506', '2507')
        OR SUBSTR(icd10_code, 1, 4) IN ('E102', 'E103', 'E104', 'E105', 'E107', 'E112', 'E113', 'E114', 'E115', 'E117', 'E122', 'E123', 'E124', 'E125', 'E127', 'E132', 'E133', 'E134', 'E135', 'E137', 'E142', 'E143', 'E144', 'E145', 'E147')
        THEN 1
        ELSE 0
      END
    ) AS c_165,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) IN ('342', '343')
        OR SUBSTR(icd9_code, 1, 4) IN ('3341', '3440', '3441', '3442', '3443', '3444', '3445', '3446', '3449')
        OR SUBSTR(icd10_code, 1, 3) IN ('G81', 'G82')
        OR SUBSTR(icd10_code, 1, 4) IN ('G041', 'G114', 'G801', 'G802', 'G830', 'G831', 'G832', 'G833', 'G834', 'G839')
        THEN 1
        ELSE 0
      END
    ) AS c_422,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) IN ('582', '585', '586', 'V56')
        OR SUBSTR(icd9_code, 1, 4) IN ('5880', 'V420', 'V451')
        OR SUBSTR(icd9_code, 1, 4) BETWEEN '5830' AND '5837'
        OR SUBSTR(icd9_code, 1, 5) IN ('40301', '40311', '40391', '40402', '40403', '40412', '40413', '40492', '40493')
        OR SUBSTR(icd10_code, 1, 3) IN ('N18', 'N19')
        OR SUBSTR(icd10_code, 1, 4) IN ('I120', 'I131', 'N032', 'N033', 'N034', 'N035', 'N036', 'N037', 'N052', 'N053', 'N054', 'N055', 'N056', 'N057', 'N250', 'Z490', 'Z491', 'Z492', 'Z940', 'Z992')
        THEN 1
        ELSE 0
      END
    ) AS c_489,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) BETWEEN '140' AND '172'
        OR SUBSTR(icd9_code, 1, 4) BETWEEN '1740' AND '1958'
        OR SUBSTR(icd9_code, 1, 3) BETWEEN '200' AND '208'
        OR SUBSTR(icd9_code, 1, 4) = '2386'
        OR SUBSTR(icd10_code, 1, 3) IN ('C43', 'C88')
        OR SUBSTR(icd10_code, 1, 3) BETWEEN 'C00' AND 'C26'
        OR SUBSTR(icd10_code, 1, 3) BETWEEN 'C30' AND 'C34'
        OR SUBSTR(icd10_code, 1, 3) BETWEEN 'C37' AND 'C41'
        OR SUBSTR(icd10_code, 1, 3) BETWEEN 'C45' AND 'C58'
        OR SUBSTR(icd10_code, 1, 3) BETWEEN 'C60' AND 'C76'
        OR SUBSTR(icd10_code, 1, 3) BETWEEN 'C81' AND 'C85'
        OR SUBSTR(icd10_code, 1, 3) BETWEEN 'C90' AND 'C97'
        THEN 1
        ELSE 0
      END
    ) AS c_343,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 4) IN ('4560', '4561', '4562')
        OR SUBSTR(icd9_code, 1, 4) BETWEEN '5722' AND '5728'
        OR SUBSTR(icd10_code, 1, 4) IN ('I850', 'I859', 'I864', 'I982', 'K704', 'K711', 'K721', 'K729', 'K765', 'K766', 'K767')
        THEN 1
        ELSE 0
      END
    ) AS c_524,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) IN ('196', '197', '198', '199')
        OR SUBSTR(icd10_code, 1, 3) IN ('C77', 'C78', 'C79', 'C80')
        THEN 1
        ELSE 0
      END
    ) AS c_365,
    MAX(
      CASE
        WHEN SUBSTR(icd9_code, 1, 3) IN ('042', '043', '044')
        OR SUBSTR(icd10_code, 1, 3) IN ('B20', 'B21', 'B22', 'B24')
        THEN 1
        ELSE 0
      END
    ) AS c_033
  FROM ds_2.t_001 AS ad
  LEFT JOIN diag
    ON ad.c_263 = diag.c_263
  GROUP BY
    ad.c_263
), ag AS (
  SELECT
    c_263,
    c_031,
    CASE
      WHEN c_031 <= 50
      THEN 0
      WHEN c_031 <= 60
      THEN 1
      WHEN c_031 <= 70
      THEN 2
      WHEN c_031 <= 80
      THEN 3
      ELSE 4
    END AS c_032
  FROM ds_1.t_002
)
SELECT
  ad.c_556,
  ad.c_263,
  ag.c_032,
  c_376,
  c_139,
  c_430,
  c_111,
  c_163,
  c_118,
  c_508,
  c_429,
  c_371,
  c_166,
  c_165,
  c_422,
  c_489,
  c_343,
  c_524,
  c_365,
  c_033,
  c_032 + c_376 + c_139 + c_430 + c_111 + c_163 + c_118 + c_508 + c_429 + GREATEST(c_371, 3 * c_524) + GREATEST(2 * c_165, c_166) + GREATEST(2 * c_343, 6 * c_365) + 2 * c_422 + 2 * c_489 + 6 * c_033 AS c_112
FROM ds_2.t_001 AS ad
LEFT JOIN com
  ON ad.c_263 = com.c_263
LEFT JOIN ag
  ON com.c_263 = ag.c_263
