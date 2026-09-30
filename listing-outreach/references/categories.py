#!/usr/bin/env python3
"""H&R MASTER DATABASE 2.0 category vocabulary — harvested from the live list, not invented.

The handbook (Step 5) asks for a MAIN CATEGORY and SUB-CATEGORY in the requirement's
`description`, so the database can be queried by use. Reading ~250 real entries out of
tim_list_id 55554 shows the convention in practice is:

    Main; Sub                     e.g. "QSR; Pizza", "Service; Hair", "Home; Furniture"
    Main; Sub; PAD                 pad-site prospects
    Main; Sub; DTC                 direct-to-consumer / online-only

...and shows it drifting: "FItness", "Fintess", "Serrvice", "General Merchanside", "Qsr",
"Med-Retail" vs "Med Retail", "Fitness; P&Y" vs "Fitness; Y&P", "Grocery; Small Format" vs
"Supermarket; Small Format", ":" and "," used instead of ";", trailing separators. Every one
of those is a query that silently misses rows — the exact JUNK IN, JUNK OUT the handbook warns
about. normalize() maps them back to canonical.
"""
import re

# Main categories actually in use (frequency order from the live sample).
MAIN_CATEGORIES = [
    "QSR", "F&B", "Service", "Fitness", "Education", "Apparel", "Med Retail",
    "General Merchandise", "Home", "Grocery", "Auto", "Entertainment", "Bank",
    "Pharmacy", "Hotel", "Salon / Spa", "Self Storage", "Gas + C-Store",
]

# Variants seen in the live data -> canonical main.
MAIN_ALIASES = {
    "qsr / fast food": "QSR", "qsr /fast food": "QSR", "qsr/fast food": "QSR",
    "fast food": "QSR", "qsr": "QSR",
    "fitness": "Fitness", "fintess": "Fitness",          # typo, live
    "service": "Service", "serrvice": "Service",         # typo, live
    "med retail": "Med Retail", "med-retail": "Med Retail", "medretail": "Med Retail",
    "general merchandise": "General Merchandise",
    "general merchanside": "General Merchandise",        # typo, live
    "supermarket": "Grocery",                            # two mains, one concept
    "grocery": "Grocery",
    "f&b": "F&B", "food & beverage": "F&B",
    "education": "Education", "apparel": "Apparel", "home": "Home", "auto": "Auto",
    "entertainment": "Entertainment", "bank": "Bank", "pharmacy": "Pharmacy",
    "salon / spa": "Salon / Spa", "salon": "Salon / Spa",
    "hotel": "Hotel",
    # surfaced by the 5,779-row pass -- real categories that were missing, plus more typos
    "self storage": "Self Storage", "storage": "Self Storage",
    "gas + c-store": "Gas + C-Store", "gas + c-stores": "Gas + C-Store",
    "gas + c store": "Gas + C-Store", "gas": "Gas + C-Store",
    "c-store": "Gas + C-Store", "convenience": "Gas + C-Store",
    "appreal": "Apparel",                                # typo, live
    "edication": "Education",                            # typo, live
    "genera merchandise": "General Merchandise",         # typo, live
    "general merchanise": "General Merchandise",         # typo, live
    "grocer": "Grocery",
    "misc. retail": "General Merchandise", "misc retail": "General Merchandise",
    "vet": "Med Retail", "veterinary": "Med Retail",
    # from the 23-row manual review, 2026-09-09
    "appeal": "Apparel", "genral merchandise": "General Merchandise",
    "sevice": "Service", "merchandise": "General Merchandise",
    "gas + c stores": "Gas + C-Store", "gas & c-store": "Gas + C-Store",
    "gas & c-stores": "Gas + C-Store", "pilates": "Fitness",

    # 5,779-row pass over the real export: "QSR / Fast Food" (637) and "QSR" (286) are one
    # category; "Med-Retail" (360) and "Med Retail" (76) are one. F&B (1,806) is the largest
    # main and stays distinct from QSR.
}

# Sub-category variants -> canonical.
SUB_ALIASES = {
    "y&p": "P&Y", "p&y": "P&Y",                          # pilates & yoga, both orders live
    "womens boutique": "Women's Boutique",
    "women's boutique": "Women's Boutique",
    "dollar store": "Dollar Store",
    "stionary": "Stationery", "journals": "Stationery",
    "menswear": "Menswear", "multi brand ownership": "Multi Brand Ownership",
    "bbc": "BBQ",                                        # consistently mistyped in the list
    "dermotology": "Dermatology", "acupunture": "Acupuncture",
    "pt": "PT", "eye": "Eye", "dental": "Dental",
}

