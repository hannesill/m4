#!/usr/bin/env python3
"""
Hospital Frailty Risk Score (HFRS) Calculator

Based on Gilbert et al. (2018) Lancet:
"Development and validation of a Hospital Frailty Risk Score focusing on
older people in acute care settings using electronic hospital records"

Supports both ICD-9-CM and ICD-10-CM codes for MIMIC-IV compatibility.

Risk Categories:
  - Low risk: HFRS < 5
  - Intermediate risk: 5 <= HFRS < 15
  - High risk: HFRS >= 15
"""

# HFRS ICD-10 codes with weights and ICD-9 mappings
# Format: icd10_code -> (weight, description, [icd9_codes])
HFRS_CODES = {
    "F00": (7.1, "Dementia in Alzheimer's disease", ["2900", "2901", "2902", "2903"]),
    "G81": (4.4, "Hemiplegia", ["3420", "3421", "3428", "3429"]),
    "G30": (4.0, "Alzheimer's disease", ["3310"]),
    "I69": (3.7, "Sequelae of cerebrovascular disease", ["438"]),
    "R29": (
        3.6,
        "Other symptoms involving nervous and musculoskeletal systems",
        ["7812", "7819", "7813"],
    ),
    "N39": (
        3.2,
        "Other disorders of urinary system",
        ["5990", "5997", "78830", "78831", "78832", "78833", "78834", "78839"],
    ),
    "F05": (3.2, "Delirium not induced by alcohol", ["2930", "2931"]),
    "W19": (3.2, "Unspecified fall", ["E8889"]),
    "S00": (
        3.2,
        "Superficial injury of head",
        [
            "9100",
            "9101",
            "9102",
            "9103",
            "9104",
            "9105",
            "9106",
            "9107",
            "9108",
            "9109",
        ],
    ),
    "R31": (3.0, "Unspecified haematuria", ["5997"]),
    "B96": (2.9, "Other bacterial agents as cause of disease", ["0418"]),
    "R41": (2.7, "Other symptoms involving cognitive functions", ["78093", "78097"]),
    "R26": (2.6, "Abnormalities of gait and mobility", ["7812"]),
    "I67": (2.6, "Other cerebrovascular diseases", ["4378", "4379"]),
    "R56": (2.6, "Convulsions not elsewhere classified", ["7803"]),
    "R40": (2.5, "Somnolence stupor and coma", ["78009", "78001", "78003"]),
    "T83": (
        2.4,
        "Complications of genitourinary prosthetic devices",
        ["9961", "9962", "9963", "9964", "9965"],
    ),
    "S06": (
        2.4,
        "Intracranial injury",
        ["8500", "8501", "8502", "8503", "8504", "8505", "8509"],
    ),
    "S42": (
        2.3,
        "Fracture of shoulder and upper arm",
        ["8100", "8101", "8102", "8103", "8110", "8111", "8112", "8113"],
    ),
    "E87": (
        2.3,
        "Other disorders of fluid electrolyte and acid-base balance",
        [
            "2760",
            "2761",
            "2762",
            "2763",
            "2764",
            "2765",
            "2766",
            "2767",
            "2768",
            "2769",
        ],
    ),
    "M25": (
        2.3,
        "Other joint disorders not elsewhere classified",
        [
            "71940",
            "71941",
            "71942",
            "71943",
            "71944",
            "71945",
            "71946",
            "71947",
            "71948",
            "71949",
        ],
    ),
    "E86": (2.3, "Volume depletion", ["2765"]),
    "R54": (2.2, "Senility", ["797"]),
    "Z50": (
        2.1,
        "Care involving use of rehabilitation procedures",
        ["V571", "V572", "V573", "V574", "V575", "V576", "V577", "V578", "V579"],
    ),
    "F03": (2.1, "Unspecified dementia", ["2949"]),
    "W18": (2.1, "Other fall on same level", ["E8881"]),
    "Z75": (
        2.0,
        "Problems related to medical facilities and other health care",
        ["V632", "V633", "V634", "V638", "V639"],
    ),
    "F01": (2.0, "Vascular dementia", ["29040", "29041", "29042", "29043"]),
    "S80": (2.0, "Superficial injury of lower leg", ["9160", "9161"]),
    "L03": (
        2.0,
        "Cellulitis",
        ["6810", "6811", "68100", "68101", "68102", "68110", "68111"],
    ),
    "H54": (
        1.9,
        "Blindness and low vision",
        ["3690", "3691", "3692", "3693", "3694", "3696", "3698", "3699"],
    ),
    "E53": (1.9, "Deficiency of other B group vitamins", ["2661", "2662"]),
    "Z60": (
        1.8,
        "Problems related to social environment",
        ["V600", "V601", "V602", "V603", "V604", "V608", "V609"],
    ),
    "G20": (1.8, "Parkinson's disease", ["3320"]),
    "R55": (1.8, "Syncope and collapse", ["7802"]),
    "S22": (
        1.8,
        "Fracture of ribs sternum and thoracic spine",
        ["8070", "8071", "8072", "8073", "8074", "8050", "8052"],
    ),
    "K59": (
        1.8,
        "Other functional intestinal disorders",
        [
            "5640",
            "5641",
            "5642",
            "5643",
            "5644",
            "5645",
            "5646",
            "5647",
            "5648",
            "5649",
        ],
    ),
    "N17": (1.8, "Acute renal failure", ["5845", "5846", "5847", "5848", "5849"]),
    "L89": (1.7, "Decubitus ulcer", ["7070"]),
    "Z22": (
        1.7,
        "Carrier of infectious disease",
        [
            "V020",
            "V021",
            "V022",
            "V023",
            "V024",
            "V025",
            "V026",
            "V027",
            "V028",
            "V029",
        ],
    ),
    "B95": (
        1.7,
        "Streptococcus and staphylococcus as cause of disease",
        ["0410", "0411", "0412"],
    ),
    "L97": (1.6, "Ulcer of lower limb not elsewhere classified", ["7071"]),
    "R44": (
        1.6,
        "Other symptoms involving general sensations and perceptions",
        ["7801"],
    ),
    "K26": (
        1.6,
        "Duodenal ulcer",
        ["5320", "5321", "5322", "5323", "5324", "5325", "5326", "5327", "5329"],
    ),
    "I95": (1.6, "Hypotension", ["4580", "4581", "4588", "4589"]),
    "N19": (1.6, "Unspecified renal failure", ["586"]),
    "A41": (
        1.6,
        "Other septicaemia",
        ["0380", "0381", "0382", "0383", "0384", "0388", "0389", "99591", "99592"],
    ),
    "Z87": (
        1.5,
        "Personal history of other diseases and conditions",
        ["V1200", "V1201", "V1202", "V1209", "V121", "V122", "V123"],
    ),
    "J96": (
        1.5,
        "Respiratory failure not elsewhere classified",
        ["51881", "51882", "51883", "51884"],
    ),
    "X59": (1.5, "Exposure to unspecified factor", ["E9289"]),
    "M19": (1.5, "Other arthrosis", ["7150", "7151", "7152", "7153", "7158", "7159"]),
    "G40": (
        1.5,
        "Epilepsy",
        [
            "3450",
            "3451",
            "3452",
            "3453",
            "3454",
            "3455",
            "3456",
            "3457",
            "3458",
            "3459",
        ],
    ),
    "M81": (
        1.4,
        "Osteoporosis without pathological fracture",
        ["73300", "73301", "73302", "73303", "73309"],
    ),
    "S72": (
        1.4,
        "Fracture of femur",
        [
            "8200",
            "8201",
            "8202",
            "8203",
            "8208",
            "8209",
            "8210",
            "8211",
            "8212",
            "8213",
        ],
    ),
    "S32": (
        1.4,
        "Fracture of lumbar spine and pelvis",
        [
            "8052",
            "8054",
            "8080",
            "8081",
            "8082",
            "8083",
            "8084",
            "8085",
            "8088",
            "8089",
        ],
    ),
    "E16": (1.4, "Other disorders of pancreatic internal secretion", ["2511", "2512"]),
    "R94": (
        1.4,
        "Abnormal results of function studies",
        [
            "7940",
            "7941",
            "7942",
            "7943",
            "7944",
            "7945",
            "7946",
            "7947",
            "7948",
            "7949",
        ],
    ),
    "N18": (
        1.4,
        "Chronic renal failure",
        ["5851", "5852", "5853", "5854", "5855", "5856", "5859"],
    ),
    "R33": (1.3, "Retention of urine", ["7882"]),
    "R69": (1.3, "Unknown and unspecified causes of morbidity", ["7999"]),
    "N28": (
        1.3,
        "Other disorders of kidney and ureter not elsewhere classified",
        ["5930", "5931", "5937", "5938", "5939"],
    ),
    "R32": (1.2, "Unspecified urinary incontinence", ["78830"]),
    "G31": (
        1.2,
        "Other degenerative diseases of nervous system",
        ["3311", "3312", "3317", "3318", "3319"],
    ),
    "Y95": (1.2, "Nosocomial condition", ["E8786"]),
    "S09": (1.2, "Other and unspecified injuries of head", ["9590"]),
    "R45": (1.2, "Symptoms and signs involving emotional state", ["7990"]),
    "G45": (
        1.2,
        "Transient cerebral ischaemic attacks",
        ["4350", "4351", "4352", "4353", "4358", "4359"],
    ),
    "Z74": (
        1.1,
        "Problems related to care-provider dependency",
        ["V462", "V468", "V469"],
    ),
    "M79": (
        1.1,
        "Other soft tissue disorders not elsewhere classified",
        ["7291", "7292", "7293", "7294", "7295", "7299"],
    ),
    "W06": (1.1, "Fall involving bed", ["E8840"]),
    "S01": (
        1.1,
        "Open wound of head",
        ["8700", "8701", "8702", "8703", "8704", "8708", "8709", "8730"],
    ),
    "A04": (
        1.1,
        "Other bacterial intestinal infections",
        [
            "0040",
            "0041",
            "0042",
            "0043",
            "0044",
            "0045",
            "0046",
            "0047",
            "0048",
            "0049",
        ],
    ),
    "A09": (
        1.1,
        "Diarrhoea and gastroenteritis of presumed infectious origin",
        ["00861", "00862", "00863", "00864", "00865", "00866", "00867", "00869"],
    ),
    "J18": (
        1.1,
        "Pneumonia organism unspecified",
        [
            "485",
            "4860",
            "4861",
            "4869",
            "480",
            "481",
            "4820",
            "4821",
            "4822",
            "4830",
            "4831",
            "4838",
            "484",
        ],
    ),
    "J69": (1.0, "Pneumonitis due to solids and liquids", ["5070"]),
    "R47": (
        1.0,
        "Speech disturbances not elsewhere classified",
        ["78451", "78452", "78459"],
    ),
    "E55": (1.0, "Vitamin D deficiency", ["2680", "2681", "2682", "2689"]),
    "Z93": (
        1.0,
        "Artificial opening status",
        [
            "V440",
            "V441",
            "V442",
            "V443",
            "V444",
            "V445",
            "V446",
            "V447",
            "V448",
            "V449",
        ],
    ),
    "R02": (1.0, "Gangrene not elsewhere classified", ["7854"]),
    "R63": (
        0.9,
        "Symptoms and signs concerning food and fluid intake",
        ["7830", "7831", "7836"],
    ),
    "H91": (
        0.9,
        "Other hearing loss",
        [
            "3890",
            "3891",
            "3892",
            "38910",
            "38911",
            "38912",
            "38913",
            "38914",
            "38915",
            "38916",
            "38917",
            "38918",
        ],
    ),
    "W10": (0.9, "Fall on and from stairs and steps", ["E8809"]),
    "W01": (
        0.9,
        "Fall on same level from slipping tripping and stumbling",
        ["E8850", "E8851", "E8852", "E8853", "E8854", "E8859"],
    ),
    "E05": (
        0.9,
        "Thyrotoxicosis hyperthyroidism",
        ["2420", "2421", "2422", "2423", "2424", "2428", "2429"],
    ),
    "M41": (0.9, "Scoliosis", ["7370", "7371", "7372", "7373", "7378", "7379"]),
    "R13": (0.8, "Dysphagia", ["7872"]),
    "Z99": (
        0.8,
        "Dependence on enabling machines and devices",
        ["V460", "V461", "V462", "V468", "V469"],
    ),
    "U80": (
        0.8,
        "Agent resistant to penicillin and related antibiotics",
        ["V090", "V091"],
    ),
    "M80": (
        0.8,
        "Osteoporosis with pathological fracture",
        ["73310", "73311", "73312", "73313", "73319"],
    ),
    "K92": (
        0.8,
        "Other diseases of digestive system",
        ["5780", "5781", "5789", "5693"],
    ),
    "I63": (0.8, "Cerebral infarction", ["4340", "4341", "4349", "4360"]),
    "N20": (0.7, "Calculus of kidney and ureter", ["5920", "5921"]),
    "F10": (
        0.7,
        "Mental and behavioural disorders due to use of alcohol",
        [
            "2910",
            "2911",
            "2912",
            "2913",
            "2914",
            "2915",
            "2918",
            "2919",
            "3039",
            "30500",
            "30501",
            "30502",
            "30503",
        ],
    ),
    "Y84": (0.7, "Other medical procedures as cause of abnormal reaction", ["E8798"]),
    "R00": (0.7, "Abnormalities of heart beat", ["7850", "7851"]),
    "J22": (0.7, "Unspecified acute lower respiratory infection", ["519"]),
    "Z73": (0.6, "Problems related to life-management difficulty", ["V629"]),
    "R79": (0.6, "Other abnormal findings of blood chemistry", ["7909"]),
    "Z91": (
        0.5,
        "Personal history of risk-factors not elsewhere classified",
        ["V1582", "V1585", "V1586", "V1588", "V1589"],
    ),
    "S51": (0.5, "Open wound of forearm", ["8810", "8811"]),
    "F32": (0.5, "Depressive episode", ["2962", "2963", "2965", "2966", "3004", "311"]),
    "M48": (0.5, "Spinal stenosis", ["72400", "72401", "72402", "72403", "72409"]),
    "E83": (0.4, "Disorders of mineral metabolism", ["2753", "2754"]),
    "M15": (0.4, "Polyarthrosis", ["7150", "7159"]),
    "D64": (0.4, "Other anaemias", ["2859", "2854", "2858"]),
    "L08": (0.4, "Other local infections of skin and subcutaneous tissue", ["6868"]),
    "R11": (0.3, "Nausea and vomiting", ["78701", "78702", "78703"]),
    "K52": (0.3, "Other noninfective gastroenteritis and colitis", ["5582", "5589"]),
    "R50": (0.1, "Fever of unknown origin", ["78060", "78061"]),
}


