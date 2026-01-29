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
