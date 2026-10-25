"""
build_site.py — Génère les fichiers de données de la plate-forme web (dossier docs/data).

Principe : chaque exécution quotidienne
  1. réécrit les historiques de prix (5 ans) et les indicateurs calculés (RSI, MACD, MA50, MA200);
  2. CUMULE ce qui n'existe nulle part ailleurs : instantanés quotidiens des signaux, mentions sociales, activité des
     initiés, Fear & Greed, lectures AAII, archive des faits saillants. L'historique grandit donc chaque jour.

Format des fichiers : `SI.reg("clé", {...});` (JavaScript, pas JSON) afin que le site fonctionne aussi bien
hébergé (GitHub Pages) qu'ouvert directement depuis le disque (file://), sans serveur.
"""
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

import data_fetcher as df
import social_fetcher as sf
from indicators import series as ind_series
from report_generator import (aaii_signal, fg_signal, insider_signal, ma200_signal, macd_signal, pe_signal, rsi_signal,
                              social_signal, vix_signal)

SNAP_CAP = 800          # instantanés conservés par société (~3 ans de jours ouvrables)
SOC_CAP = 800
DAILY_CAP = 1500
PROXY_NAMES = {"DECK": "Deckers Outdoor (HOKA)", "RDDT": "Reddit", "SHOP": "Shopify"}
INDEX_MAP = {"SP500": ("S&P 500", "^GSPC"), "NASDAQ": ("Nasdaq", "^IXIC"), "TSX": ("TSX", "^GSPTSE"),
             "VIX": ("VIX", "^VIX"), "BTC": ("Bitcoin (USD)", "BTC-USD")}


# ── lecture / écriture ──────────────────────────────────────────────────────
def _clean(o):
    if isinstance(o, float):
        return None if (o != o or o in (float("inf"), float("-inf"))) else o
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating,)):
        return _clean(float(o))
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