def build_icd9_lookup() -> dict:
    """Build reverse lookup from ICD-9 codes to ICD-10 codes with weights."""
    icd9_to_weight = {}
    for icd10, (weight, desc, icd9_codes) in HFRS_CODES.items():
        for icd9 in icd9_codes:
            icd9_to_weight[icd9] = (weight, icd10, desc)
    return icd9_to_weight


ICD9_LOOKUP = build_icd9_lookup()


def normalize_icd_code(code: str) -> str:
    """Normalize ICD code by removing dots and converting to uppercase."""
    if code is None:
        return ""
    return code.replace(".", "").strip().upper()


def get_icd10_weight(code: str) -> tuple:
    """Get HFRS weight for an ICD-10 code (3-character prefix matching)."""
    code = normalize_icd_code(code)
    if len(code) < 3:
        return (0, None, None)

    prefix = code[:3]
    if prefix in HFRS_CODES:
        weight, desc, _ = HFRS_CODES[prefix]
        return (weight, prefix, desc)
    return (0, None, None)


def get_icd9_weight(code: str) -> tuple:
    """Get HFRS weight for an ICD-9 code (prefix matching)."""
    code = normalize_icd_code(code)
    if not code:
        return (0, None, None)

    # Try progressively shorter prefixes
    for length in range(len(code), 2, -1):
        prefix = code[:length]
        if prefix in ICD9_LOOKUP:
            return ICD9_LOOKUP[prefix]

    if len(code) >= 3 and code[:3] in ICD9_LOOKUP:
        return ICD9_LOOKUP[code[:3]]

    return (0, None, None)


