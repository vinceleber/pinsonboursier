"""
social_fetcher.py — Canaux de Social Investing (gratuits, sans clé).

Sources automatisées :
  • ApeWisdom  — agrège les mentions Reddit (r/wallstreetbets, r/stocks, r/options, etc.) par titre et par cryptomonnaie.
  • StockTwits — palmarès public des symboles « en tendance ».
  • Wikipédia  — pages vues quotidiennes des articles des sociétés (indicateur d'attention du grand public).
  • Google Trends — intérêt de recherche relatif (0-100). NON OFFICIEL et fragile : pytrends est archivé depuis avril 2025
    et Google bloque souvent les adresses de serveurs. Le module est « au mieux » : en cas d'échec, la section affiche N/D.

Chaque fonction est isolée : une panne n'arrête jamais le rapport et aucune valeur n'est inventée.
"""
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

UA = "social-investing-report/1.0 (rapport personnel; contact: voir dépôt GitHub)"


def _num(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default


def _get_json(url: str, timeout: int = 15):
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ── ApeWisdom (Reddit agrégé) ────────────────────────────────────────────────
def _ape_filter(filter_name: str, pages: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for p in range(1, pages + 1):
        data = _get_json(f"https://apewisdom.io/api/v1.0/filter/{filter_name}/page/{p}")
        for it in data.get("results", []):
            rows.append({
                "rank": _num(it.get("rank")), "ticker": str(it.get("ticker", "")).upper(), "name": it.get("name", ""),
                "mentions": _num(it.get("mentions")), "upvotes": _num(it.get("upvotes")),
                "rank_24h": _num(it.get("rank_24h_ago"), None), "mentions_24h": _num(it.get("mentions_24h_ago"), None),
            })
        if p >= _num(data.get("pages"), 1):
            break
        time.sleep(0.5)
    return rows


def fetch_apewisdom(pages: int = 2) -> Dict[str, Any]:
    out: Dict[str, Any] = {"available": False, "stocks": [], "crypto": [], "by_ticker": {}}
    try:
        stocks = _ape_filter("all-stocks", pages)
        out["stocks"] = stocks[:15]
        out["by_ticker"] = {r["ticker"]: r for r in stocks}
        out["available"] = bool(stocks)
    except Exception as e:
        print(f"[WARN] ApeWisdom (actions) indisponible : {e}")
    try:
        out["crypto"] = _ape_filter("all-crypto", 1)[:8]
    except Exception as e:
        print(f"[WARN] ApeWisdom (crypto) indisponible : {e}")
    return out


# ── StockTwits (symboles en tendance) ────────────────────────────────────────
def fetch_stocktwits() -> Dict[str, Any]:
    try:
        data = _get_json("https://api.stocktwits.com/api/2/trending/symbols.json")
        rows = []
        for it in data.get("symbols", []):
            rows.append({"rank": _num(it.get("rank")), "symbol": str(it.get("symbol", "")).upper(),
                         "title": it.get("title", ""), "score": float(it.get("trending_score") or 0),
                         "watchlist": _num(it.get("watchlist_count"))})
        rows.sort(key=lambda r: r["rank"] or 999)
        return {"available": bool(rows), "rows": rows[:15], "by_symbol": {r["symbol"]: r for r in rows}}
    except Exception as e:
        print(f"[WARN] StockTwits indisponible : {e}")
        return {"available": False, "rows": [], "by_symbol": {}}


# ── Wikipédia (attention du grand public) ────────────────────────────────────
def fetch_wikipedia(titles: Dict[str, str]) -> Dict[str, Any]:
    """titles : {ticker: titre de l'article anglais}. Compare les 7 derniers jours aux 7 jours précédents."""
    end = datetime.now(timezone.utc).date() - timedelta(days=1)       # J-1 : la journée en cours est incomplète
    start = end - timedelta(days=13)
    res: Dict[str, Any] = {}
    fails = 0
    for tkr, title in titles.items():
        try:
            url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
                   f"{requests.utils.quote(title, safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
            items = _get_json(url)["items"]
            views = [i["views"] for i in items]
            if len(views) >= 14:
                last, prev = sum(views[-7:]) / 7.0, sum(views[-14:-7]) / 7.0
                res[tkr] = {"avg7": last, "prev7": prev, "chg": (last / prev - 1) * 100 if prev else None}
            time.sleep(0.15)
        except Exception:
            fails += 1
    if fails and not res:
        print("[WARN] Wikipédia indisponible")
    return {"available": bool(res), "by_ticker": res}


def fetch_wikipedia_series(titles: Dict[str, str], days: int = 365) -> Dict[str, Any]:
    """Pages vues quotidiennes sur `days` jours (rétro-remplissage de l'historique d'attention). {ticker: {d: [...], v: [...]}}"""
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    out: Dict[str, Any] = {}
    for tkr, title in titles.items():
        try:
            url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
                   f"{requests.utils.quote(title, safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
            items = _get_json(url, timeout=25)["items"]
            out[tkr] = {"d": [f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}" for i in items],
                        "v": [i["views"] for i in items]}
            time.sleep(0.15)
        except Exception:
            pass
    return out


# ── Google Trends (au mieux) ─────────────────────────────────────────────────
def fetch_google_trends(keywords: List[str]) -> Dict[str, Any]:
    if not keywords:
        return {"available": False, "rows": []}
    try:
        from pytrends.request import TrendReq          # optionnel : archivé, peut échouer
    except Exception:
        print("[WARN] Google Trends : pytrends non installé — section N/D")
        return {"available": False, "rows": []}
    try:
        pt = TrendReq(hl="fr-CA", tz=240, timeout=(8, 20), retries=1, backoff_factor=1.0)
        pt.build_payload(keywords[:5], timeframe="today 3-m", geo="US")
        df = pt.interest_over_time()
        if df is None or df.empty:
            return {"available": False, "rows": []}
        rows = []
        for k in keywords[:5]:
            if k not in df.columns:
                continue
            s = df[k].astype(float)
            cur, base = float(s.iloc[-7:].mean()), float(s.iloc[:-7].mean()) if len(s) > 7 else float("nan")
            rows.append({"keyword": k, "current": cur, "baseline": base,
                         "chg": (cur / base - 1) * 100 if base else None})
        return {"available": bool(rows), "rows": rows}
    except Exception as e:
        print(f"[WARN] Google Trends indisponible (limitation fréquente depuis les serveurs) : {e}")
        return {"available": False, "rows": []}


# ── SEC EDGAR : transactions d'initiés (formulaire 4) ────────────────────────
def _sec_headers() -> Dict[str, str]:
    return {"User-Agent": os.environ.get("SEC_USER_AGENT", "").strip(), "Accept-Encoding": "gzip, deflate"}


def _xml_float(node, path: str) -> float:
    try:
        return float(node.findtext(path) or 0)
    except Exception:
        return 0.0


def fetch_edgar(tickers: List[str], days: int = 45, max_forms: int = 10) -> Dict[str, Any]:
    """Achats (code P) et ventes (code S) en marché ouvert déclarés par les initiés, sur `days` jours.
    Exige un en-tête User-Agent déclarant un nom et un courriel (règle de la SEC) : variable SEC_USER_AGENT."""
    out: Dict[str, Any] = {"available": False, "reason": "", "days": days, "by_ticker": {}}
    if not os.environ.get("SEC_USER_AGENT", "").strip():
        out["reason"] = "SEC_USER_AGENT non configuré"
        print("[WARN] SEC EDGAR : SEC_USER_AGENT non configuré — signal des initiés laissé à la saisie manuelle")
        return out
    us = [t for t in tickers if "." not in t]
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=_sec_headers(), timeout=20)
        r.raise_for_status()
        cik_by = {v["ticker"].upper(): int(v["cik_str"]) for v in r.json().values()}
    except Exception as e:
        out["reason"] = f"table des symboles indisponible ({e})"
        print(f"[WARN] SEC EDGAR indisponible : {e}")
        return out
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    ok = 0
    for t in us:
        cik = cik_by.get(t.upper())
        if not cik:
            continue
        try:
            time.sleep(0.12)
            sub = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_sec_headers(), timeout=20)
            sub.raise_for_status()
            rec = sub.json()["filings"]["recent"]
            forms = [(rec["accessionNumber"][i], rec["primaryDocument"][i], rec["filingDate"][i])
                     for i in range(len(rec["form"])) if rec["form"][i] == "4" and rec["filingDate"][i] >= cutoff][:max_forms]
            buys = sells = 0.0
            buyers = set()
            for acc, doc, fdate in forms:
                time.sleep(0.12)
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc.split('/')[-1]}"
                xr = requests.get(url, headers=_sec_headers(), timeout=20)
                if xr.status_code != 200:
                    continue
                root = ET.fromstring(xr.content)
                owner = root.findtext("reportingOwner/reportingOwnerId/rptOwnerName") or "?"
                for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
                    code = tx.findtext("transactionCoding/transactionCode")
                    val = _xml_float(tx, "transactionAmounts/transactionShares/value") * _xml_float(tx, "transactionAmounts/transactionPricePerShare/value")
                    if code == "P":
                        buys += val; buyers.add(owner)
                    elif code == "S":
                        sells += val
            out["by_ticker"][t] = {"filings": len(forms), "buys": buys, "sells": sells, "buyers": len(buyers)}
            ok += 1
        except Exception as e:
            print(f"[WARN] EDGAR {t} : {e}")
    out["available"] = ok > 0
    if not ok:
        out["reason"] = "aucune réponse de la SEC"
    return out


