#!/usr/bin/env python3
"""Category -> VTS target-size block, per the H&R VTS Database Handbook 2.0 (Step 4/5).

The handbook asks for a size block and a MAIN CATEGORY / SUB-CATEGORY on every tenant so the
master database can be queried by use. Guessing the block from the category gets it ~right
without hand-entering 70 tenants; a broker corrects the odd one.

Blocks are the handbook's, exactly:
    1-1,500 | 1-3,000 | 3,000-5,000 | 5,000-10,000 | 10,000-25,000 | 25,000-50,000 | 50,000-250,000
"""

BLOCKS = [(1, 1500), (1, 3000), (3000, 5000), (5000, 10000),
          (10000, 25000), (25000, 50000), (50000, 250000)]

# DIRT / PAD WORK: do not use these blocks. For a ground-lease or pad requirement the number
# that matters is TOTAL REQUIRED ACREAGE, and VTS has no field for it -- the SF blocks are an
# inline-retail construct. Leave the size blank on those rather than entering a building size
# that nobody will query on. (Spencer, 2026-09-09: "building sizes don't really matter for
# most dirt work, total required acreage is the most important stat.")

# MAIN CATEGORY -> (min, max). Prototype building size, not the parcel.
# Main categories as H&R actually writes them in the 2.0 list (see categories.py).
# Prototype building size, not the parcel.
CATEGORY_SIZE = {
    "QSR":                  (1, 3000),
    "F&B":                  (3000, 5000),
    "Service":              (1, 1500),
    "Fitness":              (25000, 50000),
    "Education":            (10000, 25000),
    "Apparel":              (3000, 5000),
    "Med Retail":           (3000, 5000),
    "General Merchandise":  (10000, 25000),
    "Home":                 (25000, 50000),
    "Grocery":              (25000, 50000),
    "Auto":                 (3000, 5000),
    "Entertainment":        (25000, 50000),
    "Bank":                 (1, 3000),
    "Pharmacy":             (10000, 25000),
    "Salon / Spa":          (1, 1500),
    "Gas + C-Store":        (3000, 5000),
    "Self Storage":         (50000, 250000),
    "Hotel":                (50000, 250000),
}

# Sub-category refinements, where the sub moves the number materially.
SUB_SIZE = {
    ("QSR", "Pizza"):          (1, 1500),
    ("QSR", "Ice Cream"):      (1, 1500),
    ("QSR", "Coffee"):         (1, 1500),
    ("QSR", "Desserts"):       (1, 1500),
    ("QSR", "Bubble Tea"):     (1, 1500),
    ("QSR", "Chicken"):        (1, 3000),
    ("QSR", "BBQ"):            (1, 3000),
    ("Fitness", "P&Y"):        (3000, 5000),
    ("Fitness", "Personal Training"): (1, 3000),
    ("Fitness", "Discount"):   (10000, 25000),
    ("Grocery", "Small Format"): (10000, 25000),
    ("Grocery", "Large Format"): (25000, 50000),
    ("Auto", "Car Rental"):    (1, 1500),
    ("Auto", "Quick Lube"):    (1, 3000),
    ("Auto", "Tire"):          (3000, 5000),
    ("Auto", "Service"):       (3000, 5000),
    ("Auto", "Car Wash"):      (3000, 5000),
    ("Auto", "EV Charging"):   (1, 1500),
    ("QSR", "Drive-Thru"):     (1, 3000),
    ("QSR", "Coffee"):         (1, 1500),
    ("Bank", "Credit Union"):  (1, 3000),
    ("Gas + C-Store", None):   (3000, 5000),
    ("Auto", "Parts"):         (5000, 10000),
    ("Auto", "Collision"):     (10000, 25000),
    ("Education", "Tutoring"): (1, 3000),
    ("Education", "Martial Arts"): (3000, 5000),
    ("Home", "Furniture"):     (25000, 50000),
    ("Home", "Closets"):       (1, 3000),
    ("General Merchandise", "Dollar Store"): (5000, 10000),
    ("Apparel", "Shoes"):      (3000, 5000),
    ("Med Retail", "Urgent Care"): (3000, 5000),
}