def calculate_hfrs(diagnoses: list, icd_version: int | None = None) -> dict:
    """
    Calculate Hospital Frailty Risk Score from a list of diagnoses.

    Args:
        diagnoses: List of dicts with 'icd_code' and optionally 'icd_version' keys
                   OR list of tuples (icd_code, icd_version)
                   OR list of strings (icd_codes only, requires icd_version param)
        icd_version: Default ICD version (9 or 10) if not specified per diagnosis

    Returns:
        dict with score, risk_category, matched_codes, etc.
    """
    matched_codes = []
    seen_icd10_codes = set()

    for diag in diagnoses:
        if isinstance(diag, dict):
            code = diag.get("icd_code", "")
            version = diag.get("icd_version", icd_version)
        elif isinstance(diag, tuple):
            code, version = diag[0], diag[1] if len(diag) > 1 else icd_version
        else:
            code = str(diag)
            version = icd_version

        if version == 10:
            weight, icd10_code, desc = get_icd10_weight(code)
        elif version == 9:
            weight, icd10_code, desc = get_icd9_weight(code)
        else:
            weight, icd10_code, desc = get_icd10_weight(code)
            if weight == 0:
                weight, icd10_code, desc = get_icd9_weight(code)

        if weight > 0 and icd10_code not in seen_icd10_codes:
            seen_icd10_codes.add(icd10_code)
            matched_codes.append(
                {
                    "original_code": code,
                    "icd10_equivalent": icd10_code,
                    "description": desc,
                    "weight": weight,
                }
            )

    score = sum(m["weight"] for m in matched_codes)

    if score < 5:
        risk_category = "Low"
    elif score < 15:
        risk_category = "Intermediate"
    else:
        risk_category = "High"

    return {
        "score": round(score, 1),
        "risk_category": risk_category,
        "matched_codes": sorted(matched_codes, key=lambda x: -x["weight"]),
        "total_diagnoses": len(diagnoses),
        "matched_count": len(matched_codes),
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Calculate Hospital Frailty Risk Score"
    )
    parser.add_argument("--codes", nargs="+", help="ICD codes to evaluate")
    parser.add_argument("--version", type=int, choices=[9, 10], help="ICD version")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.codes:
        result = calculate_hfrs(args.codes, icd_version=args.version)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("\n=== Hospital Frailty Risk Score ===")
            print(f"Score: {result['score']}")
            print(f"Risk Category: {result['risk_category']}")
            print(
                f"Matched: {result['matched_count']}/{result['total_diagnoses']} diagnoses"
            )
            if result["matched_codes"]:
                print("\nMatched diagnoses:")
                for m in result["matched_codes"][:10]:
                    print(
                        f"  {m['original_code']} -> {m['icd10_equivalent']}: {m['weight']} ({m['description']})"
                    )
    else:
        parser.print_help()
