"""
data_fetcher.py — Récupère les données de marché du jour.

Sources : CNN Fear & Greed, Alternative.me, CoinGecko, Yahoo Finance (yfinance), Reddit.
Chaque source est isolée : si l'une échoue, le rapport est quand même produit et la
section concernée affiche "N/D" (aucune valeur inventée).
"""
import re
import time
import zlib
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
import pandas as pd

from indicators import analyze
from social_fetcher import fetch_social, fake_social

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Toronto")
except Exception:  # pragma: no cover
    TZ = timezone.utc

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]
WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

LABELS_FR = {
    "Extreme Fear": "Peur extrême", "extreme fear": "Peur extrême",
    "Fear": "Peur", "fear": "Peur",
    "Neutral": "Neutre", "neutral": "Neutre",
    "Greed": "Avidité", "greed": "Avidité",
    "Extreme Greed": "Avidité extrême", "extreme greed": "Avidité extrême",
}

INDEX_TICKERS = {"^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^GSPTSE": "TSX Composite", "^VIX": "VIX"}
EXTRA_HISTORY = ["BTC-USD"]        # historique seulement (plate-forme web) : exclu des tableaux du rapport

# Clôtures quotidiennes (5 ans) de la dernière récupération : {symbole: pandas.Series}. Lues par build_site.py.
LAST_CLOSES: Dict[str, Any] = {}

# Symboles courts / mots courants : comptés seulement avec le cashtag ($NOW)
AMBIGUOUS = {"NOW", "ON", "S", "NET", "BOOT", "KD", "A", "ALL", "IT", "ARE", "FOR"}


def now_local() -> datetime:
    return datetime.now(TZ)


def fr_date(dt: datetime, with_weekday: bool = False) -> str:
    s = f"{dt.day} {MONTHS_FR[dt.month - 1]} {dt.year}"
    return f"{WEEKDAYS_FR[dt.weekday()].capitalize()} {s}" if with_weekday else s


def _get(url: str, timeout: int = 15, headers=None):
    h = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
    if headers:
        h.update(headers)
    return requests.get(url, headers=h, timeout=timeout)


# ─────────────────────────────────────────────────────────────────────────────
def fetch_fg_stocks() -> Dict[str, Any]:
    try:
        r = _get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                 headers={"Referer": "https://www.cnn.com/", "Origin": "https://www.cnn.com"})
        r.raise_for_status()
        j = r.json()
        cur = j["fear_and_greed"]
        pts = j.get("fear_and_greed_historical", {}).get("data", [])
        hist = [int(round(float(p["y"]))) for p in pts[-7:]]
        by_day = {}
        for p in pts:
            by_day[datetime.fromtimestamp(p["x"] / 1000, timezone.utc).strftime("%Y-%m-%d")] = int(round(float(p["y"])))
        return {"score": int(round(float(cur["score"]))),
                "label": LABELS_FR.get(cur.get("rating", ""), cur.get("rating", "")),
                "history": hist, "series": sorted(by_day.items())}
    except Exception as e:
        print(f"[WARN] CNN Fear & Greed indisponible : {e}")
        return {"score": None, "label": "N/D", "history": [], "series": []}


def fetch_fg_crypto() -> Dict[str, Any]:
    try:
        r = _get("https://api.alternative.me/fng/?limit=1100")
        r.raise_for_status()
        rows = r.json()["data"]
        hist = [int(x["value"]) for x in reversed(rows[:7])]
        series = sorted({datetime.fromtimestamp(int(x["timestamp"]), timezone.utc).strftime("%Y-%m-%d"): int(x["value"]) for x in rows}.items())
        return {"score": int(rows[0]["value"]),
                "label": LABELS_FR.get(rows[0]["value_classification"], rows[0]["value_classification"]),
                "history": hist, "series": series}
    except Exception as e:
        print(f"[WARN] Fear & Greed crypto indisponible : {e}")
        return {"score": None, "label": "N/D", "history": [], "series": []}


