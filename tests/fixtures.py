SAMPLE_DEALS = [
    {"address": "דיזנגוף 78",  "dealDate": "2026-02-01", "dealAmount": 4675000, "priceSM": 63176, "roomNum": 3.0, "floor": "חמישית",  "assetArea": 74.0,  "yearBuilt": 1930, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 203", "dealDate": "2026-01-03", "dealAmount": 4794000, "priceSM": 103509,"roomNum": 3.0, "floor": "קרקע",    "assetArea": 46.32, "yearBuilt": 1960, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 230", "dealDate": "2025-12-28", "dealAmount": 4620000, "priceSM": 70000, "roomNum": 3.0, "floor": "חמישית",  "assetArea": 66.0,  "yearBuilt": 1955, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 154", "dealDate": "2025-12-21", "dealAmount": 3220000, "priceSM": 44513, "roomNum": 3.0, "floor": "שלישית", "assetArea": 72.33, "yearBuilt": 1940, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 137", "dealDate": "2025-12-10", "dealAmount": 3800000, "priceSM": 66667, "roomNum": 2.0, "floor": "חמישית",  "assetArea": 57.0,  "yearBuilt": 1935, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 50",  "dealDate": "2025-12-09", "dealAmount": 5500000, "priceSM": 59140, "roomNum": 4.0, "floor": "עשרים",   "assetArea": 93.0,  "yearBuilt": 1930, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 203", "dealDate": "2025-12-02", "dealAmount": 12000000,"priceSM": 95238, "roomNum": 4.0, "floor": "שניה",    "assetArea": 126.0, "yearBuilt": 1960, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 126", "dealDate": "2025-11-20", "dealAmount": 4300000, "priceSM": 75439, "roomNum": 2.5, "floor": "חמישית",  "assetArea": 57.0,  "yearBuilt": 1945, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 136", "dealDate": "2025-11-18", "dealAmount": 3290000, "priceSM": 55201, "roomNum": 3.0, "floor": "שניה",    "assetArea": 59.6,  "yearBuilt": 1952, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 249", "dealDate": "2025-11-02", "dealAmount": 10700000,"priceSM": 62941, "roomNum": 5.0, "floor": "שביעית",  "assetArea": 170.0, "yearBuilt": 1965, "dealNature": "דירת גג",         "neighborhoodName": "הצפון הישן"},
    # Deal with no priceSM — should be handled gracefully
    {"address": "דיזנגוף 70",  "dealDate": "2025-11-30", "dealAmount": 593000,  "priceSM": None,  "roomNum": None,"floor": "מרתף",   "assetArea": 55.74, "yearBuilt": 1930, "dealNature": "מחסנים",          "neighborhoodName": "הצפון הישן"},
    # Deal with no dealAmount — should be excluded from stats
    {"address": "דיזנגוף 1",   "dealDate": "2025-10-01", "dealAmount": None,    "priceSM": None,  "roomNum": 2.0, "floor": "ראשונה", "assetArea": 60.0,  "yearBuilt": 1935, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
]