def insider_signal_from(e: Dict[str, Any]) -> str:
    """ACHAT : achats ouverts >= 100 000 $ et supérieurs aux ventes. VENTE : ventes >= 25 M$ sans aucun achat. Sinon NEUTRE."""
    if not e:
        return "NEUTRE"
    if e["buys"] >= 100_000 and e["buys"] > e["sells"]:
        return "ACHAT"
    if e["sells"] >= 25_000_000 and e["buys"] == 0:
        return "VENTE"
    return "NEUTRE"


# ── YouTube Data API v3 (clé gratuite requise) ───────────────────────────────
def fetch_youtube(queries: Dict[str, str], days: int = 7) -> Dict[str, Any]:
    """queries : {ticker: texte de recherche}. 1 appel search.list par titre (limite par défaut : 100 par jour)."""
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    out: Dict[str, Any] = {"available": False, "reason": "", "by_ticker": {}}
    if not key:
        out["reason"] = "YOUTUBE_API_KEY non configurée"
        print("[WARN] YouTube : YOUTUBE_API_KEY non configurée — section N/D")
        return out
    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for t, q in list(queries.items())[:90]:
        try:
            s = requests.get("https://www.googleapis.com/youtube/v3/search", timeout=15, params={
                "part": "snippet", "q": q, "type": "video", "order": "viewCount", "publishedAfter": after,
                "maxResults": 3, "relevanceLanguage": "en", "key": key})
            s.raise_for_status()
            items = s.json().get("items", [])
            ids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]
            if not ids:
                continue
            v = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=15,
                             params={"part": "statistics", "id": ",".join(ids), "key": key})
            v.raise_for_status()
            stats = {x["id"]: int(x["statistics"].get("viewCount", 0)) for x in v.json().get("items", [])}
            best = max(items, key=lambda i: stats.get(i["id"]["videoId"], 0))
            out["by_ticker"][t] = {"views": stats.get(best["id"]["videoId"], 0), "total_views": sum(stats.values()),
                                   "title": best["snippet"]["title"], "channel": best["snippet"]["channelTitle"]}
            time.sleep(0.2)
        except Exception as e:
            print(f"[WARN] YouTube {t} : {e}")
            if "quota" in str(e).lower() or "403" in str(e):
                out["reason"] = "quota ou clé refusée"
                break
    out["available"] = bool(out["by_ticker"])
    if not out["available"] and not out["reason"]:
        out["reason"] = "aucun résultat"
    return out


