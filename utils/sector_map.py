"""
Sector → Sub-sector mapping for grouping 837 raw CSV sectors into ~50 main groups.
Used by 4_Sector_Trends.py for a two-level sector browser.
"""

# Main sector groups and keywords to match sub-sectors
# Order matters: first match wins
SECTOR_GROUPS = {
    "🏦 Banking & Finance": [
        "banking", "bank", "nbfc", "microfinance", "payments", "financial services",
        "asset management", "insurance", "wealth management", "credit",
    ],
    "💊 Pharma & Healthcare": [
        "pharmaceuticals", "pharma", "healthcare", "hospital", "diagnostics",
        "biotech", "biotechnology", "medical devices", "medical",
    ],
    "💻 IT & Technology": [
        "it -", "it /", "it services", "software", "saas", "technology",
        "cloud computing", "cloud communications", "cybersecurity", "data",
        "fintech", "artificial intelligence", "ai ",
    ],
    "🚗 Automobiles & Auto Parts": [
        "automobile", "automobiles", "auto component", "auto ancillary",
        "two wheeler", "2w", "3 wheeler", "ev", "electric vehicle", "tyres", "tyre",
    ],
    "⚗️ Chemicals": [
        "chemicals", "specialty chemicals", "agrochemicals", "dyes",
        "carbon black", "adhesives", "paints", "coatings",
    ],
    "🏗️ Infrastructure & Construction": [
        "infrastructure", "construction", "cement", "building material",
        "building products", "real estate", "realty", "roads", "ports",
        "housing", "tiles", "granite", "flooring",
    ],
    "⚡ Energy & Power": [
        "power", "energy", "solar", "renewable", "wind energy", "oil", "gas",
        "petroleum", "coal", "lng", "fuel",
    ],
    "🏭 Industrials & Capital Goods": [
        "industrials", "capital goods", "engineering", "machinery", "industrial",
        "defence", "aerospace", "bearings", "castings", "forgings",
        "pipes", "fasteners", "valves", "pumps", "compressors",
    ],
    "🌾 Agriculture & Agri-Business": [
        "agriculture", "agri", "agri business", "agri processing",
        "fertilisers", "fertilizer", "seeds", "pesticide", "aquaculture",
        "fisheries", "dairy",
    ],
    "🍽️ FMCG & Food": [
        "fmcg", "food", "beverages", "alcoholic beverages", "tobacco", "coffee",
        "tea", "sugar", "edible oil", "consumer goods", "packaged food",
    ],
    "📡 Telecom & Media": [
        "telecom", "media", "entertainment", "broadcast", "ott",
        "advertising", "publishing", "film", "content",
    ],
    "🛒 Retail & Consumer": [
        "retail", "e-commerce", "consumer", "d2c", "apparel", "fashion",
        "footwear", "jewellery", "luxury", "personal care",
    ],
    "🧵 Textiles & Apparel": [
        "textiles", "textile", "garments", "spinning", "yarn", "fabric",
        "synthetic fibre", "cotton",
    ],
    "⛏️ Metals & Mining": [
        "metals", "mining", "steel", "iron", "aluminium", "copper",
        "zinc", "gold", "silver", "ferro alloys",
    ],
    "🚢 Logistics & Transport": [
        "logistics", "transport", "shipping", "aviation", "ports", "freight",
        "courier", "warehousing", "supply chain",
    ],
    "🏨 Hospitality & Tourism": [
        "hospitality", "hotels", "tourism", "travel", "restaurants",
        "resorts", "catering",
    ],
    "📦 Packaging & Paper": [
        "packaging", "paper", "cartons", "containers", "laminates",
    ],
    "🔬 Research & Diversified": [
        "diversified", "conglomerate", "miscellaneous", "holding",
    ],
    "🎓 Education & Services": [
        "education", "edtech", "training", "services", "bpo", "staffing",
        "co-working", "facilities management",
    ],
    "🏠 Real Estate": [
        "real estate", "realty", "housing", "property",
    ],
}


def get_main_sector(raw_sector: str) -> str:
    """Map a raw CSV sector string to a main sector group."""
    s = str(raw_sector).lower().strip()
    for group, keywords in SECTOR_GROUPS.items():
        for kw in keywords:
            if kw in s:
                return group
    return "🗂️ Other"


def build_sector_hierarchy(stocks_df):
    """
    Given stocks_full.csv DataFrame, return a dict:
    {
      "Main Group Label": {
          "subsectors": ["Sub1", "Sub2", ...],
          "stock_count": N
      },
      ...
    }
    """
    import pandas as pd
    result = {}
    df = stocks_df[stocks_df["sector"].notna()].copy()
    df["main_group"] = df["sector"].apply(get_main_sector)

    for group, grp_df in df.groupby("main_group"):
        subsectors = sorted(grp_df["sector"].unique().tolist())
        result[group] = {
            "subsectors": subsectors,
            "stock_count": len(grp_df),
        }
    return dict(sorted(result.items()))
