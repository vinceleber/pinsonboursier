"""
indicators.py — Indicateurs techniques calculés localement à partir de l'historique de prix.
Aucune donnée "approximative" : tout vient des clôtures quotidiennes (yfinance).
"""
from typing import Optional, Dict, Any
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    """RSI de Wilder (lissage exponentiel alpha=1/period)."""
    close = close.dropna()
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    last_gain, last_loss = float(avg_gain.iloc[-1]), float(avg_loss.iloc[-1])
    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    return round(100 - 100 / (1 + rs), 1)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Dict[str, float]]:
    """MACD (12,26,9) : ligne, signal et histogramme."""
    close = close.dropna()
    if len(close) < slow + signal:
        return None
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False).mean()
    hist = line - sig
    return {"line": float(line.iloc[-1]), "signal": float(sig.iloc[-1]), "hist": float(hist.iloc[-1])}


def sma(close: pd.Series, window: int) -> Optional[float]:
    close = close.dropna()
    if len(close) < window:
        return None
    return float(close.iloc[-window:].mean())


def rsi_label(value: Optional[float]) -> str:
    if value is None:
        return "N/D"
    if value < 30:
        return "Survendu"
    if value > 70:
        return "Surachat"
    return "Neutre"


def trend_label(ma50: Optional[float], ma200: Optional[float]) -> str:
    """Golden Cross = MA50 > MA200 ; Death Cross = MA50 < MA200 ; Neutre si écart < 0,5 %."""
    if ma50 is None or ma200 is None or ma200 == 0:
        return "N/D"
    gap = ma50 / ma200 - 1
    if abs(gap) < 0.005:
        return "Neutre"
    return "Golden Cross" if gap > 0 else "Death Cross"


def global_signal(price, rsi_v, macd_hist, ma50, ma200) -> str:
    """
    Score simple et transparent (documenté dans le rapport) :
      RSI < 30  : +1 (survente, rebond possible)   | RSI > 70 : -1
      MACD histogramme > 0 : +1 sinon -1
      Prix > MA200 : +1 sinon -1
      MA50 > MA200 : +1 sinon -1
    Total >= 3 : ACHAT | <= -3 : VENTE | <= -1 : PRUDENCE | sinon NEUTRE
    """
    score, used = 0, 0
    if rsi_v is not None:
        used += 1
        score += 1 if rsi_v < 30 else (-1 if rsi_v > 70 else 0)
    if macd_hist is not None:
        used += 1
        score += 1 if macd_hist > 0 else -1
    if price is not None and ma200 is not None:
        used += 1
        score += 1 if price > ma200 else -1
    if ma50 is not None and ma200 is not None:
        used += 1
        score += 1 if ma50 > ma200 else -1
    if used < 3:
        return "N/D"
    if score >= 3:
        return "ACHAT"
    if score <= -3:
        return "VENTE"
    if score <= -1:
        return "PRUDENCE"
    return "NEUTRE"


def analyze(close: pd.Series) -> Dict[str, Any]:
    """Analyse complète d'une série de clôtures (ordre chronologique)."""
    close = close.dropna()
    if close.empty:
        return {}
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) >= 2 else price
    month_ago = float(close.iloc[-22]) if len(close) >= 22 else float(close.iloc[0])
    r = rsi(close)
    m = macd(close)
    ma50, ma200 = sma(close, 50), sma(close, 200)
    hist = m["hist"] if m else None
    return {
        "price": price,
        "chg_1d": (price / prev - 1) * 100 if prev else 0.0,
        "chg_1m": (price / month_ago - 1) * 100 if month_ago else 0.0,
        "rsi": r,
        "rsi_label": rsi_label(r),
        "macd_line": m["line"] if m else None,
        "macd_hist": hist,
        "macd_label": "N/D" if hist is None else ("Achat" if hist > 0 else "Vente"),
        "ma50": ma50,
        "ma200": ma200,
        "trend": trend_label(ma50, ma200),
        "signal": global_signal(price, r, hist, ma50, ma200),
        "above_ma200": (price > ma200) if ma200 is not None else None,
    }


def series(close: pd.Series) -> Dict[str, Any]:
    """Séries complètes alignées sur les clôtures (pour les graphiques de la plate-forme web).
    Mêmes formules que analyze() : RSI de Wilder (14), MACD (12, 26, 9), moyennes mobiles simples 50 et 200."""
    close = close.dropna()
    n = len(close)
    delta = close.diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    ag, al = gain.ewm(alpha=1 / 14, adjust=False).mean(), loss.ewm(alpha=1 / 14, adjust=False).mean()
    rs = ag / al.replace(0, float("nan"))
    rsi_s = 100 - 100 / (1 + rs)
    rsi_s = rsi_s.where(al != 0, 100.0)
    rsi_s.iloc[:14] = float("nan")
    ef, es = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    line = ef - es
    sig = line.ewm(span=9, adjust=False).mean()
    hist = line - sig
    for ser in (line, sig, hist):
        ser.iloc[:33] = float("nan")
    ma50, ma200 = close.rolling(50).mean(), close.rolling(200).mean()

    def clean(x, d):
        return [None if (v != v) else round(float(v), d) for v in x.tolist()]
    return {"dates": [d.strftime("%Y-%m-%d") for d in close.index], "close": clean(close, 2),
            "ma50": clean(ma50, 2), "ma200": clean(ma200, 2), "rsi": clean(rsi_s, 1),
            "macd": clean(line, 3), "macd_sig": clean(sig, 3), "macd_hist": clean(hist, 3)}