def fetch_crypto() -> Dict[str, Any]:
    try:
        ids = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "ripple": "XRP"}
        r = _get("https://api.coingecko.com/api/v3/simple/price?ids=" + ",".join(ids) +
                 "&vs_currencies=usd&include_24hr_change=true&include_market_cap=true")
        r.raise_for_status()
        j = r.json()
        return {sym: {"price": j[cid]["usd"], "chg_24h": j[cid].get("usd_24h_change"),
                      "mcap_b": (j[cid].get("usd_market_cap") or 0) / 1e9}
                for cid, sym in ids.items() if cid in j}
    except Exception as e:
        print(f"[WARN] CoinGecko indisponible : {e}")
        return {}


def fetch_quotes(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    """Clôtures quotidiennes sur 5 ans → indicateurs techniques calculés localement (historique conservé dans LAST_CLOSES)."""
    try:
        import yfinance as yf
        data = None
        for attempt in range(2):
            data = yf.download(tickers, period="5y", interval="1d", auto_adjust=True,
                               progress=False, threads=True)
            if data is not None and not data.empty:
                break
            time.sleep(3)
        if data is None or data.empty:
            return {}
        closes = data["Close"]
        if isinstance(closes, pd.Series):
            closes = closes.to_frame(tickers[0])
        out = {}
        LAST_CLOSES.clear()
        for t in tickers:
            if t in closes.columns:
                res = analyze(closes[t])
                if res:
                    out[t] = res
                    LAST_CLOSES[t] = closes[t].dropna()
        missing = [t for t in tickers if t not in out]
        if missing:
            print(f"[WARN] Sans données Yahoo Finance : {', '.join(missing)}")
        return out
    except Exception as e:
        print(f"[WARN] Yahoo Finance indisponible : {e}")
        return {}


def _symbol(t: str) -> str:
    return t.split(".")[0]


def _count(text: str, tickers: List[str]) -> Dict[str, int]:
    up = text.upper()
    res = {}
    for t in tickers:
        sym = re.escape(_symbol(t))
        n = len(re.findall(r"\$" + sym + r"(?![A-Z])", up))
        if _symbol(t) not in AMBIGUOUS:
            n += len(re.findall(r"(?<![A-Z$])" + sym + r"(?![A-Z])", up))
        if n:
            res[t] = n
    return res


def fetch_reddit(tickers: List[str]) -> Dict[str, Any]:
    subs = {"wallstreetbets": "r/wallstreetbets", "CanadianInvestor": "r/CanadianInvestor",
            "investing": "r/investing", "stocks": "r/stocks"}
    by_sub, totals, ok = {}, {}, 0
    for sub, label in subs.items():
        try:
            r = _get(f"https://www.reddit.com/r/{sub}/hot.json?limit=50", headers={"User-Agent": "social-investing-report/1.0"})
            r.raise_for_status()
            counts: Dict[str, int] = {}
            for post in r.json()["data"]["children"]:
                d = post["data"]
                for t, n in _count(d.get("title", "") + " " + d.get("selftext", ""), tickers).items():
                    counts[t] = counts.get(t, 0) + n
            by_sub[label] = sorted(counts.items(), key=lambda x: -x[1])[:6]
            for t, n in counts.items():
                totals[t] = totals.get(t, 0) + n
            ok += 1
            time.sleep(1.5)
        except Exception as e:
            print(f"[WARN] Reddit {label} indisponible : {e}")
            by_sub[label] = None
    return {"available": ok > 0, "by_sub": by_sub, "totals": totals}


# ─────────────────────────────────────────────────────────────────────────────
def all_tickers(content: Dict[str, Any]) -> List[str]:
    t = set()
    for key in ("undervalued", "overvalued", "semis", "cyber", "retail"):
        t.update(x["ticker"] for x in content.get(key, []))
    t.update(b["proxy"] for b in content.get("brands", []) if b.get("proxy"))
    t.update(content.get("extra_tickers", []))
    return sorted(t)


def fetch_all(content: Dict[str, Any]) -> Dict[str, Any]:
    tickers = all_tickers(content)
    print("  → Fear & Greed (actions) ...");  fgs = fetch_fg_stocks()
    print("  → Fear & Greed (crypto) ...");   fgc = fetch_fg_crypto()
    print("  → Crypto (CoinGecko) ...");      crypto = fetch_crypto()
    print(f"  → Cours & indicateurs ({len(tickers) + len(INDEX_TICKERS)} symboles) ...")
    quotes = fetch_quotes(tickers + list(INDEX_TICKERS) + EXTRA_HISTORY)
    print("  → Reddit (direct) ...");         reddit = fetch_reddit(tickers)
    social = fetch_social(content)
    return _package(fgs, fgc, crypto, quotes, reddit, social, demo=False)


def _package(fgs, fgc, crypto, quotes, reddit, social, demo: bool) -> Dict[str, Any]:
    now = now_local()
    return {
        "demo": demo,
        "generated_at": now,
        "date_fr": fr_date(now),
        "date_long_fr": fr_date(now, with_weekday=True),
        "date_iso": now.strftime("%Y-%m-%d"),
        "fg_stocks": fgs, "fg_crypto": fgc, "crypto": crypto,
        "indices": {k: quotes.get(k) for k in INDEX_TICKERS},
        "quotes": {k: v for k, v in quotes.items() if k not in INDEX_TICKERS and k not in EXTRA_HISTORY},
        "reddit": reddit,
        "social": social,
    }


# ─────────────────────────────────────────────────────────────────────────────
def fake_all(content: Dict[str, Any]) -> Dict[str, Any]:
    """Données SYNTHÉTIQUES pour tester la mise en page hors-ligne (--demo). Jamais pour décision."""
    import numpy as np
    tickers = all_tickers(content) + list(INDEX_TICKERS) + EXTRA_HISTORY
    quotes = {}
    idx = pd.bdate_range(end=now_local().date(), periods=1300)
    LAST_CLOSES.clear()
    for t in tickers:
        rng = np.random.default_rng(zlib.crc32(t.encode()))
        if t == "^VIX":
            x = np.empty(1300); x[0] = 18.0
            for i in range(1, 1300):
                x[i] = max(10.0, x[i - 1] + 0.08 * (19 - x[i - 1]) + rng.normal(0, 1.1))
            series = pd.Series(x, index=idx)
        else:
            start = float(rng.uniform(20, 400)) if t != "BTC-USD" else 60000.0
            series = pd.Series(start * np.exp(np.cumsum(rng.normal(0.0004, 0.02, 1300))), index=idx)
        quotes[t] = analyze(series)
        LAST_CLOSES[t] = series
    quotes = {k: v for k, v in quotes.items()}
    rng = np.random.default_rng(7)
    totals = {t: int(rng.integers(0, 14)) for t in all_tickers(content)}
    top = sorted(totals.items(), key=lambda x: -x[1])[:6]
    reddit = {"available": True,
              "by_sub": {"r/wallstreetbets": top, "r/CanadianInvestor": top[:4],
                         "r/investing": top[1:6], "r/stocks": top[2:6]},
              "totals": totals}
    def _fg(seed, n, lo=10, hi=90):
        r = np.random.default_rng(seed); v = [50.0]
        for _ in range(n - 1):
            v.append(float(min(hi, max(lo, v[-1] + 0.05 * (50 - v[-1]) + r.normal(0, 4)))))
        days = pd.bdate_range(end=now_local().date(), periods=n)
        return [(d_.strftime("%Y-%m-%d"), int(round(x))) for d_, x in zip(days, v)]
    s_series, c_series = _fg(21, 1000), _fg(22, 1000)
    fgs = {"score": s_series[-1][1], "label": "Neutre", "history": [x[1] for x in s_series[-7:]], "series": s_series}
    fgc = {"score": c_series[-1][1], "label": "Neutre", "history": [x[1] for x in c_series[-7:]], "series": c_series}
    crypto = {"BTC": {"price": 65000.0, "chg_24h": -0.4, "mcap_b": 1300.0},
              "ETH": {"price": 3100.0, "chg_24h": 0.8, "mcap_b": 370.0},
              "SOL": {"price": 140.0, "chg_24h": -1.2, "mcap_b": 65.0},
              "XRP": {"price": 0.6, "chg_24h": 0.1, "mcap_b": 34.0}}
    return _package(fgs, fgc, crypto, quotes, reddit, fake_social(content, all_tickers(content)), demo=True)
