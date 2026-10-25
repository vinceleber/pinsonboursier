"""
main.py — Orchestrateur : données du jour → PDF → courriel.

Usage :
  python bot/main.py            # production (GitHub Actions)
  python bot/main.py --demo     # données synthétiques, sans réseau (test de mise en page)
  python bot/main.py --no-email # produit le PDF sans l'envoyer
  python bot/main.py --no-site  # ne met pas à jour la plate-forme web (docs/data)
Configuration par variables d'environnement : GMAIL_FROM, GMAIL_APP_PASSWORD, TO_EMAILS (séparés par des virgules).
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import data_fetcher as df            # noqa: E402
from report_generator import build_report   # noqa: E402
from email_sender import send_gmail         # noqa: E402
from build_site import build_site           # noqa: E402
from watchlist import apply_watchlist       # noqa: E402


def main() -> int:
    demo, no_email = "--demo" in sys.argv, "--no-email" in sys.argv
    content = json.loads((HERE / "content.json").read_text(encoding="utf-8"))
    content["_watch"] = apply_watchlist(content, HERE.parent / "watchlist.json")

    print("[1/3] Données du jour ...")
    data = df.fake_all(content) if demo else df.fetch_all(content)
    if not demo and not data["quotes"]:
        print("[ERREUR] Aucune cotation récupérée (Yahoo Finance indisponible) — rapport non envoyé pour éviter un PDF vide.")
        return 1

    out_dir = Path(os.environ.get("OUTPUT_DIR", "/tmp/reports"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # PDF d'abord (publié aussi sur la plate-forme), mais un échec du PDF ne doit pas empêcher d'enregistrer l'historique
    print("[2/4] Génération du PDF ...")
    pdf = out_dir / f"LePinsonBoursier_{data['date_iso']}{'_DEMO' if demo else ''}.pdf"
    pdf_ok = True
    try:
        build_report(data, content, str(pdf))
    except Exception as e:                                       # noqa: BLE001
        pdf_ok = False
        print(f"[ERREUR] PDF non généré : {e}")

    if "--no-site" not in sys.argv:
        print("[3/4] Plate-forme web (historique) ...")
        site_dir = out_dir / "site_demo" if demo else Path(os.environ.get("SITE_DIR", str(HERE.parent / "docs")))
        try:
            build_site(data, content, site_dir, static_src=HERE.parent / "docs" if demo else None, pdf_path=pdf if pdf_ok else None)
        except Exception as e:                                   # noqa: BLE001
            print(f"[WARN] Plate-forme web non mise à jour : {e}")
    if not pdf_ok:
        return 1

    if no_email or demo and not os.environ.get("FORCE_EMAIL"):
        print("[4/4] Envoi ignoré.")
        return 0

    print("[4/4] Envoi Gmail ...")
    cfg = {"GMAIL_FROM": os.environ.get("GMAIL_FROM", ""),
           "GMAIL_APP_PASSWORD": os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", ""),
           "TO_EMAILS": [e.strip() for e in os.environ.get("TO_EMAILS", "").split(",") if e.strip()]}
    try:
        send_gmail(cfg, str(pdf), data)
    except Exception as e:
        print(f"[ERREUR] Envoi échoué : {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
