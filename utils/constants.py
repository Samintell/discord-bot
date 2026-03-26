"""
Constants for the MaiMai quiz bot, including available categories and versions.
"""

# Available categories in MaiMai (Japanese: English)
CATEGORIES = {
    "POPS＆アニメ": "pops",
    "niconico＆ボーカロイド": "vocaloid", 
    "東方Project": "touhou",
    "ゲーム＆バラエティ": "game",
    "maimai": "maimai",
    "オンゲキ＆CHUNITHM": "ongeki"
}

# Create reverse mapping for lookups (lowercase English -> Japanese)
CATEGORY_MAPPING = {v.lower(): k for k, v in CATEGORIES.items()}
# Also add Japanese names in the mapping (lowercase -> original)
for jp_name in CATEGORIES.keys():
    CATEGORY_MAPPING[jp_name.lower()] = jp_name

# Available game versions (Japanese: English)
VERSIONS = {
    "maimai": "maimai",
    "maimai PLUS": "maimai plus",
    "GreeN": "green",
    "GreeN PLUS": "green plus",
    "ORANGE": "orange",
    "ORANGE PLUS": "orange plus",
    "PiNK": "pink",
    "PiNK PLUS": "pink plus",
    "MURASAKi": "murasaki",
    "MURASAKi PLUS": "murasaki plus",
    "MiLK": "milk",
    "MiLK PLUS": "milk plus",
    "FiNALE": "finale",
    "maimaiでらっくす": "deluxe",
    "maimaiでらっくす PLUS": "deluxe plus",
    "Splash": "splash",
    "Splash PLUS": "splash plus",
    "UNiVERSE": "universe",
    "UNiVERSE PLUS": "universe plus",
    "FESTiVAL": "festival",
    "FESTiVAL PLUS": "festival plus",
    "BUDDiES": "buddies",
    "BUDDiES PLUS": "buddies plus",
    "PRiSM": "prism",
    "PRiSM PLUS": "prism plus",
    "CiRCLE": "circle",
    "宴会場": "banquet",
    "うちゅう": "uchuu"
}

# Create reverse mapping for lookups (lowercase English -> Japanese)
VERSION_MAPPING = {v.lower(): k for k, v in VERSIONS.items()}
# Also add Japanese names in the mapping (lowercase -> original)
for jp_name in VERSIONS.keys():
    VERSION_MAPPING[jp_name.lower()] = jp_name

# Available regions (display name: internal key)
REGIONS = {
    "Japan": "jp",
    "International": "intl",
    "USA": "usa"
}

# Create reverse mapping for lookups (lowercase -> internal key)
REGION_MAPPING = {v.lower(): v for v in REGIONS.values()}
# Also add display names in the mapping (lowercase -> internal key)
for display_name, key in REGIONS.items():
    REGION_MAPPING[display_name.lower()] = key

# Achievement rank thresholds (rank -> minimum achievement * 10000)
RANK_THRESHOLDS = {
    "A": 800000,
    "AA": 900000,
    "AAA": 940000,
    "S": 970000,
    "S+": 980000,
    "SS": 990000,
    "SS+": 995000,
    "SSS": 1000000,
    "SSS+": 1005000,
}

# FC hierarchy for comparison (higher index = better)
FC_HIERARCHY = ["none", "fc", "fc+", "ap", "ap+"]

# Difficulty index mapping for maimai NET URLs
SCORE_DIFFICULTY_INDICES = {
    "basic": 0,
    "advanced": 1,
    "expert": 2,
    "master": 3,
    "remaster": 4,
}

# Difficulty names indexed by maimai NET difficulty number
SCORE_DIFFICULTY_NAMES = ["basic", "advanced", "expert", "master", "remaster"]