# Brand overrides where the prototype differs from its category's default.
BRAND_SIZE = {
    "little caesars":   (1, 1500),      # 1,200-1,400 endcap w/ pick-up window (Rawley, 9/8/26)
    "7 brew":           (1, 1500),      # ~500 SF kiosk
    "dutch bros":       (1, 1500),
    "scooter's coffee": (1, 1500),
    "the human bean":   (1, 1500),
    "starbucks":        (1, 3000),
    "chipotle":         (1, 3000),
    "autozone":         (5000, 10000),
    "o'reilly auto parts": (5000, 10000),
    "mavis discount tire": (3000, 5000),
    "caliber collision":   (10000, 25000),
    "auto spa express":    (3000, 5000),
    "the lube center":     (1, 3000),
    "grease monkey":       (1, 3000),
    "learning care group, inc.": (10000, 25000),   # Everbrook Academy
    "wawa":             (5000, 10000),
    "sheetz":           (5000, 10000),
    "royal farms":      (5000, 10000),
    "7-eleven":         (3000, 5000),
    "raising cane's":   (3000, 5000),
    "chick-fil-a":      (3000, 5000),
    "panera":           (3000, 5000),
    "buc-ee's":         (50000, 250000),
    "pmg worldwide, llc":      (3000, 5000),     # MD Petroleum Group
    "sun auto tire & service": (3000, 5000),
    "flagship car wash":       (3000, 5000),
    "slim chickens":           (3000, 5000),
    "bank of america":         (1, 3000),
    "panda express":           (1, 3000),
    "bridgestone corporation": (3000, 5000),
}

# VTS names the corporate entity, brokers say the brand. Both must resolve.
# (see the triage notes: Everbrook Academy IS Learning Care Group, Inc.)
BRAND_ALIAS = {
    "everbrook academy":        "learning care group, inc.",
    "md petroleum group":       "pmg worldwide, llc",
    "sun auto":                 "sun auto tire & service",
    "evgo":                     "ev charging",
    "ionna":                    "ev charging",
    "electrify america":        "ev charging",
    "the lube center":          "the lube center",
    "layne's chicken fingers":  "layne's",
    "pj's coffee":              "pj's coffee",
}


# EV charging has no main category in the 2.0 list yet; brands resolve directly.
CATEGORY_SIZE_BY_ALIAS = {"ev charging": (1, 1500),
                          "layne's": CATEGORY_SIZE["QSR"]}


def size_for(tenant=None, category=None):
    """(min, max, why). Brand override wins, then category, else None."""
    import categories as _cat
    if category and "PAD" in _cat.normalize(category)[3]:
        # Spencer, 2026-09-09: on dirt work the number that matters is total required
        # ACREAGE, not the prototype building. VTS has no field for it, so a PAD requirement
        # gets no SF block rather than one nobody will query on. This outranks a brand
        # override -- Chipotle on a pad is still a pad.
        return (None, None, "pad - acreage is the number, and VTS has no field for it")
    t = (tenant or "").strip().lower()
    t = BRAND_ALIAS.get(t, t)
    if t in BRAND_SIZE:
        return BRAND_SIZE[t] + ("brand prototype",)
    if t in CATEGORY_SIZE_BY_ALIAS:
        return CATEGORY_SIZE_BY_ALIAS[t] + ("category via alias",)
    if category:
        _txt, main, sub, _tags = _cat.normalize(category)
        # Spencer, 2026-09-09: on dirt work the number that matters is total required
        # ACREAGE, not the prototype building. VTS has no field for it, so a PAD requirement
        # gets no SF block rather than one nobody will query on.
        if main and sub:
            for one in [x.strip() for x in sub.split(";")]:
                if (main, one) in SUB_SIZE:
                    return SUB_SIZE[(main, one)] + ("sub-category",)
        if main in CATEGORY_SIZE:
            return CATEGORY_SIZE[main] + ("category default",)
    return (None, None, "unknown - leave blank for a broker to set")


if __name__ == "__main__":
    import sys
    print(size_for(*(sys.argv[1:] or [""])))
