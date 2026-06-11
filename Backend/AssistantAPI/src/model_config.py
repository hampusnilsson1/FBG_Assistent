# ============================================================
# MODEL CONFIGURATION
# ============================================================
# This is the ONLY file you need to edit when switching
# models, providers, pricing, or allowed web search domains.
# ============================================================

# ===== PROVIDER =====
# Supported: "openai" | "google"
CHAT_PROVIDER = "openai"
EMBEDDING_PROVIDER = "openai"

# ===== MODELS =====
CHAT_MODEL = "gpt-5.4-mini"
EMBEDDING_MODEL = "text-embedding-3-large"

# ===== PRICING (per 1M tokens, USD) =====
# Add new models here when adding support for them.
PRICING = {
    "gpt-5.4-mini": {
        "input": 0.75,
        "cached_input": 0.075,
        "output": 4.50,
    },
    "gpt-4o": {
        "input": 2.50,
        "cached_input": 1.25,
        "output": 10.00,
    },
    "gemini-3.1-flash-lite": {
        "input": 0.25,
        "cached_input": 0.0625,
        "output": 1.50,
    },
    "gemini-3-flash-preview": {
        "input": 0.50,
        "cached_input": 0.125,
        "output": 3.00,
    },
    "text-embedding-3-large": {
        "input": 0.13,
    },
}

# ===== KNOWLEDGE BASE COLLECTIONS =====
# Alla Qdrant-collections som search_knowledge_base kan söka i.
# Varje collection innehåller indexerat innehåll från en specifik domän.
# "primary": den huvudsakliga kommunala kunskapsbasen som ALLTID söks.
# "secondary": ytterligare collections som söks när frågan är relevant.
PRIMARY_COLLECTION = "FalkenbergsKommunsHemsida_RAG"

SECONDARY_COLLECTIONS = {
    "Vivab_RAG": "Vatten och Miljö i Väst AB (VIVAB) — vatten, avlopp, avfallshantering, sophämtning, återvinning och sorteringsguiden",
    "Fabo_RAG": "Falkenbergs Bostads AB (FABO) — lediga lägenheter, bostadskö, hyror, felanmälan, boendeinformation",
    "FalkenbergSE_RAG": "Falkenbergs besöks- och turistsida — evenemang, restauranger, aktiviteter, sevärdheter, turistboende",
    "FEAB_RAG": "Falkenbergs Energi AB (FEAB) — energifrågor, elnät, fjärrvärme, elpriser, nätanslutning",
}

# ===== WEB SEARCH ALLOWED DOMAINS ===== #ENDAST OPENAI (GOOGLE SÖKER ALLT)
# The agent's built-in web search will ONLY return results
# from these domains (and their subdomains).
# Each domain has a description to help the agent decide when to use it.
ALLOWED_DOMAINS_INFO = {
    "falkenberg.se": (
        "Falkenbergs besöks- och turistsida. Fokuserar på vad man kan hitta på "
        "i Falkenberg som besökare: evenemang, restauranger, aktiviteter, "
        "sevärdheter, boende för turister, och kontaktuppgifter/adresser till dessa."
    ),
    "kommun.falkenberg.se": (
        "Falkenbergs kommuns tjänsteportal. Innehåller detaljerad information om "
        "kommunala tjänster, bygglov, förskola, skola, omsorg, kultur, fritid, "
        "miljö, trafik, boende, näringsliv och kontaktuppgifter till förvaltningar."
    ),
    "fabo.se": (
        "Falkenbergs Bostads AB (FABO). Kommunalt bostadsbolag. Innehåller information "
        "om lediga lägenheter, bostadskö, hyror, felanmälan, boendeinformation, "
        "nyproduktion och kontaktuppgifter för hyresgäster."
    ),
    "vivab.se": (
        "VIVAB (Vatten och Miljö i Väst AB). Ansvarar för vatten, avlopp och "
        "avfallshantering i Falkenbergs kommun. Innehåller information om "
        "dricksvatten, avlopp, sophämtning, återvinning, taxor och driftstörningar."
    ),
}

# Plain list for the API filter (auto-generated from above)
ALLOWED_DOMAINS = list(ALLOWED_DOMAINS_INFO.keys())

# ===== WEB SEARCH TOGGLE =====
# True: allow the agent to search the web (allowed domains only).
# False: agent can ONLY search the vector database (Qdrant).
WEB_SEARCH_ENABLED = True

# ===== KNOWLEDGE BASE SOURCES (informational) =====
# These are the sources indexed into the Qdrant knowledge base.
# Changing these here does NOT affect indexing — update the
# QdrantDiffCron / QdrantManual pipelines for that.
KNOWLEDGE_BASE_SOURCES = [
    "https://intranet.falkenberg.se/fbg_apps/services/evolution/documents.php",  # Evolution PDFs
    "https://kommun.falkenberg.se/index.php?option=com_jmap&view=sitemap&format=xml",  # Webpage sitemap
]
