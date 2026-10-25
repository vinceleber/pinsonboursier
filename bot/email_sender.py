"""email_sender.py — Envoi du rapport par Gmail (SMTP SSL + mot de passe d'application)."""
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from pathlib import Path


def _fmt(x, d=1, sign=False):
    if x is None:
        return "N/D"
    return (f"{x:+,.{d}f}" if sign else f"{x:,.{d}f}").replace("-", "−")


def build_html(data: dict) -> str:
    fgs, fgc, crypto = data["fg_stocks"], data["fg_crypto"], data["crypto"]
    idx = data["indices"]
    vix, spx, tsx = idx.get("^VIX"), idx.get("^GSPC"), idx.get("^GSPTSE")
    btc = crypto.get("BTC")

    def cell(label, value, sub):
        return (f'<td style="width:25%;padding:12px 6px;text-align:center;border:1px solid #CBD5E1;">'
                f'<div style="font-size:10px;color:#64748B;font-weight:700;">{escape(label)}</div>'
                f'<div style="font-size:18px;font-weight:800;color:#0F2044;">{escape(value)}</div>'
                f'<div style="font-size:11px;color:#64748B;">{escape(sub)}</div></td>')

    cells = "".join([
        cell("F&G ACTIONS", str(fgs["score"]) if fgs["score"] is not None else "N/D", fgs["label"]),
        cell("F&G CRYPTO", str(fgc["score"]) if fgc["score"] is not None else "N/D", fgc["label"]),
        cell("VIX", _fmt(vix["price"], 2) if vix else "N/D", _fmt(vix["chg_1d"], 1, True) + " %" if vix else ""),
        cell("BITCOIN", f"${btc['price']:,.0f}" if btc else "N/D", _fmt(btc["chg_24h"], 1, True) + " % (24 h)" if btc else ""),
    ])
    demo = ('<p style="color:#DC2626;font-weight:700;">MODE DÉMONSTRATION — données synthétiques</p>' if data.get("demo") else "")
    return f"""<!DOCTYPE html><html lang="fr"><body style="margin:0;background:#F1F5F9;font-family:Arial,Helvetica,sans-serif;">
<div style="max-width:620px;margin:0 auto;padding:18px;">
<div style="background:#0F2044;color:#fff;border-radius:10px;padding:22px;text-align:center;">
<div style="font-size:11px;letter-spacing:3px;color:#93C5FD;">LE PINSON BOURSIER  ·  SOCIAL INVESTING</div>
<div style="font-size:24px;font-weight:800;margin:6px 0;">Rapport quotidien</div>
<div style="font-size:13px;color:#CBD5E1;">{escape(data['date_long_fr'])}</div></div>
{demo}
<table style="width:100%;border-collapse:collapse;margin:14px 0;background:#fff;"><tr>{cells}</tr></table>
<div style="background:#fff;border:1px solid #CBD5E1;border-radius:10px;padding:14px;font-size:13px;color:#334155;">
Le rapport complet (analyse technique, listes sous-évaluées / surévaluées, matrices de confluence, secteurs, AAII, verdict) est en pièce jointe (PDF).
<br><br><span style="font-size:11px;color:#64748B;">Les cours d'actions sont les clôtures du jour. « N/D » = source indisponible aujourd'hui.</span></div>
<p style="font-size:10px;color:#94A3B8;text-align:center;">À titre informatif seulement. Ne constitue pas un conseil en placement.</p>
</div></body></html>"""


def send_gmail(config: dict, pdf_path: str, data: dict) -> None:
    sender, password, recipients = config["GMAIL_FROM"], config["GMAIL_APP_PASSWORD"], config["TO_EMAILS"]
    if not (sender and password and recipients):
        raise ValueError("GMAIL_FROM, GMAIL_APP_PASSWORD et TO_EMAILS sont requis")
    msg = MIMEMultipart("mixed")
    msg["From"] = f"Le Pinson Boursier <{sender}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"Le Pinson Boursier — Rapport du {data['date_fr']}" + (" [DÉMO]" if data.get("demo") else "")
    msg.attach(MIMEText(build_html(data), "html", "utf-8"))
    p = Path(pdf_path)
    part = MIMEBase("application", "pdf")
    part.set_payload(p.read_bytes())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=p.name)
    msg.attach(part)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(sender, password)
        s.sendmail(sender, recipients, msg.as_string())
    print(f"  [OK] Courriel envoyé à {len(recipients)} destinataire(s)")
