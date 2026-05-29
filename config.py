import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SUBREDDITS = [
    "wallstreetbets",
    "ValueInvesting",
    "stocks",
    "Stock_Picks",
    "mauerstrassenwetten",
]

# Words that look like tickers but should be ignored
EXCLUSION_LIST: frozenset = frozenset({
    # Single letters
    "A", "I",
    # Common finance/reddit jargon
    "AI", "IT", "EV", "CEO", "FDA", "IPO", "DD", "YOLO", "IMO", "TBH",
    "WSB", "OTM", "ITM", "ATM", "IV", "OP", "PM", "DM", "ET",
    "EST", "PST", "CST", "UTC", "GMT", "EOD", "EOW", "EOM",
    "YTD", "YOY", "ATH", "ETF", "NFT", "BTC", "ETH",
    "FOMO", "HODL", "REKT", "FUD", "PUMP", "DUMP", "MOON", "LMAO",
    "LMFAO", "TIL", "TLDR", "AMA", "LOL", "OMG", "WTF",
    "CALL", "PUT", "BUY", "SELL", "HOLD", "LONG", "SHORT",
    # Countries / regions
    "US", "UK", "EU", "CA",
    # Common ALL-CAPS words
    "ALL", "AND", "ARE", "BUT", "CAN", "FOR", "FROM", "GET", "HAS",
    "HAVE", "HERE", "HOW", "INTO", "JUST", "LIKE", "MAKE", "MORE",
    "MOST", "NEED", "NEXT", "NOT", "NOW", "ONLY", "OVER", "SAME",
    "SOME", "STILL", "SUCH", "THAN", "THAT", "THEM", "THEN", "THERE",
    "THEY", "THIS", "VERY", "WANT", "WELL", "WHAT", "WHEN", "WHERE",
    "WHICH", "WILL", "WITH", "YOUR",
    "CASH", "RATE", "RISK", "LOSS", "GAIN", "COST", "PLAN", "FUND",
    "DEBT", "LOAN", "BANK", "BOND", "NOTE", "YEAR", "WEEK", "DAYS",
    "TIME", "DONE", "GOOD", "GREAT", "BEST", "LAST", "FIRST", "PART",
    "MANY", "AWAY", "BACK", "EDIT", "POST", "LINK", "READ",
    "PRICE", "TRADE", "STOCK", "MARKET", "SHARE", "SHARES",
    "RETURN", "YIELD", "INDEX",
    # Technical
    "HTTP", "HTML", "JSON", "API", "URL", "SQL", "CSS",
    # Miscellaneous short noise
    "RE", "BY", "AS", "AN", "AT", "IN", "ON", "TO", "OF", "IS",
    "HE", "ME", "WE", "HI", "GO", "BE", "DO", "MY", "OR", "IF",
    "UP", "SO", "NO", "AH", "OH", "OK", "NEW", "TOP", "ANY",
    "OLD", "BIG", "LOW", "HIGH",
})

# German company name → ticker symbol for r/mauerstrassenwetten
GERMAN_TICKER_MAP: dict = {
    "biontech": "BNTX",
    "wirecard": "WDI",
    "volkswagen": "VWAGY",
    " vw ": "VWAGY",
    "daimler": "MBGYY",
    "mercedes": "MBGYY",
    " bmw ": "BMWYY",
    "siemens": "SIEGY",
    "allianz": "ALIZY",
    " basf ": "BASFY",
    "deutsche bank": "DB",
    "deutsche telekom": "DTEGY",
    "lufthansa": "DLAKY",
    "adidas": "ADDYY",
    "infineon": "IFNNY",
    "fresenius": "FSNUY",
    " rwe ": "RWEOY",
    " e.on ": "EONGY",
    "henkel": "HENKY",
    "zalando": "ZAL",
    "hellofresh": "HFG",
    "delivery hero": "DHER",
    "porsche": "POAHY",
    "continental": "CTTAY",
    "covestro": "COVTY",
    " bayer ": "BAYRY",
    "commerzbank": "CRZBY",
    "munich re": "MURGY",
    "münchener rück": "MURGY",
}

# Well-known meme/small-cap tickers not in S&P 500
EXTRA_TICKERS: dict = {
    "GME": "GameStop Corp",
    "AMC": "AMC Entertainment Holdings",
    "BB": "BlackBerry Limited",
    "NOK": "Nokia Corporation",
    "PLTR": "Palantir Technologies",
    "SPCE": "Virgin Galactic Holdings",
    "MVIS": "MicroVision Inc",
    "WKHS": "Workhorse Group Inc",
    "RIDE": "Lordstown Motors Corp",
    "NKLA": "Nikola Corporation",
    "GOEV": "Canoo Inc",
    "XPEV": "XPeng Inc",
    "NIO": "NIO Inc",
    "LI": "Li Auto Inc",
    "RIVN": "Rivian Automotive",
    "LCID": "Lucid Group",
    "COIN": "Coinbase Global",
    "HOOD": "Robinhood Markets",
    "DKNG": "DraftKings Inc",
    "PENN": "Penn Entertainment",
    "MSTR": "MicroStrategy Inc",
    "NVAX": "Novavax Inc",
    "MRNA": "Moderna Inc",
    "BNTX": "BioNTech SE",
    "TLRY": "Tilray Brands",
    "CGC": "Canopy Growth",
    "ACB": "Aurora Cannabis",
    "SOFI": "SoFi Technologies",
    "OPEN": "Opendoor Technologies",
    "DOGE": "Dogecoin (meme ref)",
    "SNAP": "Snap Inc",
    "PINS": "Pinterest Inc",
    "RBLX": "Roblox Corporation",
    "AFRM": "Affirm Holdings",
    "UPST": "Upstart Holdings",
    "OSCR": "Oscar Health",
    "BIRD": "Allbirds Inc",
    "BRCC": "Black Rifle Coffee",
    "BBAI": "BigBear.ai",
    "FFIE": "Faraday Future",
    "MULN": "Mullen Automotive",
    "ILUS": "ILUS International",
    "BBBY": "Bed Bath & Beyond",
    "SNDL": "Sundial Growers",
    "CLOV": "Clover Health",
    "WISH": "ContextLogic Inc",
}

# File paths
DB_PATH = os.path.join(BASE_DIR, "stock_mentions.db")
TICKER_CACHE_PATH = os.path.join(BASE_DIR, "tickers_cache.csv")
SP500_CSV_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies"
    "/main/data/constituents.csv"
)

# Polling intervals (seconds)
SUBREDDIT_POLL_INTERVAL = 300   # 5 minutes
LIVE_THREAD_POLL_INTERVAL = 30  # 30 seconds

# How many posts to fetch each poll cycle (hot + new each)
POSTS_PER_POLL = 25
# How many posts to fetch on initial startup backfill
BACKFILL_LIMIT = 100
# How old the ticker cache can be before re-fetching (seconds)
TICKER_CACHE_MAX_AGE = 86400  # 24 hours
