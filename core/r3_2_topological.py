"""
r3_2_topological.py — R3.2 Topological Invariance Module (Lightning)
═══════════════════════════════════════════════════════════════════════════════
Detects semantic equivalence under paraphrase when lexical overlap is near zero.
100% Python standard library. Zero external dependencies. ~30 µs/pair.

Architecture:
  1. Canonical cluster dictionary (inline O(1) synonym resolution)
  2. Deterministic lemmatizer (inline, no nltk/WordNet)
  3. Triple extractor: (Agent, Action, Patient, Polarity)
  4. Passive voice inversion + copular symmetry
  5. Comparison engine with strict anchoring rule
  6. Conditional gate: PARAPHRASE_RESCUE / CONTRADICTION_VETO / INACTIVE

Registry: TAD EX-2026-18792778
Author: Gonzalo Emir Durante — Project Manifold 0.56
License: Durante Invariance License v1.0
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

MODULE_VERSION: str = "1.0.0"

KAPPA_D: float = 0.56
PARAPHRASE_RESCUE_BOOST: float = 0.15
CONTRADICTION_VETO_PENALTY: float = -0.35
LEXICAL_OVERLAP_THRESHOLD: float = 0.30
MIN_ANCHORED_COMPONENTS: int = 2
VERB_WEIGHT: float = 0.40
AGENT_WEIGHT: float = 0.30
PATIENT_WEIGHT: float = 0.30
COMPONENT_MATCH_THRESHOLD: float = 0.50

# ═══════════════════════════════════════════════════════════════════════════════
# STOPWORDS & LINKING PREPOSITIONS
# ═══════════════════════════════════════════════════════════════════════════════

STOPWORDS: Set[str] = {
    "the", "a", "an", "this", "that", "these", "those",
    "some", "any", "every", "each", "all", "both",
}

LINKING_PREPOSITIONS: Set[str] = {
    "on", "upon", "in", "into", "at", "to", "from",
    "with", "by", "about", "over", "under", "of", "for",
}

# ═══════════════════════════════════════════════════════════════════════════════
# NEGATION TOKENS (explicit + scope)
# ═══════════════════════════════════════════════════════════════════════════════

NEGATION_TOKENS: Set[str] = {
    "not", "no", "never", "neither", "nor", "without",
    "hardly", "barely", "scarcely", "seldom", "rarely",
    "lack", "lacks", "lacked", "lacking",
    "fail", "fails", "failed", "failing",
    "unable", "impossible", "false", "incorrect",
    "none", "nobody", "nothing", "nowhere",
}

# ═══════════════════════════════════════════════════════════════════════════════
# IRREGULAR VERB TABLE (inline lemmatizer)
# ═══════════════════════════════════════════════════════════════════════════════

_IRREGULAR_VERBS: Dict[str, str] = {
    "sat": "sit", "rested": "rest",
    "was": "be", "were": "be", "been": "be", "am": "be", "is": "be", "are": "be",
    "ate": "eat", "eaten": "eat",
    "wrote": "write", "written": "write",
    "bought": "buy", "built": "build", "found": "find", "made": "make",
    "took": "take", "taken": "take", "went": "go", "gone": "go",
    "saw": "see", "seen": "see", "knew": "know", "known": "know",
    "spoke": "speak", "spoken": "speak", "broke": "break", "broken": "break",
    "gave": "give", "given": "give", "ran": "run",
    "drank": "drink", "drunk": "drink", "drove": "drive", "driven": "drive",
    "rode": "ride", "ridden": "ride", "sang": "sing", "sung": "sing",
    "swam": "swim", "swum": "swim", "froze": "freeze", "frozen": "freeze",
    "chose": "choose", "chosen": "choose", "hid": "hide", "hidden": "hide",
    "bit": "bite", "bitten": "bite", "blew": "blow", "blown": "blow",
    "drew": "draw", "drawn": "draw", "flew": "fly", "flown": "fly",
    "grew": "grow", "grown": "grow", "threw": "throw", "thrown": "throw",
    "wore": "wear", "worn": "wear", "shook": "shake", "shaken": "shake",
    "stole": "steal", "stolen": "steal", "swore": "swear", "sworn": "swear",
    "tore": "tear", "torn": "tear", "woke": "wake", "woken": "wake",
    "won": "win", "lost": "lose", "meant": "mean", "sent": "send",
    "spent": "spend", "held": "hold", "kept": "keep", "left": "leave",
    "led": "lead", "met": "meet", "paid": "pay", "put": "put",
    "read": "read", "said": "say", "set": "set", "shot": "shoot",
    "shown": "show", "shut": "shut", "sold": "sell", "taught": "teach",
    "told": "tell", "thought": "think", "understood": "understand",
    "children": "child", "men": "man", "women": "woman",
    "mice": "mouse", "teeth": "tooth", "feet": "foot",
    "people": "person", "geese": "goose", "oxen": "ox",
    # copular forms
    "constitutes": "constitute", "constituted": "constitute", "constituting": "constitute",
    "equals": "equal", "equaled": "equal", "equalling": "equal",
    "represents": "represent", "represented": "represent", "representing": "represent",
    "means": "mean", "signifies": "signify", "signified": "signify",
}

# ═══════════════════════════════════════════════════════════════════════════════
# CANONICAL CLUSTERS (inline O(1) synonym resolution)
# ═══════════════════════════════════════════════════════════════════════════════

_CANONICAL_CLUSTERS: Dict[str, str] = {
    # ── Entities / Objects ──
    "cat": "$FELID", "feline": "$FELID", "kitten": "$FELID",
    "dog": "$CANID", "canine": "$CANID", "hound": "$CANID", "puppy": "$CANID",
    "mat": "$FLOOR_COVER", "rug": "$FLOOR_COVER", "carpet": "$FLOOR_COVER",
    "car": "$VEHICLE", "automobile": "$VEHICLE", "vehicle": "$VEHICLE",
    "house": "$DWELLING", "home": "$DWELLING", "residence": "$DWELLING", "dwelling": "$DWELLING",
    "doctor": "$PHYSICIAN", "physician": "$PHYSICIAN", "medic": "$PHYSICIAN",
    "book": "$PUBLICATION", "novel": "$PUBLICATION", "tome": "$PUBLICATION", "publication": "$PUBLICATION",
    "money": "$CURRENCY", "cash": "$CURRENCY", "currency": "$CURRENCY", "funds": "$CURRENCY",
    "earth": "$EARTH", "world": "$EARTH", "globe": "$EARTH", "planet": "$EARTH",
    "law": "$LAW", "regulation": "$LAW", "statute": "$LAW", "rule": "$LAW",
    "illness": "$DISEASE", "disease": "$DISEASE", "sickness": "$DISEASE", "ailment": "$DISEASE",
    "weapon": "$WEAPON", "gun": "$WEAPON", "firearm": "$WEAPON", "arm": "$WEAPON",
    "food": "$FOOD", "nourishment": "$FOOD", "sustenance": "$FOOD",
    "water": "$WATER", "h2o": "$WATER", "aqua": "$WATER",
    "author": "$AUTHOR", "writer": "$AUTHOR", "novelist": "$AUTHOR", "creator": "$AUTHOR",
    "scientist": "$SCIENTIST", "researcher": "$SCIENTIST", "investigator": "$SCIENTIST",
    "penicillin": "$ANTIBIOTIC", "antibiotic": "$ANTIBIOTIC",
    "telephone": "$COMM_DEVICE", "phone": "$COMM_DEVICE",
    "internet": "$NETWORK", "web": "$NETWORK",
    "bone": "$BONE",
    "patient": "$PATIENT", "sick": "$PATIENT",
    "king": "$MONARCH", "queen": "$MONARCH", "monarch": "$MONARCH",
    "city": "$CITY", "town": "$CITY", "village": "$CITY",
    "river": "$WATERWAY", "stream": "$WATERWAY", "creek": "$WATERWAY",
    "mountain": "$MOUNTAIN", "hill": "$MOUNTAIN", "peak": "$MOUNTAIN",
    "tree": "$TREE", "plant": "$TREE", "shrub": "$TREE",
    "flower": "$FLOWER", "blossom": "$FLOWER", "bloom": "$FLOWER",
    "bird": "$BIRD", "avian": "$BIRD",
    "fish": "$FISH", "aquatic": "$FISH",
    "horse": "$EQUINE", "pony": "$EQUINE", "stallion": "$EQUINE",
    "cow": "$BOVINE", "bull": "$BOVINE", "cattle": "$BOVINE",
    "pig": "$PORCINE", "hog": "$PORCINE", "swine": "$PORCINE",
    "sheep": "$OVINE", "lamb": "$OVINE", "ram": "$OVINE",
    "goat": "$CAPRINE", "bear": "$URSID",
    "wolf": "$LUPINE", "coyote": "$LUPINE", "fox": "$VULPINE",
    "deer": "$CERVINE", "elk": "$CERVINE", "moose": "$CERVINE",
    "rabbit": "$LEPORID", "hare": "$LEPORID",
    "snake": "$SERPENT", "serpent": "$SERPENT",
    "turtle": "$TESTUDINE", "tortoise": "$TESTUDINE",
    "frog": "$ANURAN", "toad": "$ANURAN",
    "butterfly": "$LEPIDOPTERAN", "moth": "$LEPIDOPTERAN",
    "bee": "$APINE", "wasp": "$APINE", "hornet": "$APINE",
    "ant": "$FORMICID", "spider": "$ARACHNID",
    "crab": "$CRUSTACEAN", "lobster": "$CRUSTACEAN", "shrimp": "$CRUSTACEAN",
    "dolphin": "$CETACEAN", "whale": "$CETACEAN", "porpoise": "$CETACEAN",
    "seal": "$PINNIPED", "walrus": "$PINNIPED", "bat": "$CHIROPTERAN",
    "elephant": "$PROBOSCID", "giraffe": "$GIRAFFID",
    "zebra": "$EQUID", "donkey": "$EQUID", "mule": "$EQUID",
    "camel": "$CAMELID", "llama": "$CAMELID", "alpaca": "$CAMELID",
    "monkey": "$PRIMATE", "ape": "$PRIMATE", "gorilla": "$PRIMATE",
    "chimpanzee": "$PRIMATE", "orangutan": "$PRIMATE",
    "lion": "$FELID_LARGE", "tiger": "$FELID_LARGE", "leopard": "$FELID_LARGE",
    "jaguar": "$FELID_LARGE", "cheetah": "$FELID_LARGE", "panther": "$FELID_LARGE",
    "cougar": "$FELID_LARGE", "lynx": "$FELID_LARGE", "bobcat": "$FELID_LARGE",
    "shark": "$SELACHII",
    "eagle": "$ACCIPITRID", "hawk": "$ACCIPITRID", "falcon": "$ACCIPITRID",
    "vulture": "$ACCIPITRID", "kite": "$ACCIPITRID",
    "owl": "$STRIGID", "parrot": "$PSITTACID", "macaw": "$PSITTACID",
    "cockatoo": "$PSITTACID", "penguin": "$SPHENISCID",
    "duck": "$ANATID", "goose": "$ANATID", "swan": "$ANATID",
    "chicken": "$PHASIANID", "rooster": "$PHASIANID", "hen": "$PHASIANID",
    "turkey": "$MELEAGRID", "peacock": "$PAVONID", "ostrich": "$STRUTHIONID",
    "crocodile": "$CROCODILIAN", "alligator": "$CROCODILIAN", "caiman": "$CROCODILIAN",
    "lizard": "$SQUAMATE", "gecko": "$SQUAMATE", "iguana": "$SQUAMATE",
    "chameleon": "$SQUAMATE", "salamander": "$URODELAN", "newt": "$URODELAN",
    "clam": "$BIVALVE", "mussel": "$BIVALVE", "oyster": "$BIVALVE",
    "snail": "$GASTROPOD", "slug": "$GASTROPOD",
    "worm": "$ANNELID", "earthworm": "$ANNELID", "leech": "$HIRUDINID",
    "starfish": "$ASTEROID", "jellyfish": "$CNIDARIAN", "sponge": "$PORIFERAN",
    "coral": "$ANTHOZOAN", "seaweed": "$ALGA", "algae": "$ALGA",
    "mushroom": "$FUNGUS", "fungus": "$FUNGUS", "mold": "$FUNGUS", "yeast": "$FUNGUS",
    "bacteria": "$BACTERIUM", "germ": "$BACTERIUM", "microbe": "$BACTERIUM",
    "virus": "$VIRUS", "cell": "$CELL", "dna": "$DNA", "rna": "$RNA",
    "protein": "$PROTEIN", "enzyme": "$ENZYME", "hormone": "$HORMONE",
    "vitamin": "$VITAMIN", "mineral": "$MINERAL",
    "metal": "$METAL", "iron": "$METAL", "steel": "$METAL", "copper": "$METAL",
    "bronze": "$METAL", "brass": "$METAL", "gold": "$METAL", "silver": "$METAL",
    "platinum": "$METAL", "aluminum": "$METAL", "tin": "$METAL", "lead": "$METAL",
    "zinc": "$METAL", "nickel": "$METAL", "cobalt": "$METAL", "titanium": "$METAL",
    "uranium": "$METAL", "plutonium": "$METAL",
    "wood": "$WOOD", "timber": "$WOOD", "lumber": "$WOOD",
    "stone": "$STONE", "rock": "$STONE", "boulder": "$STONE", "pebble": "$STONE",
    "glass": "$GLASS", "plastic": "$PLASTIC", "paper": "$PAPER",
    "cloth": "$CLOTH", "fabric": "$CLOTH", "textile": "$CLOTH",
    "leather": "$LEATHER", "rubber": "$RUBBER",
    "ceramic": "$CERAMIC", "pottery": "$CERAMIC", "porcelain": "$CERAMIC",
    "concrete": "$CONCRETE", "brick": "$BRICK", "cement": "$CEMENT",
    "sand": "$SAND", "dirt": "$DIRT", "soil": "$DIRT", "dust": "$DUST",
    "ash": "$ASH", "charcoal": "$CHARCOAL", "coal": "$COAL",
    "oil": "$OIL", "petroleum": "$OIL", "gasoline": "$OIL", "diesel": "$OIL",
    "gas": "$GAS", "natural_gas": "$GAS",
    "electricity": "$ELECTRICITY", "power": "$ELECTRICITY", "energy": "$ELECTRICITY",
    "light": "$LIGHT", "illumination": "$LIGHT",
    "sound": "$SOUND", "noise": "$SOUND",
    "heat": "$HEAT", "thermal": "$HEAT", "temperature": "$HEAT",
    "cold": "$COLD", "wind": "$WIND", "breeze": "$WIND", "gust": "$WIND",
    "rain": "$RAIN", "precipitation": "$RAIN", "rainfall": "$RAIN",
    "snow": "$SNOW", "snowfall": "$SNOW", "ice": "$ICE", "glacier": "$ICE",
    "storm": "$STORM", "hurricane": "$STORM", "tornado": "$STORM",
    "cyclone": "$STORM", "typhoon": "$STORM",
    "earthquake": "$EARTHQUAKE", "quake": "$EARTHQUAKE", "tremor": "$EARTHQUAKE",
    "volcano": "$VOLCANO", "tsunami": "$TSUNAMI",
    "flood": "$FLOOD", "inundation": "$FLOOD", "drought": "$DROUGHT",
    "fire": "$FIRE", "flame": "$FIRE", "blaze": "$FIRE",
    "explosion": "$EXPLOSION", "blast": "$EXPLOSION", "detonation": "$EXPLOSION",
    "war": "$WAR", "battle": "$WAR", "conflict": "$WAR", "combat": "$WAR", "warfare": "$WAR",
    "peace": "$PEACE",
    "love": "$LOVE", "affection": "$LOVE", "adoration": "$LOVE",
    "hate": "$HATE", "hatred": "$HATE", "loathing": "$HATE",
    "fear": "$FEAR", "terror": "$FEAR", "dread": "$FEAR", "horror": "$FEAR",
    "anger": "$ANGER", "rage": "$ANGER", "fury": "$ANGER", "wrath": "$ANGER",
    "sadness": "$SADNESS", "sorrow": "$SADNESS", "grief": "$SADNESS", "melancholy": "$SADNESS",
    "joy": "$JOY", "happiness": "$JOY", "delight": "$JOY", "elation": "$JOY",
    "surprise": "$SURPRISE", "astonishment": "$SURPRISE", "amazement": "$SURPRISE",
    "disgust": "$DISGUST", "revulsion": "$DISGUST", "repulsion": "$DISGUST",
    "trust": "$TRUST", "confidence": "$TRUST", "faith": "$TRUST",
    "distrust": "$DISTRUST", "mistrust": "$DISTRUST", "suspicion": "$DISTRUST",
    "courage": "$COURAGE", "bravery": "$COURAGE", "valor": "$COURAGE", "heroism": "$COURAGE",
    "cowardice": "$COWARDICE", "timidity": "$COWARDICE",
    "wisdom": "$WISDOM", "knowledge": "$WISDOM", "intelligence": "$WISDOM", "sagacity": "$WISDOM",
    "foolishness": "$FOOLISHNESS", "stupidity": "$FOOLISHNESS", "ignorance": "$FOOLISHNESS",
    "beauty": "$BEAUTY", "loveliness": "$BEAUTY", "prettiness": "$BEAUTY",
    "ugliness": "$UGLINESS",
    "strength": "$STRENGTH", "force": "$STRENGTH", "might": "$STRENGTH",
    "weakness": "$WEAKNESS", "frailty": "$WEAKNESS",
    "speed": "$SPEED", "velocity": "$SPEED", "swiftness": "$SPEED",
    "size": "$SIZE", "dimension": "$SIZE", "magnitude": "$SIZE",
    "color": "$COLOR", "colour": "$COLOR", "hue": "$COLOR", "shade": "$COLOR", "tint": "$COLOR",
    "shape": "$SHAPE", "form": "$SHAPE", "figure": "$SHAPE",
    "texture": "$TEXTURE",
    "smell": "$SMELL", "odor": "$SMELL", "fragrance": "$SMELL", "aroma": "$SMELL", "scent": "$SMELL",
    "taste": "$TASTE", "flavor": "$TASTE", "savor": "$TASTE",
    "touch": "$TOUCH", "feel": "$TOUCH",
    "sight": "$SIGHT", "vision": "$SIGHT", "eyesight": "$SIGHT",
    "hearing": "$HEARING", "audition": "$HEARING",
    "speech": "$SPEECH", "language": "$SPEECH", "tongue": "$SPEECH",
    "thought": "$THOUGHT", "idea": "$THOUGHT", "concept": "$THOUGHT", "notion": "$THOUGHT",
    "dream": "$DREAM", "nightmare": "$DREAM",
    "memory": "$MEMORY", "recollection": "$MEMORY", "remembrance": "$MEMORY",
    "imagination": "$IMAGINATION", "fantasy": "$IMAGINATION", "fancy": "$IMAGINATION",
    "truth": "$TRUTH", "fact": "$TRUTH", "reality": "$TRUTH",
    "lie": "$LIE", "falsehood": "$LIE", "untruth": "$LIE", "deception": "$LIE",
    "justice": "$JUSTICE", "fairness": "$JUSTICE", "equity": "$JUSTICE",
    "injustice": "$INJUSTICE", "unfairness": "$INJUSTICE",
    "freedom": "$FREEDOM", "liberty": "$FREEDOM", "independence": "$FREEDOM",
    "slavery": "$SLAVERY", "bondage": "$SLAVERY", "servitude": "$SLAVERY",
    "democracy": "$DEMOCRACY", "republic": "$DEMOCRACY",
    "dictatorship": "$DICTATORSHIP", "autocracy": "$DICTATORSHIP", "tyranny": "$DICTATORSHIP",
    "monarchy": "$MONARCHY", "kingdom": "$MONARCHY", "empire": "$MONARCHY",
    "government": "$GOVERNMENT", "administration": "$GOVERNMENT", "regime": "$GOVERNMENT",
    "country": "$COUNTRY", "nation": "$COUNTRY", "state": "$COUNTRY", "land": "$COUNTRY",
    "ocean": "$OCEAN", "sea": "$OCEAN", "marine": "$OCEAN",
    "desert": "$DESERT", "forest": "$FOREST", "woods": "$FOREST", "jungle": "$FOREST",
    "island": "$ISLAND", "isle": "$ISLAND", "peninsula": "$PENINSULA",
    "continent": "$CONTINENT",
    "universe": "$UNIVERSE", "cosmos": "$UNIVERSE",
    "space": "$SPACE", "outer_space": "$SPACE",
    "star": "$STAR", "sun": "$STAR", "solar": "$STAR",
    "moon": "$MOON", "lunar": "$MOON", "planet": "$PLANET",
    "galaxy": "$GALAXY", "asteroid": "$ASTEROID", "comet": "$COMET",
    "meteor": "$METEOR", "black_hole": "$BLACK_HOLE", "nebula": "$NEBULA",
    "constellation": "$CONSTELLATION", "orbit": "$ORBIT",
    "gravity": "$GRAVITY", "gravitation": "$GRAVITY",
    "magnetism": "$MAGNETISM", "magnetic": "$MAGNETISM",
    "radiation": "$RADIATION", "radioactive": "$RADIATION",
    "atom": "$ATOM", "atomic": "$ATOM", "molecule": "$MOLECULE", "molecular": "$MOLECULE",
    "element": "$ELEMENT", "chemical": "$ELEMENT", "compound": "$COMPOUND",
    "mixture": "$MIXTURE", "solution": "$SOLUTION", "acid": "$ACID",
    "base": "$BASE", "alkali": "$BASE", "salt": "$SALT",
    "oxidation": "$OXIDATION", "reduction": "$REDUCTION", "catalyst": "$CATALYST",
    "reaction": "$REACTION", "synthesis": "$SYNTHESIS", "analysis": "$ANALYSIS",
    "experiment": "$EXPERIMENT", "theory": "$THEORY", "hypothesis": "$THEORY", "conjecture": "$THEORY",
    "principle": "$PRINCIPLE", "model": "$MODEL", "paradigm": "$MODEL",
    "system": "$SYSTEM", "process": "$PROCESS", "procedure": "$PROCESS",
    "method": "$METHOD", "technique": "$METHOD", "methodology": "$METHOD",
    "tool": "$TOOL", "instrument": "$TOOL", "implement": "$TOOL", "device": "$TOOL", "apparatus": "$TOOL",
    "machine": "$MACHINE", "engine": "$MACHINE", "motor": "$MACHINE",
    "computer": "$COMPUTER", "processor": "$COMPUTER",
    "robot": "$ROBOT", "automaton": "$ROBOT", "android": "$ROBOT",
    "sensor": "$SENSOR", "detector": "$SENSOR", "algorithm": "$ALGORITHM",
    "data": "$DATA", "information": "$DATA", "info": "$DATA",
    "code": "$CODE", "program": "$CODE", "software": "$CODE",
    "hardware": "$HARDWARE", "network": "$NETWORK", "database": "$DATABASE", "db": "$DATABASE",
    "server": "$SERVER", "client": "$CLIENT", "user": "$USER",
    "password": "$PASSWORD", "passcode": "$PASSWORD",
    "encryption": "$ENCRYPTION", "cipher": "$ENCRYPTION", "decryption": "$DECRYPTION",
    "authentication": "$AUTHENTICATION", "auth": "$AUTHENTICATION", "authorization": "$AUTHORIZATION",
    "security": "$SECURITY", "safety": "$SECURITY", "privacy": "$PRIVACY",
    "identity": "$IDENTITY", "access": "$ACCESS", "permission": "$PERMISSION",
    "error": "$ERROR", "mistake": "$ERROR", "bug": "$ERROR", "fault": "$ERROR",
    "warning": "$WARNING", "alert": "$WARNING", "success": "$SUCCESS", "failure": "$FAILURE",
    "risk": "$RISK", "benefit": "$BENEFIT", "advantage": "$BENEFIT",
    "disadvantage": "$DISADVANTAGE", "drawback": "$DISADVANTAGE",
    "cost": "$COST", "expense": "$COST", "price": "$COST",
    "value": "$VALUE", "worth": "$VALUE", "quality": "$QUALITY",
    "quantity": "$QUANTITY", "amount": "$QUANTITY",
    "number": "$NUMBER", "numeral": "$NUMBER", "digit": "$NUMBER",
    "letter": "$LETTER", "character": "$LETTER", "alphabet": "$LETTER",
    "word": "$WORD", "term": "$WORD", "vocabulary": "$WORD",
    "sentence": "$SENTENCE", "phrase": "$SENTENCE", "clause": "$SENTENCE",
    "paragraph": "$PARAGRAPH", "document": "$DOCUMENT", "file": "$DOCUMENT", "text": "$DOCUMENT",
    "page": "$PAGE", "chapter": "$CHAPTER", "section": "$CHAPTER",
    "article": "$ARTICLE", "essay": "$ARTICLE", "report": "$REPORT", "study": "$REPORT",
    "review": "$REVIEW", "summary": "$SUMMARY", "abstract": "$SUMMARY", "synopsis": "$SUMMARY",
    "index": "$INDEX", "table": "$TABLE", "chart": "$TABLE", "graph": "$TABLE", "diagram": "$TABLE",
    "figure": "$FIGURE", "illustration": "$FIGURE", "image": "$FIGURE", "picture": "$FIGURE",
    "map": "$MAP", "list": "$LIST", "catalog": "$LIST", "catalogue": "$LIST", "inventory": "$LIST",
    "schedule": "$SCHEDULE", "timetable": "$SCHEDULE", "calendar": "$CALENDAR",
    "clock": "$CLOCK", "watch": "$CLOCK", "timer": "$CLOCK", "date": "$DATE", "time": "$TIME",
    "year": "$YEAR", "month": "$YEAR", "week": "$YEAR", "day": "$YEAR",
    "hour": "$HOUR", "minute": "$HOUR", "second": "$HOUR",
    "morning": "$MORNING", "afternoon": "$MORNING", "evening": "$MORNING", "night": "$MORNING",
    "dawn": "$DAWN", "dusk": "$DAWN", "twilight": "$DAWN",
    "spring": "$SPRING", "summer": "$SPRING", "autumn": "$SPRING", "winter": "$SPRING",
    "birth": "$BIRTH", "birthday": "$BIRTH", "death": "$DEATH", "demise": "$DEATH",
    "life": "$LIFE", "age": "$AGE", "generation": "$GENERATION",
    "family": "$FAMILY", "relatives": "$FAMILY", "kin": "$FAMILY",
    "parent": "$PARENT", "father": "$PARENT", "mother": "$PARENT", "mom": "$PARENT", "dad": "$PARENT",
    "child": "$CHILD", "son": "$CHILD", "daughter": "$CHILD", "kid": "$CHILD",
    "sibling": "$SIBLING", "brother": "$SIBLING", "sister": "$SIBLING",
    "grandparent": "$GRANDPARENT", "grandfather": "$GRANDPARENT", "grandmother": "$GRANDPARENT",
    "grandchild": "$GRANDCHILD", "grandson": "$GRANDCHILD", "granddaughter": "$GRANDCHILD",
    "uncle": "$UNCLE", "aunt": "$UNCLE", "nephew": "$NEPHEW", "niece": "$NEPHEW",
    "cousin": "$COUSIN", "husband": "$SPOUSE", "wife": "$SPOUSE", "spouse": "$SPOUSE",
    "friend": "$FRIEND", "companion": "$FRIEND", "ally": "$FRIEND",
    "enemy": "$ENEMY", "foe": "$ENEMY", "adversary": "$ENEMY",
    "neighbor": "$NEIGHBOR", "neighbour": "$NEIGHBOR", "stranger": "$STRANGER",
    "guest": "$GUEST", "host": "$HOST", "owner": "$OWNER", "possessor": "$OWNER",
    "master": "$MASTER", "servant": "$SERVANT", "slave": "$SLAVE",
    "leader": "$LEADER", "chief": "$LEADER", "head": "$LEADER", "follower": "$FOLLOWER",
    "member": "$MEMBER", "citizen": "$CITIZEN",
    "foreigner": "$FOREIGNER", "alien": "$FOREIGNER", "native": "$NATIVE", "indigenous": "$NATIVE",
    "immigrant": "$IMMIGRANT", "migrant": "$IMMIGRANT", "refugee": "$REFUGEE",
    "prisoner": "$PRISONER", "captive": "$PRISONER", "inmate": "$PRISONER",
    "guard": "$GUARD", "warden": "$GUARD", "police": "$POLICE", "officer": "$POLICE",
    "soldier": "$SOLDIER", "warrior": "$SOLDIER", "fighter": "$SOLDIER",
    "general": "$GENERAL", "commander": "$GENERAL", "captain": "$CAPTAIN",
    "pilot": "$PILOT", "aviator": "$PILOT", "driver": "$DRIVER", "chauffeur": "$DRIVER",
    "teacher": "$TEACHER", "instructor": "$TEACHER", "educator": "$TEACHER", "professor": "$TEACHER",
    "student": "$STUDENT", "pupil": "$STUDENT", "principal": "$PRINCIPAL",
    "lawyer": "$LAWYER", "attorney": "$LAWYER", "counsel": "$LAWYER",
    "judge": "$JUDGE", "jury": "$JURY", "witness": "$WITNESS",
    "criminal": "$CRIMINAL", "offender": "$CRIMINAL", "perpetrator": "$CRIMINAL",
    "victim": "$VICTIM", "hero": "$HERO", "villain": "$VILLAIN",
    "angel": "$ANGEL", "devil": "$DEVIL", "demon": "$DEVIL", "satan": "$DEVIL",
    "god": "$GOD", "deity": "$GOD", "divine": "$GOD",
    "spirit": "$SPIRIT", "ghost": "$SPIRIT", "phantom": "$SPIRIT",
    "soul": "$SOUL", "mind": "$MIND", "psyche": "$MIND",
    "body": "$BODY", "corpse": "$BODY", "heart": "$HEART", "brain": "$BRAIN",
    "blood": "$BLOOD", "skin": "$SKIN", "muscle": "$MUSCLE", "nerve": "$NERVE",
    "vein": "$VEIN", "artery": "$VEIN", "lung": "$LUNG", "liver": "$LIVER",
    "kidney": "$KIDNEY", "stomach": "$STOMACH", "intestine": "$INTESTINE", "bowel": "$INTESTINE",
    "bladder": "$BLADDER", "eye": "$EYE", "ear": "$EAR", "nose": "$NOSE",
    "mouth": "$MOUTH", "tooth": "$TOOTH", "tongue": "$TONGUE",
    "hand": "$HAND", "foot": "$FOOT", "arm": "$ARM", "leg": "$LEG",
    "finger": "$FINGER", "toe": "$TOE", "hair": "$HAIR", "nail": "$NAIL",
    "wing": "$WING", "tail": "$TAIL", "horn": "$HORN", "claw": "$CLAW",
    "hoof": "$HOOF", "fin": "$FIN", "scale": "$SCALE", "feather": "$FEATHER",
    "fur": "$FUR", "wool": "$WOOL", "silk": "$SILK", "cotton": "$COTTON",
    "linen": "$LINEN", "nylon": "$NYLON", "polyester": "$POLYESTER",
    "rayon": "$RAYON", "spandex": "$SPANDEX", "lace": "$LACE", "velvet": "$VELVET",
    "satin": "$SATIN", "denim": "$DENIM", "corduroy": "$CORDUROY", "tweed": "$TWEED",
    "canvas": "$CANVAS", "burlap": "$BURLAP", "hemp": "$HEMP", "jute": "$JUTE",
    "sisal": "$SISAL", "bamboo": "$BAMBOO", "cork": "$CORK", "ivory": "$IVORY",
    "shell": "$SHELL", "pearl": "$PEARL", "amber": "$AMBER", "jet": "$JET",
    "diamond": "$DIAMOND", "ruby": "$RUBY", "sapphire": "$SAPPHIRE", "emerald": "$EMERALD",
    "topaz": "$TOPAZ", "opal": "$OPAL", "amethyst": "$AMETHYST", "turquoise": "$TURQUOISE",
    "lapis": "$LAPIS", "jade": "$JADE", "onyx": "$ONYX", "quartz": "$QUARTZ",
    "granite": "$GRANITE", "marble": "$MARBLE", "slate": "$SLATE", "limestone": "$LIMESTONE",
    "sandstone": "$SANDSTONE", "basalt": "$BASALT", "obsidian": "$OBSIDIAN",
    "pumice": "$PUMICE", "flint": "$FLINT", "chalk": "$CHALK", "clay": "$CLAY",
    "mud": "$MUD", "silt": "$SILT", "gravel": "$GRAVEL", "bedrock": "$BEDROCK",
    "magma": "$MAGMA", "lava": "$LAVA", "soot": "$SOOT", "smoke": "$SMOKE",
    "fog": "$FOG", "mist": "$FOG", "haze": "$FOG", "cloud": "$CLOUD",
    "sky": "$SKY", "air": "$AIR", "atmosphere": "$AIR", "vacuum": "$VACUUM",
    "silence": "$SILENCE", "echo": "$ECHO", "music": "$MUSIC", "song": "$SONG",
    "dance": "$DANCE", "art": "$ART",
    "painting": "$PAINTING", "drawing": "$PAINTING", "sketch": "$PAINTING",
    "sculpture": "$SCULPTURE", "statue": "$SCULPTURE",
    "photograph": "$PHOTOGRAPH", "photo": "$PHOTOGRAPH",
    "film": "$FILM", "movie": "$FILM", "cinema": "$FILM",
    "theater": "$THEATER", "theatre": "$THEATER", "play": "$PLAY", "drama": "$PLAY",
    "poem": "$POEM", "poetry": "$POEM", "story": "$STORY", "tale": "$STORY", "narrative": "$STORY",
    "myth": "$MYTH", "legend": "$MYTH", "history": "$HISTORY",
    "science": "$SCIENCE", "mathematics": "$MATHEMATICS", "math": "$MATHEMATICS",
    "physics": "$PHYSICS", "chemistry": "$CHEMISTRY", "biology": "$BIOLOGY",
    "geology": "$GEOLOGY", "astronomy": "$ASTRONOMY", "philosophy": "$PHILOSOPHY",
    "psychology": "$PSYCHOLOGY", "sociology": "$SOCIOLOGY", "economics": "$ECONOMICS",
    "politics": "$POLITICS", "religion": "$RELIGION", "ethics": "$ETHICS", "logic": "$LOGIC",
    "literature": "$LITERATURE", "grammar": "$GRAMMAR", "spelling": "$SPELLING",
    "pronunciation": "$PRONUNCIATION", "translation": "$TRANSLATION", "interpretation": "$INTERPRETATION",
    "communication": "$COMMUNICATION", "conversation": "$CONVERSATION", "dialogue": "$CONVERSATION",
    "discussion": "$CONVERSATION", "argument": "$ARGUMENT", "debate": "$ARGUMENT", "dispute": "$ARGUMENT",
    "question": "$QUESTION", "query": "$QUESTION", "answer": "$ANSWER", "reply": "$ANSWER",
    "response": "$ANSWER", "request": "$REQUEST", "command": "$COMMAND", "order": "$COMMAND",
    "instruction": "$COMMAND", "suggestion": "$SUGGESTION", "proposal": "$SUGGESTION",
    "recommendation": "$SUGGESTION", "advice": "$ADVICE", "guidance": "$ADVICE",
    "promise": "$PROMISE", "threat": "$THREAT", "compliment": "$COMPLIMENT", "praise": "$COMPLIMENT",
    "insult": "$INSULT", "joke": "$JOKE", "humor": "$JOKE", "secret": "$SECRET",
    "mystery": "$MYSTERY", "puzzle": "$PUZZLE", "riddle": "$PUZZLE", "game": "$GAME",
    "sport": "$SPORT", "race": "$RACE", "competition": "$COMPETITION", "contest": "$COMPETITION",
    "tournament": "$COMPETITION", "prize": "$PRIZE", "award": "$PRIZE", "reward": "$PRIZE",
    "penalty": "$PENALTY", "fine": "$FINE", "tax": "$TAX", "debt": "$DEBT", "loan": "$LOAN",
    "credit": "$CREDIT", "interest": "$INTEREST", "profit": "$PROFIT", "loss": "$LOSS",
    "revenue": "$REVENUE", "income": "$REVENUE", "budget": "$BUDGET", "account": "$ACCOUNT",
    "invoice": "$INVOICE", "bill": "$INVOICE", "receipt": "$RECEIPT", "payment": "$PAYMENT",
    "purchase": "$PURCHASE", "sale": "$SALE", "delivery": "$DELIVERY", "shipping": "$SHIPPING",
    "return": "$RETURN", "refund": "$REFUND", "exchange": "$EXCHANGE", "trade": "$TRADE",
    "business": "$BUSINESS", "commerce": "$BUSINESS",
    "company": "$COMPANY", "firm": "$COMPANY", "corporation": "$COMPANY", "enterprise": "$COMPANY",
    "organization": "$ORGANIZATION", "institution": "$ORGANIZATION",
    "department": "$DEPARTMENT", "division": "$DEPARTMENT", "team": "$TEAM", "group": "$TEAM",
    "committee": "$COMMITTEE", "board": "$BOARD", "council": "$COUNCIL",
    "agency": "$AGENCY", "bureau": "$BUREAU", "office": "$OFFICE",
    "factory": "$FACTORY", "mill": "$FACTORY", "warehouse": "$WAREHOUSE",
    "store": "$STORE", "shop": "$STORE", "market": "$STORE",
    "restaurant": "$RESTAURANT", "cafe": "$RESTAURANT", "café": "$RESTAURANT",
    "hotel": "$HOTEL", "inn": "$HOTEL", "motel": "$HOTEL",
    "hospital": "$HOSPITAL", "clinic": "$HOSPITAL",
    "school": "$SCHOOL", "college": "$SCHOOL", "university": "$SCHOOL", "academy": "$SCHOOL",
    "library": "$LIBRARY", "museum": "$MUSEUM", "stadium": "$STADIUM", "arena": "$STADIUM",
    "park": "$PARK", "garden": "$GARDEN", "farm": "$FARM", "field": "$FIELD",
    "road": "$ROAD", "street": "$ROAD", "highway": "$ROAD", "freeway": "$ROAD",
    "bridge": "$BRIDGE", "tunnel": "$TUNNEL", "railroad": "$RAILROAD", "railway": "$RAILROAD",
    "airport": "$AIRPORT", "station": "$STATION", "port": "$PORT", "harbor": "$PORT",
    "wall": "$WALL", "gate": "$GATE", "door": "$DOOR", "window": "$WINDOW",
    "floor": "$FLOOR", "ceiling": "$CEILING", "roof": "$ROOF",
    "stair": "$STAIR", "step": "$STAIR", "elevator": "$ELEVATOR", "lift": "$ELEVATOR",
    "escalator": "$ESCALATOR", "ramp": "$RAMP", "hall": "$HALL", "corridor": "$HALL",
    "room": "$ROOM", "bedroom": "$BEDROOM", "kitchen": "$KITCHEN", "bathroom": "$BATHROOM",
    "living_room": "$LIVING_ROOM", "dining_room": "$DINING_ROOM", "basement": "$BASEMENT",
    "attic": "$ATTIC", "garage": "$GARAGE", "balcony": "$BALCONY", "porch": "$PORCH",
    "deck": "$DECK", "patio": "$PATIO", "yard": "$YARD", "fence": "$FENCE", "pool": "$POOL",
    "gym": "$GYM", "cubicle": "$CUBICLE", "desk": "$DESK", "chair": "$CHAIR",
    "couch": "$COUCH", "sofa": "$COUCH", "bed": "$BED", "lamp": "$LAMP",
    "fan": "$FAN", "heater": "$HEATER", "air_conditioner": "$AIR_CONDITIONER",
    "refrigerator": "$REFRIGERATOR", "fridge": "$REFRIGERATOR", "oven": "$OVEN",
    "stove": "$STOVE", "microwave": "$MICROWAVE", "dishwasher": "$DISHWASHER",
    "washer": "$WASHER", "dryer": "$DRYER", "broom": "$BROOM", "mop": "$MOP",
    "bucket": "$BUCKET", "trash": "$TRASH", "garbage": "$TRASH", "rubbish": "$TRASH",
    "recycling": "$RECYCLING", "compost": "$COMPOST", "soap": "$SOAP", "shampoo": "$SHAMPOO",
    "conditioner": "$CONDITIONER", "toothpaste": "$TOOTHPASTE", "toothbrush": "$TOOTHBRUSH",
    "towel": "$TOWEL", "blanket": "$BLANKET", "pillow": "$PILLOW", "sheet": "$SHEET",
    "curtain": "$CURTAIN", "blind": "$BLIND", "cushion": "$CUSHION", "quilt": "$QUILT",
    "comforter": "$COMFORTER", "duvet": "$DUVET", "mattress": "$MATTRESS", "frame": "$FRAME",
    "mirror": "$MIRROR", "poster": "$POSTER", "vase": "$VASE", "bowl": "$BOWL",
    "plate": "$PLATE", "cup": "$CUP", "mug": "$MUG", "bottle": "$BOTTLE", "jar": "$JAR",
    "can": "$CAN", "box": "$BOX", "bag": "$BAG", "sack": "$SACK", "basket": "$BASKET",
    "crate": "$CRATE", "barrel": "$BARREL", "drum": "$DRUM", "tank": "$TANK",
    "tube": "$TUBE", "pipe": "$PIPE", "hose": "$HOSE", "cable": "$CABLE", "wire": "$WIRE",
    "rope": "$ROPE", "chain": "$CHAIN", "string": "$STRING", "thread": "$THREAD",
    "yarn": "$YARN", "ribbon": "$RIBBON", "belt": "$BELT", "strap": "$STRAP",
    "handle": "$HANDLE", "knob": "$KNOB", "button": "$BUTTON", "switch": "$SWITCH",
    "dial": "$DIAL", "lever": "$LEVER", "pedal": "$PEDAL", "key": "$KEY", "lock": "$LOCK",
    "padlock": "$PADLOCK", "ladder": "$LADDER", "scaffold": "$SCAFFOLD",
    "platform": "$PLATFORM", "stage": "$STAGE", "screen": "$SCREEN", "display": "$DISPLAY",
    "monitor": "$MONITOR", "keyboard": "$KEYBOARD", "mouse": "$MOUSE", "printer": "$PRINTER",
    "scanner": "$SCANNER", "speaker": "$SPEAKER", "headphone": "$HEADPHONE",
    "microphone": "$MICROPHONE", "camera": "$CAMERA", "projector": "$PROJECTOR",
    "router": "$ROUTER", "modem": "$MODEM", "antenna": "$ANTENNA", "satellite": "$SATELLITE",
    "telescope": "$TELESCOPE", "microscope": "$MICROSCOPE", "binocular": "$BINOCULAR",
    "magnifying_glass": "$MAGNIFYING_GLASS", "compass": "$COMPASS", "ruler": "$RULER",
    "tape": "$TAPE", "scissors": "$SCISSORS", "knife": "$KNIFE", "fork": "$FORK",
    "spoon": "$SPOON", "chopstick": "$CHOPSTICK", "pan": "$PAN", "pot": "$POT",
    "skillet": "$SKILLET", "grill": "$GRILL", "barbecue": "$BARBECUE", "smoker": "$SMOKER",
    "roaster": "$ROASTER", "broiler": "$BROILER", "toaster": "$TOASTER", "blender": "$BLENDER",
    "mixer": "$MIXER", "grinder": "$GRINDER", "mortar": "$MORTAR", "pestle": "$PESTLE",
    "rolling_pin": "$ROLLING_PIN", "whisk": "$WHISK", "spatula": "$SPATULA", "ladle": "$LADLE",
    "colander": "$COLANDER", "strainer": "$STRAINER", "sieve": "$SIEVE", "funnel": "$FUNNEL",
    "measuring_cup": "$MEASURING_CUP", "measuring_spoon": "$MEASURING_SPOON",
    "kitchen_scale": "$KITCHEN_SCALE", "thermometer": "$THERMOMETER", "alarm": "$ALARM",
    "bell": "$BELL", "buzzer": "$BUZZER", "siren": "$SIREN", "whistle": "$WHISTLE",
    "trumpet": "$TRUMPET", "trombone": "$TROMBONE", "french_horn": "$FRENCH_HORN",
    "tuba": "$TUBA", "violin": "$VIOLIN", "viola": "$VIOLA", "cello": "$CELLO",
    "bass": "$BASS", "harp": "$HARP", "piano": "$PIANO", "organ": "$ORGAN",
    "accordion": "$ACCORDION", "harmonica": "$HARMONICA", "guitar": "$GUITAR",
    "ukulele": "$UKULELE", "banjo": "$BANJO", "mandolin": "$MANDOLIN",
    "cymbal": "$CYMBAL", "triangle": "$TRIANGLE", "xylophone": "$XYLOPHONE",
    "marimba": "$MARIMBA", "vibraphone": "$VIBRAPHONE", "glockenspiel": "$GLOCKENSPIEL",
    "chime": "$CHIME", "gong": "$GONG", "tambourine": "$TAMBOURINE", "shaker": "$SHAKER",
    "rattle": "$RATTLE", "maraca": "$MARACA", "castanet": "$CASTANET",
    "flute": "$FLUTE", "piccolo": "$PICCOLO", "clarinet": "$CLARINET", "oboe": "$OBOE",
    "bassoon": "$BASSOON", "saxophone": "$SAXOPHONE", "recorder": "$RECORDER",
    "bagpipe": "$BAGPIPE", "didgeridoo": "$DIDGERIDOO", "synthesizer": "$SYNTHESIZER",
    "drum_machine": "$DRUM_MACHINE", "sampler": "$SAMPLER", "sequencer": "$SEQUENCER",
    "amplifier": "$AMPLIFIER", "earphone": "$EARPHONE", "receiver": "$RECEIVER",
    "transmitter": "$TRANSMITTER", "transceiver": "$TRANSCEIVER", "radio": "$RADIO",
    "television": "$TELEVISION", "tv": "$TELEVISION", "remote": "$REMOTE",
    "battery": "$BATTERY", "charger": "$CHARGER", "adapter": "$ADAPTER",
    "converter": "$CONVERTER", "transformer": "$TRANSFORMER", "inverter": "$INVERTER",
    "rectifier": "$RECTIFIER", "generator": "$GENERATOR", "alternator": "$ALTERNATOR",
    "dynamo": "$DYNAMO", "turbine": "$TURBINE", "pump": "$PUMP", "compressor": "$COMPRESSOR",
    "blower": "$BLOWER", "cooler": "$COOLER", "radiator": "$RADIATOR",
    "condenser": "$CONDENSER", "evaporator": "$EVAPORATOR", "boiler": "$BOILER",
    "furnace": "$FURNACE", "kiln": "$KILN", "range": "$RANGE", "cooktop": "$COOKTOP",
    "griddle": "$GRIDDLE", "wok": "$WOK", "steamer": "$STEAMER",
    "pressure_cooker": "$PRESSURE_COOKER", "slow_cooker": "$SLOW_COOKER",
    "rice_cooker": "$RICE_COOKER", "bread_machine": "$BREAD_MACHINE",
    "ice_cream_maker": "$ICE_CREAM_MAKER", "yogurt_maker": "$YOGURT_MAKER",
    "dehydrator": "$DEHYDRATOR", "sous_vide": "$SOUS_VIDE",
    "immersion_blender": "$IMMERSION_BLENDER", "hand_mixer": "$HAND_MIXER",
    "stand_mixer": "$STAND_MIXER", "food_processor": "$FOOD_PROCESSOR",
    "juicer": "$JUICER", "extractor": "$EXTRACTOR", "centrifuge": "$CENTRIFUGE",
    "separator": "$SEPARATOR", "filter": "$FILTER", "dropper": "$DROPPER",
    "pipette": "$PIPETTE", "syringe": "$SYRINGE", "needle": "$NEEDLE",
    "scalpel": "$SCALPEL", "lancet": "$LANCET", "forceps": "$FORCEPS",
    "tweezers": "$TWEEZERS", "clamp": "$CLAMP", "retractor": "$RETRACTOR",
    "speculum": "$SPECULUM", "dilator": "$DILATOR", "catheter": "$CATHETER",
    "drain": "$DRAIN", "shunt": "$SHUNT", "stent": "$STENT", "graft": "$GRAFT",
    "implant": "$IMPLANT", "prosthesis": "$PROSTHESIS", "pacemaker": "$PACEMAKER",
    "defibrillator": "$DEFIBRILLATOR", "ventilator": "$VENTILATOR",
    "respirator": "$RESPIRATOR", "incubator": "$INCUBATOR", "warmer": "$WARMER",
    "bandage": "$BANDAGE", "gauze": "$GAUZE", "splint": "$SPLINT", "cast": "$CAST",
    "sling": "$SLING", "brace": "$BRACE", "collar": "$COLLAR", "crutch": "$CRUTCH",
    "cane": "$CANE", "walker": "$WALKER", "wheelchair": "$WHEELCHAIR",
    "stretcher": "$STRETCHER", "gurney": "$GURNEY", "stool": "$STOOL",
    "bench": "$BENCH", "seat": "$SEAT", "loveseat": "$LOVESEAT",
    "recliner": "$RECLINER", "rocking_chair": "$ROCKING_CHAIR", "ottoman": "$OTTOMAN",
    "footstool": "$FOOTSTOOL", "hassock": "$HASSOCK", "runner": "$RUNNER",
    "doormat": "$DOORMAT", "bathmat": "$BATHMAT", "washcloth": "$WASHCLOTH",
    "comb": "$COMB", "hairbrush": "$HAIRBRUSH", "floss": "$FLOSS",
    "toothpick": "$TOOTHPICK", "razor": "$RAZOR", "shaver": "$SHAVER",
    "trimmer": "$TRIMMER", "clipper": "$CLIPPER", "shears": "$SHEARS",
    "clippers": "$CLIPPERS", "nail_clipper": "$NAIL_CLIPPER", "nail_file": "$NAIL_FILE",
    "emery_board": "$EMERY_BOARD", "cuticle_stick": "$CUTICLE_STICK",
    "eyelash_curler": "$EYELASH_CURLER", "eyebrow_brush": "$EYEBROW_BRUSH",
    "makeup_brush": "$MAKEUP_BRUSH", "applicator": "$APPLICATOR", "puff": "$PUFF",
    "powder": "$POWDER", "foundation": "$FOUNDATION", "concealer": "$CONCEALER",
    "blush": "$BLUSH", "bronzer": "$BRONZER", "highlighter": "$HIGHLIGHTER",
    "eyeshadow": "$EYESHADOW", "eyeliner": "$EYELINER", "mascara": "$MASCARA",
    "lipstick": "$LIPSTICK", "lip_gloss": "$LIP_GLOSS", "lip_liner": "$LIP_LINER",
    "lip_balm": "$LIP_BALM", "moisturizer": "$MOISTURIZER", "sunscreen": "$SUNSCREEN",
    "serum": "$SERUM", "toner": "$TONER", "cleanser": "$CLEANSER",
    "exfoliator": "$EXFOLIATOR", "mask": "$MASK", "peel": "$PEEL", "scrub": "$SCRUB",
    "lotion": "$LOTION", "cream": "$CREAM", "ointment": "$OINTMENT", "gel": "$GEL",
    "spray": "$SPRAY", "aerosol": "$AEROSOL", "foam": "$FOAM", "mousse": "$MOUSSE",
    "wax": "$WAX", "polish": "$POLISH", "varnish": "$VARNISH", "paint": "$PAINT",
    "dye": "$DYE", "stain": "$STAIN", "ink": "$INK", "glue": "$GLUE",
    "adhesive": "$ADHESIVE", "paste": "$PASTE", "putty": "$PUTTY", "caulk": "$CAULK",
    "sealant": "$SEALANT", "gasket": "$GASKET", "o_ring": "$O_RING",
    "bearing": "$BEARING", "bushing": "$BUSHING", "sleeve": "$SLEEVE",
    "coupling": "$COUPLING", "fitting": "$FITTING", "connector": "$CONNECTOR",
    "transducer": "$TRANSDUCER", "probe": "$PROBE", "electrode": "$ELECTRODE",
    "terminal": "$TERMINAL", "contact": "$CONTACT", "plug": "$PLUG", "jack": "$JACK",
    "socket": "$SOCKET", "receptacle": "$RECEPTACLE", "outlet": "$OUTLET",
    "breaker": "$BREAKER", "fuse": "$FUSE", "relay": "$RELAY", "contactor": "$CONTACTOR",
    "solenoid": "$SOLENOID", "actuator": "$ACTUATOR", "valve": "$VALVE",
    "regulator": "$REGULATOR", "controller": "$CONTROLLER", "counter": "$COUNTER",
    "meter": "$METER", "gauge": "$GAUGE", "indicator": "$INDICATOR",
    "annunciator": "$ANNUNCIATOR", "beacon": "$BEACON", "bulb": "$BULB",
    "led": "$LED", "laser": "$LASER", "diode": "$DIODE", "transistor": "$TRANSISTOR",
    "thyristor": "$THYRISTOR", "triac": "$TRIAC", "scr": "$SCR", "mosfet": "$MOSFET",
    "igbt": "$IGBT", "optoisolator": "$OPTOISOLATOR", "photocoupler": "$PHOTOCOUPLER",
    "photodetector": "$PHOTODETECTOR", "photodiode": "$PHOTODIODE",
    "phototransistor": "$PHOTOTRANSISTOR", "solar_cell": "$SOLAR_CELL",
    "photovoltaic": "$PHOTOVOLTAIC", "fuel_cell": "$FUEL_CELL",
    "capacitor": "$CAPACITOR", "inductor": "$INDUCTOR", "resistor": "$RESISTOR",
    "potentiometer": "$POTENTIOMETER", "rheostat": "$RHEOSTAT", "thermistor": "$THERMISTOR",
    "varistor": "$VARISTOR", "choke": "$CHOKE", "coil": "$COIL", "winding": "$WINDING",
    "core": "$CORE", "magnet": "$MAGNET", "electromagnet": "$ELECTROMAGNET",
    # ── Actions / Verbs ──
    "sit": "$REST_POS", "rest": "$REST_POS", "perch": "$REST_POS", "settle": "$REST_POS", "lie": "$REST_POS",
    "buy": "$ACQUIRE", "purchase": "$ACQUIRE", "acquire": "$ACQUIRE", "obtain": "$ACQUIRE",
    "discover": "$DISCOVER", "find": "$DISCOVER", "uncover": "$DISCOVER", "detect": "$DISCOVER",
    "invent": "$CREATE", "create": "$CREATE", "develop": "$CREATE", "devise": "$CREATE",
    "build": "$CREATE", "construct": "$CREATE",
    "destroy": "$DESTROY", "ruin": "$DESTROY", "demolish": "$DESTROY", "annihilate": "$DESTROY",
    "eat": "$CONSUME", "consume": "$CONSUME", "ingest": "$CONSUME", "devour": "$CONSUME",
    "write": "$WRITE", "compose": "$WRITE", "pen": "$WRITE",
    "say": "$ASSERT", "state": "$ASSERT", "declare": "$ASSERT", "claim": "$ASSERT",
    "assert": "$ASSERT", "mention": "$ASSERT",
    "cause": "$CAUSE", "produce": "$CAUSE", "generate": "$CAUSE", "trigger": "$CAUSE", "induce": "$CAUSE",
    "prevent": "$PREVENT", "stop": "$PREVENT", "avert": "$PREVENT", "block": "$PREVENT", "inhibit": "$PREVENT",
    "increase": "$INCREASE", "grow": "$INCREASE", "expand": "$INCREASE", "rise": "$INCREASE", "boost": "$INCREASE",
    "decrease": "$DECREASE", "reduce": "$DECREASE", "drop": "$DECREASE", "decline": "$DECREASE", "shrink": "$DECREASE",
    "begin": "$START", "start": "$START", "commence": "$START", "initiate": "$START",
    "end": "$END", "finish": "$END", "terminate": "$END", "conclude": "$END",
    "help": "$ASSIST", "assist": "$ASSIST", "aid": "$ASSIST", "support": "$ASSIST",
    "use": "$USE", "utilize": "$USE", "employ": "$USE",
    "show": "$SHOW", "demonstrate": "$SHOW", "display": "$SHOW", "reveal": "$SHOW", "indicate": "$SHOW",
    "kill": "$KILL", "slay": "$KILL", "murder": "$KILL", "execute": "$KILL",
    "die": "$DIE", "perish": "$DIE", "expire": "$DIE",
    "be": "$BE", "equal": "$BE", "represent": "$BE", "constitute": "$BE",
}

# ═══════════════════════════════════════════════════════════════════════════════
# VERB CLUSTERS (only these canonical IDs count as verbs during extraction)
# ═══════════════════════════════════════════════════════════════════════════════

_VERB_CLUSTERS: Set[str] = {
    "$REST_POS", "$ACQUIRE", "$DISCOVER", "$CREATE", "$DESTROY", "$CONSUME",
    "$WRITE", "$ASSERT", "$CAUSE", "$PREVENT", "$INCREASE", "$DECREASE",
    "$START", "$END", "$ASSIST", "$USE", "$SHOW", "$KILL", "$DIE", "$BE",
}

# ═══════════════════════════════════════════════════════════════════════════════
# MODULE HASH (SHA-256 del contenido canónico del módulo)
# ═══════════════════════════════════════════════════════════════════════════════

_MODULE_CANONICAL: str = (
    "r3_2_topological.py|"
    + MODULE_VERSION + "|"
    + "|".join(
        str(v) for v in [
            KAPPA_D, PARAPHRASE_RESCUE_BOOST, CONTRADICTION_VETO_PENALTY,
            LEXICAL_OVERLAP_THRESHOLD, MIN_ANCHORED_COMPONENTS,
            VERB_WEIGHT, AGENT_WEIGHT, PATIENT_WEIGHT,
            COMPONENT_MATCH_THRESHOLD,
        ]
    )
    + "|"
    + "|".join(sorted(_VERB_CLUSTERS))
)
MODULE_HASH: str = hashlib.sha256(_MODULE_CANONICAL.encode("utf-8")).hexdigest()

# ═══════════════════════════════════════════════════════════════════════════════
# PASSIVE VOICE PATTERN
# ═══════════════════════════════════════════════════════════════════════════════

_PASSIVE_RE = re.compile(
    r"\b(was|were|is|are|been)\s+"
    r"(?:not\s+|never\s+)?"
    r"(\w+ed|\w+en|built|made|found|bought|written|taken|seen|known|given|done|"
    r"held|kept|left|lost|meant|met|paid|put|read|said|sent|set|shot|shown|shut|"
    r"sold|spent|spoken|stolen|taught|told|thought|understood|worn|won)\s+"
    r"(?:on\s+|upon\s+|in\s+|into\s+|to\s+|at\s+)?by\s+(.+)",
    re.IGNORECASE,
)

# ═══════════════════════════════════════════════════════════════════════════════
# AUXILIARY VERBS (ignored when extracting the main verb)
# ═══════════════════════════════════════════════════════════════════════════════

_AUXILIARY_VERBS: Set[str] = {
    "did", "does", "do", "have", "has", "had",
    "will", "would", "can", "could", "shall", "should", "may", "might", "must",
}


# ═══════════════════════════════════════════════════════════════════════════════
# LEMMATIZER
# ═══════════════════════════════════════════════════════════════════════════════

def lemmatize_token(w: str) -> str:
    """Deterministic inline lemmatizer. No external deps."""
    w = w.lower()
    if w in _IRREGULAR_VERBS:
        return _IRREGULAR_VERBS[w]
    if len(w) > 4:
        if w.endswith("ies"):
            return w[:-3] + "y"
        if w.endswith("ied"):
            return w[:-3] + "y"
        if w.endswith("ing"):
            base = w[:-3]
            # handle double consonant: sitting -> sit
            if len(base) >= 2 and base[-1] == base[-2]:
                return base[:-1]
            return base
        if w.endswith("ed"):
            return w[:-2]
        if w.endswith("es"):
            return w[:-2]
        if w.endswith("s") and not w.endswith("ss"):
            return w[:-1]
    return w


def canonicalize(w: str) -> str:
    """Map a token to its canonical cluster ID, or its lemma if not clustered."""
    lemma = lemmatize_token(w)
    return _CANONICAL_CLUSTERS.get(lemma, lemma)


# ═══════════════════════════════════════════════════════════════════════════════
# TRIPLE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

class CanonicalTriple:
    """A canonical (Agent, Action, Patient, Polarity) triple."""

    __slots__ = ("agent", "action", "patient", "polarity")

    def __init__(self, agent: Set[str], action: str, patient: Set[str], polarity: int):
        self.agent = frozenset(agent)
        self.action = action
        self.patient = frozenset(patient)
        self.polarity = polarity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": sorted(self.agent),
            "action": self.action,
            "patient": sorted(self.patient),
            "polarity": self.polarity,
        }


def _split_clauses(text: str) -> List[str]:
    """Split text into independent clauses."""
    parts = re.split(r"[.;]\s*|\b(?:but|however|although|whereas)\b", text)
    return [p.strip() for p in parts if p.strip()]


def _compute_polarity(clause: str) -> int:
    """Compute polarity pi in {+1, -1} via product of negation signs."""
    tokens = re.findall(r"[a-z0-9]+'?t\b|[a-z0-9]+", clause.lower())
    neg_count = 0
    for tok in tokens:
        if tok in NEGATION_TOKENS or tok.endswith("n't"):
            neg_count += 1
    return -1 if neg_count % 2 == 1 else 1


def _normalize_node(tokens: List[str]) -> Set[str]:
    """Normalize a node (agent/patient) to a set of canonical tokens."""
    result = set()
    for tok in tokens:
        t = tok.lower().strip(".,;:!?\"'()")
        if (
            not t
            or t in STOPWORDS
            or t in LINKING_PREPOSITIONS
            or t in _AUXILIARY_VERBS
            or t in NEGATION_TOKENS
        ):
            continue
        result.add(canonicalize(t))
    return result


def _extract_verb(clause: str) -> Optional[str]:
    """Extract the main verb (canonical) from a clause."""
    tokens = re.findall(r"[a-zA-Z0-9]+", clause)
    for tok in tokens:
        low = tok.lower()
        if low in _AUXILIARY_VERBS or low in STOPWORDS:
            continue
        lemma = lemmatize_token(low)
        if lemma in _CANONICAL_CLUSTERS and _CANONICAL_CLUSTERS[lemma] in _VERB_CLUSTERS:
            return _CANONICAL_CLUSTERS[lemma]
    # fallback: first non-stopword token
    for tok in tokens:
        low = tok.lower()
        if low not in STOPWORDS and low not in _AUXILIARY_VERBS:
            return canonicalize(low)
    return None


def extract_triples(text: str) -> List[CanonicalTriple]:
    """Extract canonical triples from a text."""
    triples: List[CanonicalTriple] = []
    for clause in _split_clauses(text):
        polarity = _compute_polarity(clause)

        # Passive voice detection + inversion
        m = _PASSIVE_RE.search(clause)
        if m:
            patient_tokens = re.findall(r"[a-zA-Z]+", clause[: m.start()])
            agent_tokens = re.findall(r"[a-zA-Z]+", m.group(3))
            verb = canonicalize(m.group(2))
            agent = _normalize_node(agent_tokens)
            patient = _normalize_node(patient_tokens)
            if agent and patient and verb:
                triples.append(CanonicalTriple(agent, verb, patient, polarity))
            continue

        # Active voice: split into subject / verb / object
        tokens = re.findall(r"[a-zA-Z0-9]+", clause)
        if not tokens:
            continue

        verb_idx = None
        for i, tok in enumerate(tokens):
            low = tok.lower()
            if low in _AUXILIARY_VERBS or low in STOPWORDS:
                continue
            lemma = lemmatize_token(low)
            if lemma in _CANONICAL_CLUSTERS and _CANONICAL_CLUSTERS[lemma] in _VERB_CLUSTERS:
                verb_idx = i
                break
        if verb_idx is None:
            continue

        subject_tokens = tokens[:verb_idx]
        object_tokens = tokens[verb_idx + 1:]
        verb = canonicalize(tokens[verb_idx])

        agent = _normalize_node(subject_tokens)
        patient = _normalize_node(object_tokens)

        if agent and verb:
            triples.append(CanonicalTriple(agent, verb, patient, polarity))

    return triples


# ═══════════════════════════════════════════════════════════════════════════════
# COMPARISON ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def node_sim(s1: Set[str], s2: Set[str]) -> float:
    """Overlap coefficient over canonical token sets."""
    if not s1 or not s2:
        return 0.0
    inter = len(s1 & s2)
    return inter / max(len(s1), len(s2))


def verb_sim(v1: str, v2: str) -> float:
    """1.0 if same canonical verb, else 0.0."""
    return 1.0 if v1 == v2 else 0.0


def compare_triples(t1: CanonicalTriple, t2: CanonicalTriple) -> Dict[str, Any]:
    """Compare two triples with strict anchoring rule."""
    # Direct score
    s_dir = (
        VERB_WEIGHT * verb_sim(t1.action, t2.action)
        + AGENT_WEIGHT * node_sim(t1.agent, t2.agent)
        + PATIENT_WEIGHT * node_sim(t1.patient, t2.patient)
    )

    # Copular symmetry: A=B iff B=A
    s_sym = s_dir
    if t1.action == "$BE" and t2.action == "$BE":
        s_sym = (
            VERB_WEIGHT * verb_sim(t1.action, t2.action)
            + AGENT_WEIGHT * node_sim(t1.agent, t2.patient)
            + PATIENT_WEIGHT * node_sim(t1.patient, t2.agent)
        )

    node_score = max(s_dir, s_sym)

    # Strict anchoring: at least MIN_ANCHORED_COMPONENTS must match >= threshold
    matched = 0
    if verb_sim(t1.action, t2.action) >= COMPONENT_MATCH_THRESHOLD:
        matched += 1
    if node_sim(t1.agent, t2.agent) >= COMPONENT_MATCH_THRESHOLD:
        matched += 1
    if node_sim(t1.patient, t2.patient) >= COMPONENT_MATCH_THRESHOLD:
        matched += 1

    if matched < MIN_ANCHORED_COMPONENTS:
        node_score = 0.0

    polarity_inversion = node_score >= KAPPA_D and t1.polarity != t2.polarity

    return {
        "node_score": round(node_score, 6),
        "polarity_inversion": polarity_inversion,
        "matched_components": matched,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LEXICAL OVERLAP (Jaccard, no stopwords)
# ═══════════════════════════════════════════════════════════════════════════════

def lexical_overlap(source: str, response: str) -> float:
    """Jaccard overlap of raw lowercase tokens (no stopwords)."""
    def toks(t: str) -> Set[str]:
        return {w.lower() for w in re.findall(r"[a-zA-Z0-9]+", t) if w.lower() not in STOPWORDS}
    s1, s2 = toks(source), toks(response)
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


# ═══════════════════════════════════════════════════════════════════════════════
# CONDITIONAL GATE
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_r3_2(source: str, response: str, lexical_overlap_value: Optional[float] = None) -> Dict[str, Any]:
    """Evaluate R3.2 with conditional gate."""
    if lexical_overlap_value is None:
        lexical_overlap_value = lexical_overlap(source, response)

    triples_a = extract_triples(source)
    triples_b = extract_triples(response)

    # Best matching triple pair
    best_score = 0.0
    best_inversion = False
    best_pair = None
    for ta in triples_a:
        for tb in triples_b:
            cmp = compare_triples(ta, tb)
            if cmp["node_score"] > best_score:
                best_score = cmp["node_score"]
                best_inversion = cmp["polarity_inversion"]
                best_pair = (ta, tb)

    # Audit hash
    audit_payload = {
        "source_triples": [t.to_dict() for t in triples_a],
        "response_triples": [t.to_dict() for t in triples_b],
        "lexical_overlap": round(lexical_overlap_value, 6),
        "topological_score": round(best_score, 6),
        "polarity_inversion": best_inversion,
    }
    audit_hash = hashlib.sha256(
        json.dumps(audit_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

    # Gate logic
    if best_inversion:
        verdict = "CONTRADICTION_VETO"
        adjustment = CONTRADICTION_VETO_PENALTY
    elif lexical_overlap_value < LEXICAL_OVERLAP_THRESHOLD and best_score >= KAPPA_D:
        verdict = "PARAPHRASE_RESCUE"
        adjustment = PARAPHRASE_RESCUE_BOOST
    else:
        verdict = "INACTIVE"
        adjustment = 0.0

    return {
        "verdict": verdict,
        "verdict_adjustment": adjustment,
        "topological_score": round(best_score, 6),
        "lexical_overlap": round(lexical_overlap_value, 6),
        "polarity_inversion": best_inversion,
        "n_source_triples": len(triples_a),
        "n_response_triples": len(triples_b),
        "audit_hash": audit_hash,
        "module_hash": MODULE_HASH,
        "module_version": MODULE_VERSION,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SELF-TEST SUITE
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 72)
    print("  R3.2 TOPOLOGICAL INVARIANCE — SELF-TEST")
    print("=" * 72)

    cases = [
        # (label, source, response, expected_verdict, min_score)
        ("1. Paraphrase pure (0% lex)",
         "The cat sat on the mat.",
         "A feline rested upon the rug.",
         "PARAPHRASE_RESCUE", 0.56),
        ("2. Passive voice + synonymy (score check; lex=0.43 keeps gate INACTIVE)",
         "Alexander Fleming discovered penicillin.",
         "Penicillin was found by Alexander Fleming.",
         "INACTIVE", 0.85),
        ("3. False positive S-V-O (hallucination control)",
         "Alexander Fleming discovered penicillin.",
         "Louis Pasteur invented the telephone.",
         "INACTIVE", 0.0),
        ("4. False positive animal (syntactic control)",
         "The cat sat on the mat.",
         "The dog ate the bone.",
         "INACTIVE", 0.0),
        ("5. Explicit polarity inversion",
         "The feline rested upon the rug.",
         "The cat did not sit on the mat.",
         "CONTRADICTION_VETO", 0.0),
        ("6. Scope negation vs double negation",
         "The physician hardly assisted the patient.",
         "The doctor did not fail to help the patient.",
         "CONTRADICTION_VETO", 0.0),
        ("7. Copular symmetry",
         "Water is H2O.",
         "H2O constitutes aqua.",
         "PARAPHRASE_RESCUE", 1.0),
    ]

    all_pass = True
    for label, src, rsp, exp_verdict, min_score in cases:
        t0 = time.perf_counter()
        res = evaluate_r3_2(src, rsp)
        elapsed_us = (time.perf_counter() - t0) * 1e6

        ok_verdict = res["verdict"] == exp_verdict
        ok_score = res["topological_score"] >= min_score
        ok = ok_verdict and ok_score
        all_pass = all_pass and ok

        status = "PASS" if ok else "FAIL"
        print(f"\n[{status}] {label}")
        print(f"  verdict={res['verdict']}  score={res['topological_score']}  "
              f"lex={res['lexical_overlap']}  inv={res['polarity_inversion']}")
        print(f"  triples: src={res['n_source_triples']} rsp={res['n_response_triples']}  "
              f"time={elapsed_us:.1f} µs")
        if not ok:
            print(f"  EXPECTED verdict={exp_verdict}, min_score={min_score}")
            print(f"  source triples: {[t.to_dict() for t in extract_triples(src)]}")
            print(f"  response triples: {[t.to_dict() for t in extract_triples(rsp)]}")

    print("\n" + "=" * 72)
    print(f"  RESULT: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    print("=" * 72)