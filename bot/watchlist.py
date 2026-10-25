"""watchlist.py — Gestion manuelle des titres suivis (fichier watchlist.json à la racine du dépôt).

  add    : [{"ticker": "META", "name": "Meta Platforms", "industry": "Plateformes Internet", "note": "", "wiki": "Meta_Platforms"}]
  remove : ["INTC", "DUOL"]            -> retirés de la plate-forme web (le PDF garde ses listes éditoriales)
  move   : {"AMZN": "Commerce de détail"} -> change l'industrie affichée
Les symboles ajoutés sont téléchargés (5 ans d'historique) dès la prochaine exécution.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict

TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-^=]{0,14}$")


def apply_watchlist(content: Dict[str, Any], path: Path) -> Dict[str, Any]:
    """Fusionne watchlist.json dans content (en mémoire) et retourne le résumé affiché sur la page « Gérer »."""
    wl: Dict[str, Any] = {}
    try:
        if path.exists():
            wl = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:                                           # noqa: BLE001
        print(f"[WARN] watchlist.json illisible, ignoré : {e}")
    add = []
    for it in wl.get("add", []) or []:
        t = str(it.get("ticker", "")).strip().upper()
        if not TICKER_RE.match(t):
            print(f"[WARN] watchlist : symbole invalide ignoré : {it.get('ticker')!r}")
            continue
        add.append({"ticker": t, "name": (it.get("name") or t).strip(), "industry": (it.get("industry") or "Autres").strip(),
                    "note": (it.get("note") or "").strip(), "wiki": (it.get("wiki") or "").strip()})
    remove = sorted({str(t).strip().upper() for t in (wl.get("remove") or []) if str(t).strip()})
    move = {str(k).strip().upper(): str(v).strip() for k, v in (wl.get("move") or {}).items() if str(v).strip()}

    extra = list(content.get("universe_extra", []))
    known = {x["ticker"] for x in extra}
    for it in add:
        if it["ticker"] not in known:
            extra.append({k: it[k] for k in ("ticker", "name", "industry", "note")})
        if it["wiki"]:
            content.setdefault("wiki_titles", {})[it["ticker"]] = it["wiki"]
    content["universe_extra"] = extra
    # tout titre de universe_extra doit être téléchargé
    content["extra_tickers"] = sorted(set(content.get("extra_tickers", [])) | {x["ticker"] for x in extra})
    content.setdefault("industry_overrides", {}).update(move)
    content["watch_remove"] = remove
    return {"add": add, "remove": remove, "move": move}