# ── Orchestration ────────────────────────────────────────────────────────────
def fetch_social(content: Dict[str, Any]) -> Dict[str, Any]:
    print("  → ApeWisdom (Reddit agrégé) ...");       ape = fetch_apewisdom()
    print("  → StockTwits (tendances) ...");           st = fetch_stocktwits()
    print("  → Wikipédia (pages vues) ...");           wiki = fetch_wikipedia(content.get("wiki_titles", {}))
    print("  → Google Trends (au mieux) ...");         gt = fetch_google_trends(content.get("trends_keywords", []))
    names = {x["ticker"]: x["name"] for k in ("undervalued", "overvalued") for x in content.get(k, [])}
    ticks = list(names)
    print("  → SEC EDGAR (formulaire 4) ...");         edgar = fetch_edgar(ticks)
    ambiguous = {"NOW", "ON", "S", "NET", "A", "ALL", "IT", "KD"}
    yq = {t: f"{names[t] if t in ambiguous else t} stock" for t in ticks}
    print("  → YouTube (vidéos les plus vues) ...");   yt = fetch_youtube(yq)
    return {"ape": ape, "stocktwits": st, "wiki": wiki, "trends": gt, "edgar": edgar, "youtube": yt}


def fake_social(content: Dict[str, Any], tickers: List[str]) -> Dict[str, Any]:
    """Données SYNTHÉTIQUES pour le mode --demo."""
    import numpy as np
    rng = np.random.default_rng(11)
    pool = list(dict.fromkeys(tickers + ["GME", "SPY", "QQQ", "BAC", "JPM"]))[:30]
    stocks = []
    for i, t in enumerate(sorted(pool, key=lambda _: rng.random())[:25], 1):
        m = int(rng.integers(20, 400) * (26 - i) / 5)
        stocks.append({"rank": i, "ticker": t, "name": t, "mentions": m, "upvotes": m * int(rng.integers(3, 20)),
                       "rank_24h": max(1, i + int(rng.integers(-5, 6))), "mentions_24h": max(1, int(m * rng.uniform(0.6, 1.4)))})
    crypto = [{"rank": i + 1, "ticker": t, "name": n, "mentions": int(rng.integers(30, 300)), "upvotes": 0,
               "rank_24h": i + 1, "mentions_24h": int(rng.integers(30, 300))}
              for i, (t, n) in enumerate([("BTC", "Bitcoin"), ("ETH", "Ethereum"), ("SOL", "Solana"), ("XRP", "XRP"), ("DOGE", "Dogecoin")])]
    st_rows = [{"rank": i + 1, "symbol": t, "title": t, "score": round(float(rng.uniform(3, 12)), 2), "watchlist": int(rng.integers(5000, 300000))}
               for i, t in enumerate(pool[:12])]
    wiki = {t: {"avg7": float(rng.integers(800, 9000)), "prev7": 1000.0, "chg": float(rng.normal(3, 18))} for t in tickers}
    trends = {"available": True, "rows": [{"keyword": k, "current": float(rng.integers(20, 90)), "baseline": float(rng.integers(20, 90)),
                                          "chg": float(rng.normal(0, 25))} for k in content.get("trends_keywords", [])[:5]]}
    ticks = [x["ticker"] for k in ("undervalued", "overvalued") for x in content.get(k, [])]
    edgar = {"available": True, "reason": "", "days": 45, "by_ticker": {
        t: {"filings": int(rng.integers(0, 9)), "buys": float(rng.choice([0, 0, 0, 250_000, 1_200_000])),
            "sells": float(rng.choice([0, 3_000_000, 40_000_000, 120_000_000])), "buyers": int(rng.integers(0, 3))} for t in ticks}}
    yt = {"available": True, "reason": "", "by_ticker": {
        t: {"views": int(rng.integers(20_000, 2_000_000)), "total_views": int(rng.integers(50_000, 4_000_000)),
            "title": f"{t} stock: exemple de titre de vidéo (démo)", "channel": "Chaîne démo"} for t in ticks}}
    return {"edgar": edgar, "youtube": yt, "ape": {"available": True, "stocks": stocks[:15], "crypto": crypto, "by_ticker": {r["ticker"]: r for r in stocks}},
            "stocktwits": {"available": True, "rows": st_rows, "by_symbol": {r["symbol"]: r for r in st_rows}},
            "wiki": {"available": True, "by_ticker": wiki}, "trends": trends}
