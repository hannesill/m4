-- Elixhauser Comorbidity Index for MIMIC-IV
-- Supports both ICD-9-CM and ICD-10-CM codes
-- Based on Quan et al. 2005: "Coding algorithms for defining comorbidities
-- in ICD-9-CM and ICD-10 administrative data." Medical Care 43(11):1130-1139.
-- https://www.ncbi.nlm.nih.gov/pubmed/16224307

-- This query derives 31 Elixhauser comorbidity categories from diagnoses_icd
-- Primary diagnosis (seq_num = 1) is excluded per Elixhauser methodology

WITH eliflg AS (
  SELECT
    hadm_id,
    seq_num,
    icd_code,
    icd_version,

    -- =============================================================
    -- 1. CONGESTIVE HEART FAILURE
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND icd_code IN ('39891','40201','40211','40291','40401','40403','40411','40413','40491','40493') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('4254','4255','4257','4258','4259') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('428') THEN 1
      -- ICD-10: I09.9, I11.0, I13.0, I13.2, I25.5, I42.0, I42.5-I42.9, I43.x, I50.x, P29.0
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('I099','I110','I130','I132','I255','I420','I425','I426','I427','I428','I429','P290') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I43','I50') THEN 1
      ELSE 0
    END AS chf,

    -- =============================================================
    -- 2. CARDIAC ARRHYTHMIAS
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND icd_code IN ('42613','42610','42612','99601','99604') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('4260','4267','4269','4270','4271','4272','4273','4274','4276','4278','4279','7850','V450','V533') THEN 1
      -- ICD-10: I44.1-I44.3, I45.6, I45.9, I47.x-I49.x, R00.0, R00.1, R00.8, T82.1, Z45.0, Z95.0
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('I441','I442','I443','I456','I459','R000','R001','R008','T821','Z450','Z950') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I47','I48','I49') THEN 1
      ELSE 0
    END AS arrhy,

    -- =============================================================
    -- 3. VALVULAR DISEASE
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('0932','7463','7464','7465','7466','V422','V433') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('394','395','396','397','424') THEN 1
      -- ICD-10: A52.0, I05.x-I08.x, I09.1, I09.8, I34.x-I39.x, Q23.0-Q23.3, Z95.2, Z95.4
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('A520','I091','I098','Q230','Q231','Q232','Q233','Z952','Z954') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I05','I06','I07','I08','I34','I35','I36','I37','I38','I39') THEN 1
      ELSE 0
    END AS valve,

    -- =============================================================
    -- 4. PULMONARY CIRCULATION DISORDERS
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('4150','4151','4170','4178','4179') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('416') THEN 1
      -- ICD-10: I26.x, I27.x, I28.0, I28.8, I28.9
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('I280','I288','I289') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I26','I27') THEN 1
      ELSE 0
    END AS pulmcirc,

    -- =============================================================
    -- 5. PERIPHERAL VASCULAR DISORDERS
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('0930','4373','4431','4432','4438','4439','4471','5571','5579','V434') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('440','441') THEN 1
      -- ICD-10: I70.x, I71.x, I73.1, I73.8, I73.9, I77.1, I79.0, I79.2, K55.1, K55.8, K55.9, Z95.8, Z95.9
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('I731','I738','I739','I771','I790','I792','K551','K558','K559','Z958','Z959') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I70','I71') THEN 1
      ELSE 0
    END AS perivasc,

    -- =============================================================
    -- 6. HYPERTENSION, UNCOMPLICATED
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('401') THEN 1
      -- ICD-10: I10.x
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I10') THEN 1
      ELSE 0
    END AS htn,

    -- =============================================================
    -- 7. HYPERTENSION, COMPLICATED
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('402','403','404','405') THEN 1
      -- ICD-10: I11.x-I13.x, I15.x
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I11','I12','I13','I15') THEN 1
      ELSE 0
    END AS htncx,

    -- =============================================================
    -- 8. PARALYSIS
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('3341','3440','3441','3442','3443','3444','3445','3446','3449') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('342','343') THEN 1
      -- ICD-10: G04.1, G11.4, G80.1, G80.2, G81.x, G82.x, G83.0-G83.4, G83.9
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('G041','G114','G801','G802','G830','G831','G832','G833','G834','G839') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('G81','G82') THEN 1
      ELSE 0
    END AS para,

    -- =============================================================
    -- 9. OTHER NEUROLOGICAL DISORDERS
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND icd_code IN ('33392') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('3319','3320','3321','3334','3335','3362','3481','3483','7803','7843') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('334','335','340','341','345') THEN 1
      -- ICD-10: G10.x-G13.x, G20.x-G22.x, G25.4, G25.5, G31.2, G31.8, G31.9, G32.x, G35.x-G37.x, G40.x, G41.x, G93.1, G93.4, R47.0, R56.x
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('G254','G255','G312','G318','G319','G931','G934','R470') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('G10','G11','G12','G13','G20','G21','G22','G32','G35','G36','G37','G40','G41','R56') THEN 1
      ELSE 0
    END AS neuro,

    -- =============================================================
    -- 10. CHRONIC PULMONARY DISEASE
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('4168','4169','5064','5081','5088') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('490','491','492','493','494','495','496','500','501','502','503','504','505') THEN 1
      -- ICD-10: I27.8, I27.9, J40.x-J47.x, J60.x-J67.x, J68.4, J70.1, J70.3
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('I278','I279','J684','J701','J703') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('J40','J41','J42','J43','J44','J45','J46','J47','J60','J61','J62','J63','J64','J65','J66','J67') THEN 1
      ELSE 0
    END AS chrnlung,

    -- =============================================================
    -- 11. DIABETES, UNCOMPLICATED
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2500','2501','2502','2503') THEN 1
      -- ICD-10: E10.0, E10.1, E10.9, E11.0, E11.1, E11.9, E12.0, E12.1, E12.9, E13.0, E13.1, E13.9, E14.0, E14.1, E14.9
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('E100','E101','E109','E110','E111','E119','E120','E121','E129','E130','E131','E139','E140','E141','E149') THEN 1
      ELSE 0
    END AS dm,

    -- =============================================================
    -- 12. DIABETES, COMPLICATED
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2504','2505','2506','2507','2508','2509') THEN 1
      -- ICD-10: E10.2-E10.8, E11.2-E11.8, E12.2-E12.8, E13.2-E13.8, E14.2-E14.8
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('E102','E103','E104','E105','E106','E107','E108') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('E112','E113','E114','E115','E116','E117','E118') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('E122','E123','E124','E125','E126','E127','E128') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('E132','E133','E134','E135','E136','E137','E138') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('E142','E143','E144','E145','E146','E147','E148') THEN 1
      ELSE 0
    END AS dmcx,

    -- =============================================================
    -- 13. HYPOTHYROIDISM
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2409','2461','2468') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('243','244') THEN 1
      -- ICD-10: E00.x-E03.x, E89.0
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('E890') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('E00','E01','E02','E03') THEN 1
      ELSE 0
    END AS hypothy,

    -- =============================================================
    -- 14. RENAL FAILURE
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND icd_code IN ('40301','40311','40391','40402','40403','40412','40413','40492','40493') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('5880','V420','V451') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('585','586','V56') THEN 1
      -- ICD-10: I12.0, I13.1, N18.x, N19.x, N25.0, Z49.0-Z49.2, Z94.0, Z99.2
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('I120','I131','N250','Z490','Z491','Z492','Z940','Z992') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('N18','N19') THEN 1
      ELSE 0
    END AS renlfail,

    -- =============================================================
    -- 15. LIVER DISEASE
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND icd_code IN ('07022','07023','07032','07033','07044','07054') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('0706','0709','4560','4561','4562','5722','5723','5724','5728','5733','5734','5738','5739','V427') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('570','571') THEN 1
      -- ICD-10: B18.x, I85.x, I86.4, I98.2, K70.x, K71.1, K71.3-K71.5, K71.7, K72.x-K74.x, K76.0, K76.2-K76.9, Z94.4
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('I864','I982','K711','K713','K714','K715','K717','K760','K762','K763','K764','K765','K766','K767','K768','K769','Z944') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('B18','I85','K70','K72','K73','K74') THEN 1
      ELSE 0
    END AS liver,

    -- =============================================================
    -- 16. PEPTIC ULCER DISEASE (excluding bleeding)
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('5317','5319','5327','5329','5337','5339','5347','5349') THEN 1
      -- ICD-10: K25.7, K25.9, K26.7, K26.9, K27.7, K27.9, K28.7, K28.9
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('K257','K259','K267','K269','K277','K279','K287','K289') THEN 1
      ELSE 0
    END AS ulcer,

    -- =============================================================
    -- 17. AIDS/HIV
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('042','043','044') THEN 1
      -- ICD-10: B20.x-B22.x, B24.x
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('B20','B21','B22','B24') THEN 1
      ELSE 0
    END AS aids,

    -- =============================================================
    -- 18. LYMPHOMA
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2030','2386') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('200','201','202') THEN 1
      -- ICD-10: C81.x-C85.x, C88.x, C96.x, C90.0, C90.2
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('C900','C902') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('C81','C82','C83','C84','C85','C88','C96') THEN 1
      ELSE 0
    END AS lymph,

    -- =============================================================
    -- 19. METASTATIC CANCER
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('196','197','198','199') THEN 1
      -- ICD-10: C77.x-C80.x
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('C77','C78','C79','C80') THEN 1
      ELSE 0
    END AS mets,

    -- =============================================================
    -- 20. SOLID TUMOR WITHOUT METASTASIS
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN (
        '140','141','142','143','144','145','146','147','148','149',
        '150','151','152','153','154','155','156','157','158','159',
        '160','161','162','163','164','165','166','167','168','169',
        '170','171','172','174','175','176','177','178','179',
        '180','181','182','183','184','185','186','187','188','189',
        '190','191','192','193','194','195'
      ) THEN 1
      -- ICD-10: C00.x-C26.x, C30.x-C34.x, C37.x-C41.x, C43.x, C45.x-C58.x, C60.x-C76.x, C97.x
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN (
        'C00','C01','C02','C03','C04','C05','C06','C07','C08','C09',
        'C10','C11','C12','C13','C14','C15','C16','C17','C18','C19',
        'C20','C21','C22','C23','C24','C25','C26',
        'C30','C31','C32','C33','C34',
        'C37','C38','C39','C40','C41','C43',
        'C45','C46','C47','C48','C49','C50','C51','C52','C53','C54','C55','C56','C57','C58',
        'C60','C61','C62','C63','C64','C65','C66','C67','C68','C69',
        'C70','C71','C72','C73','C74','C75','C76','C97'
      ) THEN 1
      ELSE 0
    END AS tumor,

    -- =============================================================
    -- 21. RHEUMATOID ARTHRITIS / COLLAGEN VASCULAR DISEASES
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND icd_code IN ('72889','72930') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('7010','7100','7101','7102','7103','7104','7108','7109','7112','7193','7285') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('446','714','720','725') THEN 1
      -- ICD-10: L94.0, L94.1, L94.3, M05.x, M06.x, M08.x, M12.0, M12.3, M30.x, M31.0-M31.3, M32.x-M35.x, M45.x, M46.1, M46.8, M46.9
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('L940','L941','L943','M120','M123','M310','M311','M312','M313','M461','M468','M469') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('M05','M06','M08','M30','M32','M33','M34','M35','M45') THEN 1
      ELSE 0
    END AS arth,

    -- =============================================================
    -- 22. COAGULOPATHY
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2871','2873','2874','2875') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('286') THEN 1
      -- ICD-10: D65-D68.x, D69.1, D69.3-D69.6
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('D691','D693','D694','D695','D696') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('D65','D66','D67','D68') THEN 1
      ELSE 0
    END AS coag,

    -- =============================================================
    -- 23. OBESITY
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2780') THEN 1
      -- ICD-10: E66.x
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('E66') THEN 1
      ELSE 0
    END AS obese,

    -- =============================================================
    -- 24. WEIGHT LOSS
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('7832','7994') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('260','261','262','263') THEN 1
      -- ICD-10: E40.x-E46.x, R63.4, R64
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('R634') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('E40','E41','E42','E43','E44','E45','E46','R64') THEN 1
      ELSE 0
    END AS wghtloss,

    -- =============================================================
    -- 25. FLUID AND ELECTROLYTE DISORDERS
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2536') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('276') THEN 1
      -- ICD-10: E22.2, E86.x, E87.x
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('E222') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('E86','E87') THEN 1
      ELSE 0
    END AS lytes,

    -- =============================================================
    -- 26. BLOOD LOSS ANEMIA
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2800') THEN 1
      -- ICD-10: D50.0
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('D500') THEN 1
      ELSE 0
    END AS bldloss,

    -- =============================================================
    -- 27. DEFICIENCY ANEMIAS
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2801','2808','2809') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('281') THEN 1
      -- ICD-10: D50.8, D50.9, D51.x-D53.x
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('D508','D509') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('D51','D52','D53') THEN 1
      ELSE 0
    END AS anemdef,

    -- =============================================================
    -- 28. ALCOHOL ABUSE
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2652','2911','2912','2913','2915','2918','2919','3030','3039','3050','3575','4255','5353','5710','5711','5712','5713','V113') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('980') THEN 1
      -- ICD-10: F10.x, E52, G62.1, I42.6, K29.2, K70.0, K70.3, K70.9, T51.x, Z50.2, Z71.4, Z72.1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('G621','I426','K292','K700','K703','K709','Z502','Z714','Z721') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('F10','E52','T51') THEN 1
      ELSE 0
    END AS alcohol,

    -- =============================================================
    -- 29. DRUG ABUSE
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND icd_code IN ('V6542') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('3052','3053','3054','3055','3056','3057','3058','3059') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('292','304') THEN 1
      -- ICD-10: F11.x-F16.x, F18.x, F19.x, Z71.5, Z72.2
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('Z715','Z722') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('F11','F12','F13','F14','F15','F16','F18','F19') THEN 1
      ELSE 0
    END AS drug,

    -- =============================================================
    -- 30. PSYCHOSES
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND icd_code IN ('29604','29614','29644','29654') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2938') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('295','297','298') THEN 1
      -- ICD-10: F20.x, F22.x-F25.x, F28.x, F29.x, F30.2, F31.2, F31.5
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('F302','F312','F315') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('F20','F22','F23','F24','F25','F28','F29') THEN 1
      ELSE 0
    END AS psych,

    -- =============================================================
    -- 31. DEPRESSION
    -- =============================================================
    CASE
      -- ICD-9
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('2962','2963','2965','3004') THEN 1
      WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('309','311') THEN 1
      -- ICD-10: F20.4, F31.3-F31.5, F32.x, F33.x, F34.1, F41.2, F43.2
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('F204','F313','F314','F315','F341','F412','F432') THEN 1
      WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('F32','F33') THEN 1
      ELSE 0
    END AS depress

  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` icd
  WHERE seq_num != 1  -- Exclude primary diagnosis per Elixhauser methodology
),

-- Aggregate flags to admission level
eligrp AS (
  SELECT
    hadm_id,
    MAX(chf) AS chf,
    MAX(arrhy) AS arrhy,
    MAX(valve) AS valve,
    MAX(pulmcirc) AS pulmcirc,
    MAX(perivasc) AS perivasc,
    MAX(htn) AS htn,
    MAX(htncx) AS htncx,
    MAX(para) AS para,
    MAX(neuro) AS neuro,
    MAX(chrnlung) AS chrnlung,
    MAX(dm) AS dm,
    MAX(dmcx) AS dmcx,
    MAX(hypothy) AS hypothy,
    MAX(renlfail) AS renlfail,
    MAX(liver) AS liver,
    MAX(ulcer) AS ulcer,
    MAX(aids) AS aids,
    MAX(lymph) AS lymph,
    MAX(mets) AS mets,
    MAX(tumor) AS tumor,
    MAX(arth) AS arth,
    MAX(coag) AS coag,
    MAX(obese) AS obese,
    MAX(wghtloss) AS wghtloss,
    MAX(lytes) AS lytes,
    MAX(bldloss) AS bldloss,
    MAX(anemdef) AS anemdef,
    MAX(alcohol) AS alcohol,
    MAX(drug) AS drug,
    MAX(psych) AS psych,
    MAX(depress) AS depress
  FROM eliflg
  GROUP BY hadm_id
)

-- Final output with hierarchy rules applied
SELECT
  adm.subject_id,
  adm.hadm_id,

  -- Individual comorbidity flags (with hierarchy rules)
  COALESCE(chf, 0) AS congestive_heart_failure,
  COALESCE(arrhy, 0) AS cardiac_arrhythmias,
  COALESCE(valve, 0) AS valvular_disease,
  COALESCE(pulmcirc, 0) AS pulmonary_circulation,
  COALESCE(perivasc, 0) AS peripheral_vascular,

  -- Hypertension: combine uncomplicated and complicated
  CASE
    WHEN COALESCE(htn, 0) = 1 OR COALESCE(htncx, 0) = 1 THEN 1
    ELSE 0
  END AS hypertension,

  COALESCE(para, 0) AS paralysis,
  COALESCE(neuro, 0) AS other_neurological,
  COALESCE(chrnlung, 0) AS chronic_pulmonary,

  -- Diabetes: complicated overrides uncomplicated
  CASE
    WHEN COALESCE(dmcx, 0) = 1 THEN 0
    WHEN COALESCE(dm, 0) = 1 THEN 1
    ELSE 0
  END AS diabetes_uncomplicated,
  COALESCE(dmcx, 0) AS diabetes_complicated,

  COALESCE(hypothy, 0) AS hypothyroidism,
  COALESCE(renlfail, 0) AS renal_failure,
  COALESCE(liver, 0) AS liver_disease,
  COALESCE(ulcer, 0) AS peptic_ulcer,
  COALESCE(aids, 0) AS aids,
  COALESCE(lymph, 0) AS lymphoma,
  COALESCE(mets, 0) AS metastatic_cancer,

  -- Solid tumor: metastatic overrides non-metastatic
  CASE
    WHEN COALESCE(mets, 0) = 1 THEN 0
    WHEN COALESCE(tumor, 0) = 1 THEN 1
    ELSE 0
  END AS solid_tumor,

  COALESCE(arth, 0) AS rheumatoid_arthritis,
  COALESCE(coag, 0) AS coagulopathy,
  COALESCE(obese, 0) AS obesity,
  COALESCE(wghtloss, 0) AS weight_loss,
  COALESCE(lytes, 0) AS fluid_electrolyte,
  COALESCE(bldloss, 0) AS blood_loss_anemia,
  COALESCE(anemdef, 0) AS deficiency_anemias,
  COALESCE(alcohol, 0) AS alcohol_abuse,
  COALESCE(drug, 0) AS drug_abuse,
  COALESCE(psych, 0) AS psychoses,
  COALESCE(depress, 0) AS depression,

  -- Unweighted Elixhauser count (29 categories after hierarchy)
  (
    COALESCE(chf, 0) + COALESCE(arrhy, 0) + COALESCE(valve, 0) + COALESCE(pulmcirc, 0) +
    COALESCE(perivasc, 0) +
    CASE WHEN COALESCE(htn, 0) = 1 OR COALESCE(htncx, 0) = 1 THEN 1 ELSE 0 END +
    COALESCE(para, 0) + COALESCE(neuro, 0) + COALESCE(chrnlung, 0) +
    CASE WHEN COALESCE(dmcx, 0) = 1 THEN 0 WHEN COALESCE(dm, 0) = 1 THEN 1 ELSE 0 END +
    COALESCE(dmcx, 0) + COALESCE(hypothy, 0) + COALESCE(renlfail, 0) + COALESCE(liver, 0) +
    COALESCE(ulcer, 0) + COALESCE(aids, 0) + COALESCE(lymph, 0) + COALESCE(mets, 0) +
    CASE WHEN COALESCE(mets, 0) = 1 THEN 0 WHEN COALESCE(tumor, 0) = 1 THEN 1 ELSE 0 END +
    COALESCE(arth, 0) + COALESCE(coag, 0) + COALESCE(obese, 0) + COALESCE(wghtloss, 0) +
    COALESCE(lytes, 0) + COALESCE(bldloss, 0) + COALESCE(anemdef, 0) + COALESCE(alcohol, 0) +
    COALESCE(drug, 0) + COALESCE(psych, 0) + COALESCE(depress, 0)
  ) AS elixhauser_count,

  -- van Walraven weighted score (Med Care 2009;47(6):626-33)
  -- Weights derived for in-hospital mortality prediction
  (
    7 * COALESCE(chf, 0) +          -- Congestive heart failure
    5 * COALESCE(arrhy, 0) +        -- Cardiac arrhythmias
    (-1) * COALESCE(valve, 0) +     -- Valvular disease
    4 * COALESCE(pulmcirc, 0) +     -- Pulmonary circulation disorders
    2 * COALESCE(perivasc, 0) +     -- Peripheral vascular disorders
    -- 0 * hypertension (combined)  -- Hypertension (weight = 0)
    7 * COALESCE(para, 0) +         -- Paralysis
    6 * COALESCE(neuro, 0) +        -- Other neurological disorders
    3 * COALESCE(chrnlung, 0) +     -- Chronic pulmonary disease
    -- 0 * diabetes_uncomplicated   -- Diabetes uncomplicated (weight = 0)
    -- 0 * diabetes_complicated     -- Diabetes complicated (weight = 0)
    -- 0 * hypothyroidism           -- Hypothyroidism (weight = 0)
    5 * COALESCE(renlfail, 0) +     -- Renal failure
    11 * COALESCE(liver, 0) +       -- Liver disease
    -- 0 * peptic_ulcer             -- Peptic ulcer (weight = 0)
    -- 0 * aids                     -- AIDS/HIV (weight = 0)
    9 * COALESCE(lymph, 0) +        -- Lymphoma
    12 * COALESCE(mets, 0) +        -- Metastatic cancer
    4 * CASE WHEN COALESCE(mets, 0) = 1 THEN 0 WHEN COALESCE(tumor, 0) = 1 THEN 1 ELSE 0 END + -- Solid tumor (after hierarchy)
    -- 0 * rheumatoid_arthritis     -- Rheumatoid arthritis (weight = 0)
    3 * COALESCE(coag, 0) +         -- Coagulopathy
    (-4) * COALESCE(obese, 0) +     -- Obesity
    6 * COALESCE(wghtloss, 0) +     -- Weight loss
    5 * COALESCE(lytes, 0) +        -- Fluid and electrolyte disorders
    (-2) * COALESCE(bldloss, 0) +   -- Blood loss anemia
    (-2) * COALESCE(anemdef, 0) +   -- Deficiency anemias
    -- 0 * alcohol_abuse            -- Alcohol abuse (weight = 0)
    (-7) * COALESCE(drug, 0) +      -- Drug abuse
    -- 0 * psychoses                -- Psychoses (weight = 0)
    (-3) * COALESCE(depress, 0)     -- Depression
  ) AS elixhauser_vanwalraven

FROM `physionet-data.mimiciv_3_1_hosp.admissions` adm
LEFT JOIN eligrp eli ON adm.hadm_id = eli.hadm_id
ORDER BY adm.subject_id, adm.hadm_id;