def write_reg(path: Path, key: str, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(_clean(obj), ensure_ascii=False, separators=(",", ":"))
    path.write_text(f'SI.reg({json.dumps(key)},{body});\n', encoding="utf-8")


def read_reg(path: Path) -> Optional[Any]:
    try:
        m = re.match(r'^SI\.reg\("[^"]*",(.*)\);\s*$', path.read_text(encoding="utf-8"), re.S)
        return json.loads(m.group(1)) if m else None
    except Exception:
        return None


def _r(x, d=2):
    return None if x is None or x != x else round(float(x), d)


# ── univers de sociétés ─────────────────────────────────────────────────────
def build_universe(content: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    comps: Dict[str, Dict[str, Any]] = {}

    def add(t, name, industry=None, lst=None, sub="", note="", ed=None):
        c = comps.setdefault(t, {"t": t, "n": name, "ind": None, "sub": "", "note": "", "lists": [], "type": "stock"})
        if lst and lst not in c["lists"]:
            c["lists"].append(lst)
        if industry and not c["ind"]:
            c["ind"] = industry
        if sub and not c["sub"]:
            c["sub"] = sub
        if note and not c["note"]:
            c["note"] = note
        if ed is not None:
            c["ed"] = ed

    for lst in ("undervalued", "overvalued"):
        for it in content.get(lst, []):
            ed = {k: it.get(k) for k in ("target", "sector_pe", "conviction", "risk", "insider")}
            ed["pe_fwd"] = it.get("pe_fwd", it.get("pe"))
            add(it["ticker"], it["name"], it.get("industry"), lst, sub=it.get("sector", ""), ed=ed)
    defaults = content.get("industry_defaults", {})
    for lst in ("semis", "cyber", "retail"):
        for it in content.get(lst, []):
            add(it["ticker"], it["name"], defaults.get(lst), lst, note=it.get("note", ""))
    over = content.get("industry_overrides", {})
    for b in content.get("brands", []):
        if b.get("proxy"):
            add(b["proxy"], PROXY_NAMES.get(b["proxy"], b["brand"]), over.get(b["proxy"]), "brands", note=b.get("theme", ""))
    for it in content.get("universe_extra", []):
        add(it["ticker"], it.get("name", it["ticker"]), it.get("industry"), "extra", note=it.get("note", ""))
    for t, c in comps.items():
        c["ind"] = over.get(t) or c["ind"] or "Autres"
        c["src"] = "ajout" if "extra" in c["lists"] else "liste"
    for t in content.get("watch_remove", []):
        comps.pop(t, None)
    return comps


def _verdict(sigs: List[str]) -> str:
    buy, sell = sigs.count("ACHAT"), sigs.count("VENTE")
    if buy >= 6: return "FORT ACHAT"
    if buy >= 4: return "ACHAT"
    if sell >= 6: return "FORT VENTE"
    if sell >= 4: return "VENTE"
    if sell >= 3: return "PRUDENCE"
    return "NEUTRE"


def _perf(close: pd.Series) -> Dict[str, Any]:
    last = float(close.iloc[-1])

    def pct(n):
        return _r((last / float(close.iloc[-1 - n]) - 1) * 100, 2) if len(close) > n else None
    year = close.index[-1].year
    prev_year = close[close.index.year < year]
    base = float(prev_year.iloc[-1]) if len(prev_year) else float(close[close.index.year == year].iloc[0])
    w = close.iloc[-252:]
    return {"chg1d": pct(1), "chg1m": pct(21), "chg3m": pct(63), "chg6m": pct(126), "chg1y": pct(252),
            "ytd": _r((last / base - 1) * 100, 2), "hi52": _r(w.max()), "lo52": _r(w.min()),
            "from_hi": _r((last / float(w.max()) - 1) * 100, 1)}


# ── construction ────────────────────────────────────────────────────────────
def _valuation(lists, pe, spe) -> Dict[str, Any]:
    """Sous-évalué / surévalué : liste éditoriale du rapport en priorité, sinon ratio P/E ÷ médiane du secteur."""
    ratio = round(pe / spe, 2) if pe and spe else None
    tail = f" (P/E ÷ secteur : {str(ratio).replace('.', ',')})" if ratio is not None else ""
    if "undervalued" in lists:
        return {"label": "Sous-évalué", "basis": "Liste du rapport" + tail, "ratio": ratio}
    if "overvalued" in lists:
        return {"label": "Surévalué", "basis": "Liste du rapport" + tail, "ratio": ratio}
    if ratio is not None:
        lab = "Sous-évalué" if ratio < 0.85 else "Surévalué" if ratio > 1.5 else "Valeur juste"
        return {"label": lab, "basis": "P/E ÷ secteur : " + str(ratio).replace(".", ","), "ratio": ratio}
    return {"label": "N/D", "basis": "Pas de P/E saisi", "ratio": None}


def publish_pdf(pdf_path: Path, site_dir: Path, date_iso: str, keep: int = 30) -> Dict[str, Any]:
    """Copie le PDF du jour dans docs/rapports (dernier.pdf + archive datée) et renvoie l'index pour le site."""
    rdir = site_dir / "rapports"
    rdir.mkdir(parents=True, exist_ok=True)
    dated = rdir / f"LePinsonBoursier_{date_iso}.pdf"
    shutil.copy2(pdf_path, dated)
    shutil.copy2(pdf_path, rdir / "dernier.pdf")
    files = sorted(rdir.glob("LePinsonBoursier_*.pdf"), reverse=True)
    for old in files[keep:]:
        old.unlink()
    files = files[:keep]
    return {"latest": "rapports/dernier.pdf", "date": date_iso, "size": dated.stat().st_size,
            "archive": [{"d": f.stem.split("_")[1], "f": "rapports/" + f.name} for f in files]}


def build_site(data: Dict[str, Any], content: Dict[str, Any], site_dir: Path, static_src: Optional[Path] = None,
               pdf_path: Optional[Path] = None) -> Dict[str, Any]:
    site_dir = Path(site_dir)
    ddir = site_dir / "data"
    closes: Dict[str, pd.Series] = dict(df.LAST_CLOSES)
    if not closes:
        raise RuntimeError("aucun historique de prix disponible (Yahoo Finance)")

    site_dir.mkdir(parents=True, exist_ok=True)
    # fichiers statiques de l'interface (démo : copie hors du dépôt)
    if static_src and Path(static_src).resolve() != site_dir.resolve():
        for item in Path(static_src).iterdir():
            if item.name == "data":
                continue
            dst = site_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)

    # données de démonstration et données réelles ne se mélangent jamais
    old_meta = read_reg(ddir / "meta.js") if ddir.exists() else None
    if old_meta and bool(old_meta.get("demo")) != bool(data["demo"]):
        shutil.rmtree(ddir)
    (ddir / "t").mkdir(parents=True, exist_ok=True)

    today = data["date_iso"]
    comps = build_universe(content)
    quotes = data["quotes"]
    fgs = data["fg_stocks"]["score"]
    vixq = data["indices"].get("^VIX")
    vix = vixq["price"] if vixq else None
    aa = content["aaii"]
    spread = round(aa["bull"] - aa["bear"], 1)
    soc = data.get("social") or {}
    ape, stw = soc.get("ape") or {}, soc.get("stocktwits") or {}
    wk, yt, ed_ = soc.get("wiki") or {}, soc.get("youtube") or {}, soc.get("edgar") or {}

    # séries Wikipédia (rétro-remplissage sur un an)
    titles = {t: v for t, v in content.get("wiki_titles", {}).items() if t in comps}
    if data["demo"]:
        rng = np.random.default_rng(5)
        days = pd.date_range(end=pd.Timestamp(today) - pd.Timedelta(days=1), periods=365)
        wiki_series = {t: {"d": [d.strftime("%Y-%m-%d") for d in days],
                           "v": [int(x) for x in np.maximum(200, 3000 * np.exp(np.cumsum(rng.normal(0, 0.03, 365))) * rng.uniform(0.7, 1.3, 365))]}
                       for t in titles}
    else:
        print("  → Wikipédia (historique d'un an) ...")
        wiki_series = sf.fetch_wikipedia_series(titles)

    sig_counts = {"ACHAT": 0, "NEUTRE": 0, "PRUDENCE": 0, "VENTE": 0}
    above200 = n200 = 0
    rsis: List[float] = []
    universe: List[Dict[str, Any]] = []

    for t, c in sorted(comps.items()):
        close = closes.get(t)
        q = quotes.get(t)
        if close is None or len(close) < 30 or not q:
            continue
        ed = c.get("ed") or {}
        s = ind_series(close)
        # --- métriques du jour
        rec = dict(c)
        rec.update(_perf(close))
        rec.update({"price": _r(q["price"]), "rsi": q["rsi"], "macd_hist": _r(q["macd_hist"], 3), "ma50": _r(q["ma50"]),
                    "ma200": _r(q["ma200"]), "trend": q["trend"], "signal": q["signal"],
                    "spark": [_r(x) for x in close.iloc[-60:].tolist()]})
        tg, pe = ed.get("target"), ed.get("pe_fwd")
        rec["upside"] = _r((tg / q["price"] - 1) * 100, 1) if tg else None
        # --- social du jour
        a = (ape.get("by_ticker") or {}).get(t.split(".")[0]) if ape.get("available") else None
        sts = (stw.get("by_symbol") or {}).get(t) if stw.get("available") else None
        yv = (yt.get("by_ticker") or {}).get(t) if yt.get("available") else None
        ev = (ed_.get("by_ticker") or {}).get(t) if ed_.get("available") else None
        ws = (wk.get("by_ticker") or {}).get(t) if wk.get("available") else None
        rec["soc"] = {"men": a["mentions"] if a else None, "ape_rank": a["rank"] if a else None,
                      "men24": a.get("mentions_24h") if a else None, "st_rank": sts["rank"] if sts else None,
                      "wiki_chg": _r(ws["chg"], 1) if ws and ws.get("chg") is not None else None,
                      "yt_views": yv["views"] if yv else None, "yt_title": yv["title"] if yv else None,
                      "yt_channel": yv["channel"] if yv else None,
                      "buys": _r(ev["buys"], 0) if ev else None, "sells": _r(ev["sells"], 0) if ev else None}
        # --- confluence (mêmes règles que le rapport PDF)
        item = {"ticker": t, "insider": ed.get("insider", "NEUTRE")}
        sigs = [pe_signal(pe, ed.get("sector_pe")), fg_signal(fgs), vix_signal(vix), rsi_signal(q["rsi"]),
                macd_signal(q["macd_hist"]), ma200_signal(q), social_signal(t, data), insider_signal(item, data), aaii_signal(spread)]
        rec["conf"] = {"sigs": sigs, "verdict": _verdict(sigs), "buy": sigs.count("ACHAT"), "sell": sigs.count("VENTE")}
        rec["val"] = _valuation(c["lists"], pe, ed.get("sector_pe"))
        universe.append(rec)

        sig_counts[q["signal"]] = sig_counts.get(q["signal"], 0) + 1
        if q["above_ma200"] is not None:
            n200 += 1
            above200 += 1 if q["above_ma200"] else 0
        if q["rsi"] is not None:
            rsis.append(q["rsi"])

        # --- fichier détaillé de la société (cumul des anciennes données)
        path = ddir / "t" / f"{t}.js"
        old = read_reg(path) or {}
        snaps = [x for x in old.get("snaps", []) if x.get("d") != today]
        snaps.append({"d": today, "p": rec["price"], "sig": q["signal"], "v": rec["conf"]["verdict"], "rsi": q["rsi"],
                      "mh": rec["macd_hist"], "tr": q["trend"], "so": sigs[6], "in": sigs[7], "b": rec["conf"]["buy"], "s": rec["conf"]["sell"]})
        sc = old.get("soc") or {"d": [], "men": [], "st": [], "yt": [], "buy": [], "sell": []}
        vals = [rec["soc"]["men"], rec["soc"]["st_rank"], rec["soc"]["yt_views"], rec["soc"]["buys"], rec["soc"]["sells"]]
        if any(v is not None for v in vals):
            if today in sc["d"]:
                i = sc["d"].index(today)
                for k, v in zip(("men", "st", "yt", "buy", "sell"), vals):
                    sc[k][i] = v
            else:
                sc["d"].append(today)
                for k, v in zip(("men", "st", "yt", "buy", "sell"), vals):
                    sc[k].append(v)
        for k in sc:
            sc[k] = sc[k][-SOC_CAP:]
        detail = dict(s)
        detail.update({"t": t, "snaps": snaps[-SNAP_CAP:], "soc": sc,
                       "wiki": wiki_series.get(t) or old.get("wiki"), "updated": today})
        write_reg(path, f"t:{t}", detail)

    # ── marché : indices, F&G, AAII, instantanés quotidiens, archive éditoriale
    mpath = ddir / "market.js"
    old_m = read_reg(mpath) or {}
    idx = {}
    for key, (label, sym) in INDEX_MAP.items():
        ser = closes.get(sym)
        if ser is not None and len(ser) > 5:
            idx[key] = {"n": label, "d": [d.strftime("%Y-%m-%d") for d in ser.index], "v": [_r(x) for x in ser.tolist()]}
        elif old_m.get("idx", {}).get(key):
            idx[key] = old_m["idx"][key]

    def merge_series(old_s, new_pairs):
        m = dict(zip(old_s.get("d", []), old_s.get("v", []))) if old_s else {}
        for d_, v_ in new_pairs:
            m[d_] = v_
        ks = sorted(m)
        return {"d": ks, "v": [m[k] for k in ks]}
    fg_s = merge_series(old_m.get("fg_s"), data["fg_stocks"].get("series", []) or ([(today, fgs)] if fgs is not None else []))
    fgc_score = data["fg_crypto"]["score"]
    fg_c = merge_series(old_m.get("fg_c"), data["fg_crypto"].get("series", []) or ([(today, fgc_score)] if fgc_score is not None else []))

    aaii = [x for x in old_m.get("aaii", []) if x.get("d") != aa["as_of"]]
    aaii.append({"d": aa["as_of"], "bull": aa["bull"], "neutral": aa["neutral"], "bear": aa["bear"], "spread": spread})
    aaii.sort(key=lambda x: x["d"])

    daily = [x for x in old_m.get("daily", []) if x.get("d") != today]
    daily.append({"d": today, "fg_s": fgs, "fg_c": fgc_score, "vix": _r(vix), "n_sig": sig_counts,
                  "pct200": _r(100 * above200 / n200, 1) if n200 else None, "rsi_avg": _r(sum(rsis) / len(rsis), 1) if rsis else None})

    arch = old_m.get("archive", [])
    if content["editorial_as_of"] not in {a.get("as_of") for a in arch}:
        arch.append({"as_of": content["editorial_as_of"], "d": today, "items": content["highlights"]})

    crypto = {k: {"price": v.get("price"), "chg_24h": _r(v.get("chg_24h"), 2)} for k, v in (data.get("crypto") or {}).items()}
    market = {"idx": idx, "fg_s": fg_s, "fg_c": fg_c, "fg_now": {"s": {"score": fgs, "label": data["fg_stocks"]["label"]},
                                                                  "c": {"score": fgc_score, "label": data["fg_crypto"]["label"]}},
              "crypto": crypto, "aaii": aaii, "aaii_signals": aa.get("signals", []), "aaii_note": aa.get("reading_note", ""),
              "daily": daily[-DAILY_CAP:], "archive": arch[-120:],
              "editorial": {"as_of": content["editorial_as_of"], "highlights": content["highlights"],
                            "details": content.get("detail_blocks", []), "valuation_note": content.get("valuation_note", "")}}
    write_reg(mpath, "market", market)

    # ── univers + sources + méta
    brands = [{"brand": b["brand"], "status": b.get("status", ""), "theme": b.get("theme", ""), "proxy": b.get("proxy")}
              for b in content.get("brands", [])]
    industries = sorted({u["ind"] for u in universe})
    watch = content.get("_watch", {"add": [], "remove": [], "move": {}})
    have = {u["t"] for u in universe}
    watch["missing"] = [a["ticker"] for a in watch.get("add", []) if a["ticker"] not in have]
    write_reg(ddir / "universe.js", "universe", {"companies": universe, "industries": industries, "brands": brands, "watch": watch})
    write_reg(ddir / "sources.js", "sources", {"catalogue": content.get("social_sources", []), "manual_watch": content.get("manual_watch", {})})

    status = [("Yahoo Finance (cours)", bool(universe)), ("CNN Fear & Greed", fgs is not None), ("Fear & Greed crypto", fgc_score is not None),
              ("CoinGecko", bool(crypto)), ("Reddit direct", bool(data["reddit"].get("available"))), ("ApeWisdom", bool(ape.get("available"))),
              ("StockTwits", bool(stw.get("available"))), ("Wikipédia", bool(wk.get("available"))),
              ("Google Trends", bool((soc.get("trends") or {}).get("available"))), ("SEC EDGAR", bool(ed_.get("available"))),
              ("YouTube", bool(yt.get("available")))]
    meta = {"empty": False, "demo": bool(data["demo"]), "generated": datetime.now().isoformat(timespec="seconds"), "date_iso": today,
            "date_fr": data["date_fr"], "editorial_as_of": content["editorial_as_of"], "n": len(universe),
            "status": [{"n": n, "ok": ok} for n, ok in status], "history_from": min(d["d"] for d in daily) if daily else today,
            "version": 1}
    if pdf_path and Path(pdf_path).exists():
        meta["pdf"] = publish_pdf(Path(pdf_path), site_dir, today)
    elif old_meta and old_meta.get("pdf") and not data["demo"]:
        meta["pdf"] = old_meta["pdf"]                       # PDF du jour indisponible : on garde le dernier connu
    write_reg(ddir / "meta.js", "meta", meta)
    print(f"  [OK] Plate-forme web : {len(universe)} sociétés, {len(industries)} industries → {site_dir}")
    return meta