# The outreach spreadsheet uses its own shorthand ("QSR drive-thru"), which is NOT the 2.0
# database vocabulary. Bridge it before normalising, or every pad tenant lands as "Qsr
# Drive-Thru" and never matches a query.
OUTREACH_CATEGORY = {
    "qsr drive-thru":      "QSR; Drive-Thru; PAD",
    "coffee drive-thru":   "QSR; Coffee; Drive-Thru; PAD",
    "bank / credit union": "Bank; Credit Union",
    "gas / c-store":       "Gas + C-Store; PAD",
    "quick lube":          "Auto; Quick Lube; PAD",
    "tire / auto":         "Auto; Tire",
    "auto service":        "Auto; Service",
    "express car wash":    "Auto; Car Wash; PAD",
    "ev charging":         "Auto; EV Charging; PAD",
    "owner-user":          "",          # not a use -- a deal structure
}

# A single free-text word that names a sub AND settles the main.
SUB_IMPLIES_MAIN = {
    "menswear":  ("Apparel", "Menswear"),
    "womenswear": ("Apparel", "Womenswear"),
    "kids play": ("Entertainment", "Kids Play"),
    "stionary":  ("General Merchandise", "Stationery"),
    "stationery": ("General Merchandise", "Stationery"),
    "journals":  ("General Merchandise", "Stationery"),
}

TAGS = {"PAD", "DTC"}

# .title() would turn these into "Bbq" / "Sco" and quietly make 69 real rows worse.
ACRONYMS = {"BBQ", "SCO", "PT", "P&Y", "ENT", "QSR", "DTC", "PAD", "CBD", "MMA",
            "HVAC", "ATM", "EV", "DIY", "TV", "US", "DC", "MD", "VA", "NY", "LA"}


def _case(word):
    w = word.strip()
    if w.upper() in ACRONYMS:
        return w.upper()
    if w.isupper() and len(w) <= 4:      # unknown short acronym -- leave it alone
        return w
    # title-case word by word so "Asian BBQ" keeps its acronym
    def cap(x):
        if x.upper() in ACRONYMS:
            return x.upper()
        return "-".join(y[:1].upper() + y[1:] if y else y for y in x.split("-"))
    return " ".join(cap(x) for x in w.split())
SPLIT = re.compile(r"\s*(?:[;:,/|\n]|\s-\s)\s*")  # "|", " - " and literal newlines all appear live


def normalize(desc):
    """'FItness ; P&Y' -> 'Fitness; P&Y'.  Returns (text, main, sub, tags)."""
    raw = (desc or "").strip().strip(";:,").strip()
    raw = OUTREACH_CATEGORY.get(raw.lower(), raw)
    if not raw:
        return ("", None, None, [])
    if re.search(r"\(\s*online only\s*\)", raw, re.I):        # -> the handbook's DTC tag
        raw = re.sub(r"\(\s*online only\s*\)", "", raw, flags=re.I).strip() + "; DTC"
    if not raw:
        return ("", None, None, [])
    parts = [p for p in SPLIT.split(raw) if p.strip()]
    tags = [p.upper() for p in parts if p.upper() in TAGS]
    parts = [p for p in parts if p.upper() not in TAGS]
    if not parts:
        return (raw, None, None, tags)

    implied = SUB_IMPLIES_MAIN.get(parts[0].strip().lower())
    if implied:
        m2, s2 = implied
        rest = [SUB_ALIASES.get(x.strip().lower(), _case(x)) for x in parts[1:]]
        subs2 = [s2] + [x for x in rest if x.lower() != s2.lower()]
        return ("; ".join([m2] + subs2 + tags), m2, "; ".join(subs2), tags)

    main = MAIN_ALIASES.get(parts[0].strip().lower())
    if not main:
        # "QSR / Fast Food" arrives pre-split by SPLIT; try rejoining the first two
        if len(parts) > 1:
            main = MAIN_ALIASES.get((parts[0] + " / " + parts[1]).strip().lower())
            if main:
                parts = parts[1:]
        if not main:
            main = parts[0].strip().title()

    subs = []
    for p in parts[1:]:
        low = p.strip().lower()
        if MAIN_ALIASES.get(low) == main:      # "QSR / Fast Food" -> don't repeat "Fast Food"
            continue
        subs.append(SUB_ALIASES.get(low, _case(p)))
    sub = "; ".join(subs) or None
    text = "; ".join([main] + subs + tags)
    return (text, main, sub, tags)


if __name__ == "__main__":
    live = ["FItness ; P&Y", "Fitness; Y&P", "Qsr; Bubble Tea", "QSR: Asian",
            "QSR /Fast Food; BBC;", "Serrvice; Dry Cleaning", "General Merchanside",
            "Med-Retail; Urgent Care", "Supermarket; Small Format", "Education, Tutoring",
            "Apparel; Womens Boutique", "QSR / Fast Food; Ice Cream; PAD", "Service"]
    w = max(len(x) for x in live)
    for s in live:
        print("  %-*s ->  %s" % (w, s, normalize(s)[0]))
