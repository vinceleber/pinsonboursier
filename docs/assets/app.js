/* Social Investing — plateforme web (JS natif, sans dépendance, fonctionne en file:// et en http) */
(function () {
  "use strict";
  var SI = (window.SI = { data: {}, reg: function (k, o) { SI.data[k] = o; } });
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var main = $("#main");
  var loaded = {};

  /* ── utilitaires ─────────────────────────────────────────── */
  function h(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      var v = attrs[k];
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), v);
      else if (k === "text") e.textContent = v;
      else e.setAttribute(k, v === true ? "" : v);
    }
    (Array.isArray(kids) ? kids : kids == null ? [] : [kids]).forEach(function (c) {
      if (c == null || c === false) return;
      e.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    });
    return e;
  }
  var NS = "http://www.w3.org/2000/svg";
  function sv(tag, attrs, kids) {
    var e = document.createElementNS(NS, tag);
    if (attrs) for (var k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    (kids || []).forEach(function (c) { e.appendChild(c); });
    return e;
  }
  var nf0 = new Intl.NumberFormat("fr-CA", { maximumFractionDigits: 0 });
  var nf1 = new Intl.NumberFormat("fr-CA", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  var nf2 = new Intl.NumberFormat("fr-CA", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  function num(v, d) { if (v == null || isNaN(v)) return "N/D"; return (d === 0 ? nf0 : d === 1 ? nf1 : nf2).format(v); }
  function px(v) { if (v == null) return "N/D"; return Math.abs(v) >= 1000 ? nf0.format(v) : nf2.format(v); }
  function pct(v, d) { if (v == null || isNaN(v)) return "N/D"; return (v > 0 ? "+" : v < 0 ? "−" : "") + (d === 1 ? nf1 : nf2).format(Math.abs(v)) + " %"; }
  function cls(v) { return v > 0 ? "pos" : v < 0 ? "neg" : ""; }
  function pctEl(v, d) { return h("span", { class: cls(v) }, pct(v, d)); }
  function sigClass(s) {
    s = s || "";
    if (s.indexOf("FORT") === 0) return s.indexOf("ACHAT") > 0 ? "t-strongbuy" : "t-strongsell";
    if (s === "ACHAT") return "t-buy";
    if (s === "VENTE") return "t-sell";
    if (s === "PRUDENCE") return "t-warn";
    return "t-neu";
  }
  function tag(s) { return h("span", { class: "tag " + sigClass(s) }, s || "N/D"); }
  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* ignoré */ } }
  function css(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  function daysAgo(iso) { return Math.floor((Date.now() - Date.parse(iso)) / 864e5); }
  function enc(s) { return encodeURIComponent(s); }

  function load(src) {
    if (loaded[src]) return loaded[src];
    loaded[src] = new Promise(function (ok, ko) {
      var s = document.createElement("script");
      s.src = src; s.onload = ok;
      s.onerror = function () { delete loaded[src]; ko(new Error("Fichier introuvable : " + src)); };
      document.head.appendChild(s);
    });
    return loaded[src];
  }
  function loadTicker(t) {
    return load("data/t/" + t + ".js").then(function () { return SI.data["t:" + t]; });
  }

  function csv(name, head, rows) {
    var cell = function (v) {
      if (v == null) return "";
      if (typeof v === "number") return String(v).replace(".", ",");
      v = String(v);
      return /[;"\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
    };
    var text = "﻿" + [head].concat(rows).map(function (r) { return r.map(cell).join(";"); }).join("\r\n");
    var a = h("a", { href: URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" })), download: name });
    document.body.appendChild(a); a.click(); a.remove();
  }

  /* ── graphiques SVG ──────────────────────────────────────── */
  var groups = {};
  var tip = $("#tip");
  var MONTHS = { "1M": 1, "3M": 3, "6M": 6, "1A": 12, "3A": 36, "5A": 60, "Tout": null };
  function niceTicks(lo, hi, n) {
    if (lo === hi) { lo -= 1; hi += 1; }
    var span = hi - lo, step = Math.pow(10, Math.floor(Math.log10(span / n)));
    var err = span / n / step;
    step *= err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
    var a = Math.floor(lo / step) * step, out = [];
    for (var v = a; v <= hi + step * 0.001; v += step) out.push(+v.toFixed(10));
    return out;
  }
  function bs(arr, t) { // plus proche index
    var lo = 0, hi = arr.length - 1;
    while (hi - lo > 1) { var m = (lo + hi) >> 1; if (arr[m] <= t) lo = m; else hi = m; }
    return Math.abs(arr[lo] - t) <= Math.abs(arr[hi] - t) ? lo : hi;
  }

  /* opts: {series:[{name,color:'c1',d:[iso],v:[],type:'line'|'bar',w}], height, fmt, ref:[{y,label}], yFixed:[a,b], rebase, group, months, label} */
  function chart(opts) {
    var wrap = h("div", { class: "chart", role: "img", "aria-label": opts.label || "Graphique" });
    var legend = h("div", { class: "legend" });
    var box = h("div");
    var tblWrap = opts.table === false ? null : h("details", { class: "tbl" }, [h("summary", null, "Voir les données en tableau")]);
    var series = opts.series.map(function (s, i) {
      return { name: s.name, color: s.color || "c" + (i + 1), d: s.d, v: s.v, type: s.type || "line", t: s.d.map(function (x) { return Date.parse(x); }), on: true, dash: s.dash, w: s.w };
    });
    var st = { months: opts.months === undefined ? 12 : opts.months, cross: null };
    var H = opts.height || 260, W = 800, svg;
    var api = { el: null, setMonths: null, showAt: null };

    function range() {
      var tmax = Math.max.apply(null, series.map(function (s) { return s.t.length ? s.t[s.t.length - 1] : 0; }));
      var tmin = Math.min.apply(null, series.map(function (s) { return s.t.length ? s.t[0] : Infinity; }));
      if (st.months != null) { var dt = new Date(tmax); dt.setMonth(dt.getMonth() - st.months); tmin = Math.max(tmin, dt.getTime()); }
      return [tmin, tmax];
    }
    function visible() {
      var r = range();
      return series.filter(function (s) { return s.on; }).map(function (s) {
        var a = 0; while (a < s.t.length && s.t[a] < r[0]) a++;
        var idx = [], vals = [];
        for (var i = a; i < s.t.length; i++) { idx.push(s.t[i]); vals.push(s.v[i]); }
        if (opts.rebase) {
          var b = null; for (var j = 0; j < vals.length; j++) if (vals[j] != null) { b = vals[j]; break; }
          vals = vals.map(function (x) { return x == null || !b ? null : (x / b) * 100; });
        }
        return { s: s, t: idx, v: vals };
      });
    }
    function draw() {
      W = Math.max(280, box.clientWidth || wrap.clientWidth || 800);
      var m = { l: 46, r: 12, t: 10, b: 24 };
      var r = range(), vis = visible();
      var lo = Infinity, hi = -Infinity;
      vis.forEach(function (x) { x.v.forEach(function (y) { if (y != null) { if (y < lo) lo = y; if (y > hi) hi = y; } }); });
      (opts.ref || []).forEach(function (q) { if (opts.yFixed) return; lo = Math.min(lo, q.y); hi = Math.max(hi, q.y); });
      if (vis.some(function (x) { return x.s.type === "bar"; })) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
      if (opts.yFixed) { lo = opts.yFixed[0]; hi = opts.yFixed[1]; }
      if (!isFinite(lo)) { lo = 0; hi = 1; }
      var pad = opts.yFixed ? 0 : (hi - lo) * 0.06;
      var ticks = niceTicks(lo - pad, hi + pad, 5);
      var y0 = ticks[0], y1 = ticks[ticks.length - 1];
      var X = function (t) { return m.l + ((t - r[0]) / Math.max(1, r[1] - r[0])) * (W - m.l - m.r); };
      var Y = function (v) { return m.t + (1 - (v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b); };
      svg = sv("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, "aria-hidden": "true" });
      var grid = css("--grid"), muted = css("--muted");
      ticks.forEach(function (v) {
        svg.appendChild(sv("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: grid, "stroke-width": 1 }));
        var tx = sv("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end", fill: muted, "font-size": 11 });
        tx.textContent = (opts.fmt || function (z) { return Math.abs(z) >= 1000 ? nf0.format(z) : String(+z.toFixed(2)).replace(".", ","); })(v);
        svg.appendChild(tx);
      });
      var nx = W < 500 ? 3 : 6, spanM = (r[1] - r[0]) / 2.63e9;
      for (var i = 0; i <= nx; i++) {
        var t = r[0] + ((r[1] - r[0]) * i) / nx, dd = new Date(t);
        var tx2 = sv("text", { x: X(t), y: H - 6, "text-anchor": i === 0 ? "start" : i === nx ? "end" : "middle", fill: muted, "font-size": 11 });
        tx2.textContent = spanM <= 4 ? dd.toLocaleDateString("fr-CA", { day: "numeric", month: "short" }) : dd.toLocaleDateString("fr-CA", { month: "short", year: "2-digit" });
        svg.appendChild(tx2);
      }
      if (y0 < 0 && y1 > 0) svg.appendChild(sv("line", { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), stroke: muted, "stroke-width": 1 }));
      (opts.ref || []).forEach(function (q) {
        svg.appendChild(sv("line", { x1: m.l, x2: W - m.r, y1: Y(q.y), y2: Y(q.y), stroke: muted, "stroke-dasharray": "4 4", "stroke-width": 1 }));
        var lt = sv("text", { x: W - m.r - 2, y: Y(q.y) - 4, "text-anchor": "end", fill: muted, "font-size": 10.5 }); lt.textContent = q.label || ""; svg.appendChild(lt);
      });
      vis.forEach(function (x) {
        var col = css("--" + x.s.color);
        if (x.s.type === "bar") {
          var bw = Math.max(1, (W - m.l - m.r) / Math.max(1, x.t.length) * 0.7);
          x.t.forEach(function (t, i2) {
            var v = x.v[i2]; if (v == null) return;
            var ya = Y(Math.max(v, 0)), yb = Y(Math.min(v, 0));
            svg.appendChild(sv("rect", { x: X(t) - bw / 2, y: ya, width: bw, height: Math.max(1, yb - ya), fill: v >= 0 ? css("--c2") : css("--c5"), opacity: 0.85 }));
          });
        } else {
          var dstr = "", pen = false;
          x.t.forEach(function (t, i2) {
            var v = x.v[i2];
            if (v == null) { pen = false; return; }
            dstr += (pen ? "L" : "M") + X(t).toFixed(1) + " " + Y(v).toFixed(1); pen = true;
          });
          svg.appendChild(sv("path", { d: dstr, fill: "none", stroke: col, "stroke-width": x.s.w || 2, "stroke-linejoin": "round", "stroke-linecap": "round", "stroke-dasharray": x.s.dash || null }));
          if (x.t.length === 1 || x.t.filter(function (v, i3) { return x.v[i3] != null; }).length < 3)
            x.t.forEach(function (t, i2) { if (x.v[i2] != null) svg.appendChild(sv("circle", { cx: X(t), cy: Y(x.v[i2]), r: 3.5, fill: col, stroke: css("--surface"), "stroke-width": 2 })); });
        }
      });
      var cl = sv("line", { y1: m.t, y2: H - m.b, stroke: css("--ink2"), "stroke-width": 1, "stroke-dasharray": "3 3", visibility: "hidden" });
      var dots = vis.map(function (x) { var c = sv("circle", { r: 4, fill: css("--" + x.s.color), stroke: css("--surface"), "stroke-width": 2, visibility: "hidden" }); return c; });
      svg.appendChild(cl); dots.forEach(function (d) { svg.appendChild(d); });
      var ov = sv("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent", style: "cursor:crosshair;touch-action:pan-y" });
      svg.appendChild(ov);
      function at(t, withTip, cx, cy) {
        var info = [], px0 = X(t), best = null;
        vis.forEach(function (x, k) {
          if (!x.t.length) { dots[k].setAttribute("visibility", "hidden"); return; }
          var i2 = bs(x.t, t);
          if (Math.abs(x.t[i2] - t) > (r[1] - r[0]) * 0.05 + 864e5 * 4 || x.v[i2] == null) { dots[k].setAttribute("visibility", "hidden"); return; }
          if (best == null) best = x.t[i2];
          dots[k].setAttribute("cx", X(x.t[i2])); dots[k].setAttribute("cy", Y(x.v[i2])); dots[k].setAttribute("visibility", x.s.type === "bar" ? "hidden" : "visible");
          info.push([x.s, x.v[i2]]);
        });
        if (best == null) { cl.setAttribute("visibility", "hidden"); tip.hidden = true; return; }
        cl.setAttribute("x1", X(best)); cl.setAttribute("x2", X(best)); cl.setAttribute("visibility", "visible");
        if (withTip) {
          tip.replaceChildren();
          tip.appendChild(h("b", null, new Date(best).toLocaleDateString("fr-CA", { year: "numeric", month: "short", day: "numeric" })));
          info.forEach(function (p) {
            var f = opts.tipFmt || opts.fmt || function (z) { return num(z, 2); };
            tip.appendChild(h("div", { class: "r" }, [h("span", null, p[0].name), h("span", null, f(p[1]))]));
          });
          tip.hidden = false;
          var tw = tip.offsetWidth, th = tip.offsetHeight;
          tip.style.left = Math.min(window.innerWidth - tw - 8, Math.max(8, cx + 14)) + "px";
          tip.style.top = Math.max(8, cy - th - 12) + "px";
        }
      }
      api.showAt = function (t) { at(t, false); };
      function mv(ev) {
        var bb = ov.getBoundingClientRect(), fx = (ev.clientX - bb.left) / bb.width;
        var t = r[0] + fx * (r[1] - r[0]);
        at(t, true, ev.clientX, ev.clientY);
        (groups[opts.group] || []).forEach(function (o) { if (o !== api && o.showAt) o.showAt(t); });
      }
      function lv() {
        cl.setAttribute("visibility", "hidden"); dots.forEach(function (d) { d.setAttribute("visibility", "hidden"); }); tip.hidden = true;
        (groups[opts.group] || []).forEach(function (o) { if (o !== api && o.hide) o.hide(); });
      }
      api.hide = function () { cl.setAttribute("visibility", "hidden"); dots.forEach(function (d) { d.setAttribute("visibility", "hidden"); }); };
      ov.addEventListener("pointermove", mv); ov.addEventListener("pointerleave", lv); ov.addEventListener("pointerdown", mv);
      box.replaceChildren(svg);
    }
    function buildLegend() {
      legend.replaceChildren();
      if (series.length < 2 || opts.noLegend) return;
      series.forEach(function (s) {
        var b = h("button", { type: "button", "aria-pressed": "true" }, [h("i", { style: "background:var(--" + s.color + ")" }), s.name]);
        b.addEventListener("click", function () { s.on = !s.on; b.setAttribute("aria-pressed", String(s.on)); draw(); });
        legend.appendChild(b);
      });
    }
    function buildTable() {
      var tb = h("div", { class: "tw", style: "max-height:300px;margin-top:8px" });
      var vis = visible(), ds = {}, order = [];
      vis.forEach(function (x, k) { x.t.forEach(function (t, i) { if (!ds[t]) { ds[t] = {}; order.push(t); } ds[t][k] = x.v[i]; }); });
      order.sort(function (a, b) { return b - a; });
      var tbl = h("table", null, [h("thead", null, h("tr", null, [h("th", null, "Date")].concat(vis.map(function (x) { return h("th", { class: "n" }, x.s.name); })))),
        h("tbody", null, order.slice(0, 400).map(function (t) {
          return h("tr", null, [h("td", null, new Date(t).toISOString().slice(0, 10))].concat(vis.map(function (x, k) { return h("td", { class: "n" }, ds[t][k] == null ? "" : num(ds[t][k], 2)); })));
        }))]);
      tb.appendChild(tbl); return tb;
    }
    if (tblWrap) tblWrap.addEventListener("toggle", function () {
      if (tblWrap.open) { var old = tblWrap.querySelector(".tw"); if (old) old.remove(); tblWrap.appendChild(buildTable()); }
    });
    wrap.appendChild(legend); wrap.appendChild(box); if (tblWrap) wrap.appendChild(tblWrap);
    buildLegend();
    api.el = wrap;
    api.setMonths = function (m) { st.months = m; if (wrap.isConnected) draw(); if (tblWrap && tblWrap.open) { var o = tblWrap.querySelector(".tw"); if (o) o.remove(); tblWrap.appendChild(buildTable()); } };
    api.draw = draw;
    if (opts.group) (groups[opts.group] = groups[opts.group] || []).push(api);
    new ResizeObserver(function () { if (wrap.isConnected && box.clientWidth && Math.abs(box.clientWidth - W) > 2) draw(); }).observe(box);
    requestAnimationFrame(function () { if (wrap.isConnected) draw(); });
    setTimeout(function () { if (wrap.isConnected && !svg) draw(); }, 50);
    return api;
  }
  function rangeBar(charts, def) {
    var cur = def === undefined ? "1A" : def;
    var seg = h("div", { class: "seg", role: "group", "aria-label": "Période" });
    Object.keys(MONTHS).forEach(function (k) {
      var b = h("button", { type: "button", "aria-pressed": String(k === cur) }, k);
      b.addEventListener("click", function () {
        cur = k;
        Array.prototype.forEach.call(seg.children, function (c) { c.setAttribute("aria-pressed", String(c === b)); });
        charts.forEach(function (c) { c.setMonths(MONTHS[k]); });
      });
      seg.appendChild(b);
    });
    charts.forEach(function (c) { c.setMonths(MONTHS[cur]); });
    return seg;
  }
  function spark(vals, w, hh) {
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var d = vals.map(function (v, i) { return (i ? "L" : "M") + ((i / (vals.length - 1)) * w).toFixed(1) + " " + (hh - 2 - ((v - lo) / (hi - lo || 1)) * (hh - 4)).toFixed(1); }).join("");
    var up = vals[vals.length - 1] >= vals[0];
    return sv("svg", { class: "spark", width: w, height: hh, viewBox: "0 0 " + w + " " + hh, "aria-hidden": "true" }, [sv("path", { d: d, fill: "none", stroke: up ? css("--green") : css("--red"), "stroke-width": 1.6, "stroke-linejoin": "round" })]);
  }

  /* ── données dérivées ────────────────────────────────────── */
  var U, BYT, M, META, SRC;
  var CONF = ["P/E", "Fear & Greed", "VIX", "RSI", "MACD", "MA200", "Social", "Initiés", "AAII"];
  function idxStats(k) {
    var s = M.idx[k]; if (!s || !s.v.length) return null;
    var n = s.v.length, last = s.v[n - 1], prev = s.v[n - 2];
    var y = s.d[n - 1].slice(0, 4), base = null;
    for (var i = n - 1; i >= 0; i--) if (s.d[i].slice(0, 4) < y) { base = s.v[i]; break; }
    return { name: s.n, last: last, chg: prev ? (last / prev - 1) * 100 : null, ytd: base ? (last / base - 1) * 100 : null, date: s.d[n - 1] };
  }
  function avg(a) { a = a.filter(function (x) { return x != null; }); return a.length ? a.reduce(function (p, c) { return p + c; }, 0) / a.length : null; }
  function industryStats() {
    var by = {};
    U.forEach(function (c) { (by[c.ind] = by[c.ind] || []).push(c); });
    return Object.keys(by).sort().map(function (k) {
      var L = by[k];
      return { name: k, list: L, n: L.length, d1: avg(L.map(function (c) { return c.chg1d; })), m1: avg(L.map(function (c) { return c.chg1m; })), ytd: avg(L.map(function (c) { return c.ytd; })),
        y1: avg(L.map(function (c) { return c.chg1y; })), rsi: avg(L.map(function (c) { return c.rsi; })),
        buy: L.filter(function (c) { return c.conf.verdict.indexOf("ACHAT") >= 0; }).length, sell: L.filter(function (c) { return c.conf.verdict.indexOf("VENTE") >= 0; }).length,
        above: L.filter(function (c) { return c.price > c.ma200; }).length };
    });
  }
  function page(title, sub, right) {
    return h("div", { class: "page-head" }, [h("div", null, [h("h1", null, title), sub ? h("p", null, sub) : null]), right || null]);
  }
  function kpi(label, value, sub, subCls) {
    return h("div", { class: "card kpi" }, [h("div", { class: "l" }, label), h("div", { class: "v" }, value), h("div", { class: "s " + (subCls || "") }, sub)]);
  }
  function coLink(c) { return h("a", { href: "#/t/" + enc(c.t) }, c.t); }

  /* ── page : Marché ───────────────────────────────────────── */
  function pageMarket() {
    var root = h("div");
    root.appendChild(page("Marché", "Vue d'ensemble au " + META.date_fr + " : indices, sentiment, meneurs et signaux de confluence.", h("a", { class: "btn pri", href: "#/confluence" }, "Voir la matrice de confluence")));
    var k = h("div", { class: "grid g5" });
    ["SP500", "NASDAQ", "TSX"].forEach(function (key) {
      var s = idxStats(key); if (!s) return;
      k.appendChild(kpi(s.name, px(s.last), [pct(s.chg), " · ", pct(s.ytd), " depuis janv."].join(""), cls(s.chg)));
    });
    var v = idxStats("VIX"); if (v) k.appendChild(kpi("VIX", num(v.last, 1), v.last < 15 ? "Complaisance" : v.last > 30 ? "Peur élevée" : "Zone normale"));
    var b = idxStats("BTC"); if (b) k.appendChild(kpi("Bitcoin (USD)", px(b.last), pct(b.chg), cls(b.chg)));
    k.appendChild(kpi("Fear & Greed — actions", M.fg_now.s.score == null ? "N/D" : String(M.fg_now.s.score), M.fg_now.s.label || ""));
    k.appendChild(kpi("Fear & Greed — crypto", M.fg_now.c.score == null ? "N/D" : String(M.fg_now.c.score), M.fg_now.c.label || ""));
    var last = M.aaii[M.aaii.length - 1];
    if (last) k.appendChild(kpi("Écart AAII (haussiers − baissiers)", (last.spread > 0 ? "+" : "") + num(last.spread, 1) + " pts", "Sondage du " + last.d));
    root.appendChild(k);

    var keys = ["SP500", "NASDAQ", "TSX", "BTC"].filter(function (x) { return M.idx[x]; });
    var ch = chart({ series: keys.map(function (x, i) { return { name: M.idx[x].n, d: M.idx[x].d, v: M.idx[x].v }; }), rebase: true, height: 280, fmt: function (z) { return num(z, 0); }, tipFmt: function (z) { return num(z, 1); }, label: "Indices rebasés à 100" });
    var card = h("div", { class: "card sec" }, [h("div", { class: "ch" }, [h("h2", null, "Performance comparée (base 100)"), rangeBar([ch], "1A")]), ch.el,
      h("p", { class: "note" }, "Chaque courbe commence à 100 au début de la période choisie. Le Bitcoin est beaucoup plus volatil que les indices boursiers.")]);
    root.appendChild(card);

    var g = h("div", { class: "grid g2 sec" });
    var up = U.slice().sort(function (a, c) { return (c.chg1d || -99) - (a.chg1d || -99); });
    function mini(title, list, f) {
      return h("div", { class: "card" }, [h("h2", null, title), h("div", { class: "tw mini" }, h("table", null, h("tbody", null, list.map(function (c) {
        return h("tr", null, [h("td", { class: "tk" }, coLink(c)), h("td", { class: "nm" }, c.n), h("td", { class: "n" }, f(c))]);
      }))))]);
    }
    g.appendChild(mini("Plus fortes hausses du jour", up.slice(0, 6), function (c) { return pctEl(c.chg1d); }));
    g.appendChild(mini("Plus fortes baisses du jour", up.slice(-6).reverse(), function (c) { return pctEl(c.chg1d); }));
    var byBuy = U.slice().sort(function (a, c) { return c.conf.buy - a.conf.buy || a.conf.sell - c.conf.sell; });
    var bySell = U.slice().sort(function (a, c) { return c.conf.sell - a.conf.sell || a.conf.buy - c.conf.buy; });
    g.appendChild(mini("Meilleure confluence d'achat (sur 9 signaux)", byBuy.slice(0, 6), function (c) { return h("span", null, [c.conf.buy + " achat · ", tag(c.conf.verdict)]); }));
    g.appendChild(mini("Meilleure confluence de vente (sur 9 signaux)", bySell.slice(0, 6), function (c) { return h("span", null, [c.conf.sell + " vente · ", tag(c.conf.verdict)]); }));
    root.appendChild(g);

    var st = industryStats().sort(function (a, c) { return (c.m1 || 0) - (a.m1 || 0); });
    root.appendChild(h("div", { class: "card sec" }, [h("div", { class: "ch" }, [h("h2", null, "Industries : rendement moyen sur 1 mois"), h("a", { href: "#/industries" }, "Toutes les industries")]), hbars(st.map(function (s) { return { label: s.name, v: s.m1, href: "#/i/" + enc(s.name) }; }))]));

    var ed = M.editorial, age = daysAgo(ed.as_of);
    root.appendChild(h("div", { class: "card sec" }, [h("h2", null, "Faits saillants (éditorial du " + ed.as_of + ")"),
      age > 7 ? h("p", { class: "note" }, "Ce commentaire date de " + age + " jours : il n'est pas mis à jour automatiquement.") : null,
      h("ul", { class: "list" }, ed.highlights.map(function (t) { return h("li", null, t); }))]));
    return root;
  }
  function hbars(rows) {
    var mx = Math.max.apply(null, rows.map(function (r) { return Math.abs(r.v || 0); })) || 1;
    var box = h("div");
    rows.forEach(function (r) {
      var w = (Math.abs(r.v || 0) / mx) * 50, pos = (r.v || 0) >= 0;
      box.appendChild(h("div", { class: "hbar" }, [h("a", { href: r.href }, r.label),
        h("div", { class: "tr", "aria-hidden": "true" }, [h("div", { class: "bar", style: "background:" + (pos ? "var(--green)" : "var(--red)") + ";width:" + w + "%;" + (pos ? "left:50%" : "left:" + (50 - w) + "%") }), h("div", { style: "position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--muted)" })]),
        h("div", { class: "n " + cls(r.v) }, pct(r.v))]));
    });
    return box;
  }

  function valClass(l) { return l === "Sous-évalué" ? "t-buy" : l === "Surévalué" ? "t-sell" : "t-neu"; }
  function valTag(v) { v = v || { label: "N/D", basis: "" }; return h("span", { class: "tag " + valClass(v.label), title: v.basis }, v.label); }

  /* ── page : Explorer ─────────────────────────────────────── */
  var LISTS = { undervalued: "Sous-évaluées", overvalued: "Surévaluées", semis: "Semi-conducteurs", cyber: "Cybersécurité", retail: "Commerce de détail", brands: "Marques", extra: "Ajoutées" };
  var sortState = { key: "t", dir: 1 };
  function parseQuery() {
    var q = {}, s = location.hash.split("?")[1] || "";
    s.split("&").forEach(function (p) { if (p) { var a = p.split("="); q[a[0]] = decodeURIComponent(a[1] || ""); } });
    return q;
  }
  var COLS = [
    { k: "t", l: "Symbole", get: function (c) { return c.t; }, cell: function (c) { return h("td", { class: "tk" }, coLink(c)); } },
    { k: "n", l: "Société", get: function (c) { return c.n; }, cell: function (c) { return h("td", { class: "nm", title: c.n }, c.n); } },
    { k: "ind", l: "Industrie", get: function (c) { return c.ind; }, cell: function (c) { return h("td", null, h("a", { href: "#/i/" + enc(c.ind) }, c.ind)); } },
    { k: "price", l: "Prix", n: 1, get: function (c) { return c.price; }, cell: function (c) { return h("td", { class: "n" }, px(c.price)); } },
    { k: "chg1d", l: "1 j", n: 1, get: function (c) { return c.chg1d; }, cell: function (c) { return h("td", { class: "n" }, pctEl(c.chg1d)); } },
    { k: "chg1m", l: "1 mois", n: 1, get: function (c) { return c.chg1m; }, cell: function (c) { return h("td", { class: "n" }, pctEl(c.chg1m, 1)); } },
    { k: "ytd", l: "Depuis janv.", n: 1, get: function (c) { return c.ytd; }, cell: function (c) { return h("td", { class: "n" }, pctEl(c.ytd, 1)); } },
    { k: "chg1y", l: "1 an", n: 1, get: function (c) { return c.chg1y; }, cell: function (c) { return h("td", { class: "n" }, pctEl(c.chg1y, 1)); } },
    { k: "spark", l: "60 jours", get: null, cell: function (c) { return h("td", null, spark(c.spark, 84, 24)); } },
    { k: "rsi", l: "RSI", n: 1, get: function (c) { return c.rsi; }, cell: function (c) { return h("td", { class: "n" }, num(c.rsi, 1)); } },
    { k: "trend", l: "Tendance", get: function (c) { return c.trend; }, cell: function (c) { return h("td", null, c.trend); } },
    { k: "signal", l: "Signal technique", get: function (c) { return c.signal; }, cell: function (c) { return h("td", null, tag(c.signal)); } },
    { k: "verdict", l: "Confluence (9)", get: function (c) { return c.conf.buy - c.conf.sell; }, cell: function (c) { return h("td", null, [tag(c.conf.verdict), h("span", { class: "note" }, " " + c.conf.buy + "↑ " + c.conf.sell + "↓")]); } },
    { k: "val", l: "Valorisation", get: function (c) { return c.val ? c.val.label : ""; }, cell: function (c) { return h("td", null, valTag(c.val)); } },
    { k: "upside", l: "Potentiel cible", n: 1, get: function (c) { return c.upside; }, cell: function (c) { return h("td", { class: "n" }, c.upside == null ? "" : pctEl(c.upside, 1)); } }
  ];
  function pageExplorer(fixed) {
    var q = fixed || parseQuery();
    var state = { q: q.q || "", ind: q.ind || "", list: q.list || "", v: q.v || "" };
    var root = h("div");
    var tbody = h("tbody"), thead = h("thead"), count = h("p", { class: "note" });
    var inp = h("input", { type: "search", placeholder: "Filtrer par nom, symbole ou industrie", value: state.q, "aria-label": "Filtrer" });
    var selI = h("select", { "aria-label": "Industrie" }, [h("option", { value: "" }, "Toutes les industries")].concat(SI.data.universe.industries.map(function (i) { return h("option", { value: i, selected: i === state.ind }, i); })));
    var selV = h("select", { "aria-label": "Verdict de confluence" }, [h("option", { value: "" }, "Tous les verdicts")].concat(["FORT ACHAT", "ACHAT", "NEUTRE", "PRUDENCE", "VENTE", "FORT VENTE"].map(function (i) { return h("option", { value: i, selected: i === state.v }, i); })));
    var chipBox = h("div", { class: "chips", role: "group", "aria-label": "Listes" });
    Object.keys(LISTS).forEach(function (key) {
      if (!U.some(function (c) { return c.lists.indexOf(key) >= 0; })) return;
      var b = h("button", { type: "button", class: "chip", "aria-pressed": String(state.list === key) }, LISTS[key]);
      b.addEventListener("click", function () { state.list = state.list === key ? "" : key; Array.prototype.forEach.call(chipBox.children, function (c) { c.setAttribute("aria-pressed", "false"); }); if (state.list) b.setAttribute("aria-pressed", "true"); render(); });
      chipBox.appendChild(b);
    });
    var rows = [];
    function filtered() {
      var t = state.q.trim().toLowerCase();
      return U.filter(function (c) {
        return (!t || (c.t + " " + c.n + " " + c.ind + " " + c.sub).toLowerCase().indexOf(t) >= 0) && (!state.ind || c.ind === state.ind) &&
          (!state.list || c.lists.indexOf(state.list) >= 0) && (!state.v || c.conf.verdict === state.v);
      });
    }
    function render() {
      rows = filtered();
      var col = COLS.filter(function (c) { return c.k === sortState.key; })[0];
      if (col && col.get) rows.sort(function (a, b) {
        var x = col.get(a), y = col.get(b);
        if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
        return (typeof x === "string" ? x.localeCompare(y, "fr") : x - y) * sortState.dir;
      });
      thead.replaceChildren(h("tr", null, COLS.map(function (c) {
        var th = h("th", { class: (c.n ? "n " : "") + (c.get ? "s" : ""), scope: "col", tabindex: c.get ? 0 : null, "aria-sort": sortState.key === c.k ? (sortState.dir > 0 ? "ascending" : "descending") : null, "data-arrow": sortState.dir > 0 ? "▲" : "▼" }, c.l);
        if (c.get) {
          var f = function () { if (sortState.key === c.k) sortState.dir *= -1; else { sortState.key = c.k; sortState.dir = c.n || c.k === "verdict" ? -1 : 1; } render(); };
          th.addEventListener("click", f); th.addEventListener("keydown", function (e) { if (e.key === "Enter") f(); });
        }
        return th;
      })));
      tbody.replaceChildren.apply(tbody, rows.map(function (c) { return h("tr", null, COLS.map(function (x) { return x.cell(c); })); }));
      count.textContent = rows.length + " société" + (rows.length > 1 ? "s" : "") + " sur " + U.length + (rows.length ? "" : " — aucun résultat : élargissez les filtres.");
    }
    inp.addEventListener("input", function () { state.q = inp.value; render(); });
    selI.addEventListener("change", function () { state.ind = selI.value; render(); });
    selV.addEventListener("change", function () { state.v = selV.value; render(); });
    var exp = h("button", { class: "btn", type: "button" }, "Exporter en CSV");
    exp.addEventListener("click", function () {
      var cols = COLS.filter(function (c) { return c.get && c.k !== "verdict"; });
      csv("explorer_" + META.date_iso + ".csv", cols.map(function (c) { return c.l; }).concat(["Verdict de confluence", "Achats", "Ventes"]),
        rows.map(function (c) { return cols.map(function (x) { return x.get(c); }).concat([c.conf.verdict, c.conf.buy, c.conf.sell]); }));
    });
    root.appendChild(page("Explorer les sociétés", "Cherchez par nom, symbole ou industrie. Cliquez sur un en-tête pour trier, sur un symbole pour ouvrir la fiche.", h("div", { class: "toolbar", style: "margin:0" }, [h("a", { class: "btn", href: "#/manage" }, "Gérer les titres suivis"), exp])));
    root.appendChild(h("div", { class: "toolbar" }, [inp, selI, selV]));
    root.appendChild(h("div", { class: "toolbar" }, [chipBox]));
    root.appendChild(count);
    root.appendChild(h("div", { class: "tw" }, h("table", null, [thead, tbody])));
    root.appendChild(h("p", { class: "note", style: "margin-top:10px" }, ["Confluence : 9 signaux (P/E, Fear & Greed, VIX, RSI, MACD, MA200, social, initiés, AAII). 6 achats ou plus = FORT ACHAT; 4 = ACHAT; ventes symétriques; 3 ventes = PRUDENCE. Tendance (Golden Cross, Death Cross) et tous les calculs : ", h("a", { href: "#/sources?s=tendance" }, "Sources et méthodes"), "."]));
    render();
    return root;
  }


  /* ── page : Matrice de confluence ────────────────────────── */
  var SIGCOL = [["P/E", "P/E comparé à la médiane du secteur"], ["F&G", "Fear & Greed (CNN)"], ["VIX", "Indice de volatilité"], ["RSI", "RSI 14 jours"], ["MACD", "MACD (12, 26, 9)"], ["MA200", "Prix comparé à la moyenne mobile 200 jours"], ["SOCIAL", "Mentions Reddit sur 24 h"], ["INIT.", "Achats et ventes des initiés (SEC)"], ["AAII", "Sondage AAII"]];
  var VERDICTS = ["FORT ACHAT", "ACHAT", "NEUTRE", "PRUDENCE", "VENTE", "FORT VENTE"];
  var VALS = ["Sous-évalué", "Valeur juste", "Surévalué", "N/D"];
  function cell(sg) { return h("span", { class: "tag cell " + (sg === "ACHAT" ? "t-buy" : sg === "VENTE" ? "t-sell" : "t-neu") }, sg === "NEUTRE" ? "NEUTRE" : sg); }
  function pageConfluence() {
    var q = parseQuery(), f = { q: q.q || "", ind: q.ind || "", v: q.v || "", val: q.val || "" };
    var sort = { k: "score", dir: -1 };
    var root = h("div"), tbody = h("tbody"), thead = h("thead"), count = h("p", { class: "note" }), sum = h("div", { class: "chips", role: "group", "aria-label": "Verdicts" });
    var exp = h("button", { class: "btn", type: "button" }, "Exporter en CSV");
    root.appendChild(page("Matrice de confluence", "Les 9 signaux du rapport PDF pour chaque société, avec sa valorisation (sous-évalué ou surévalué) et le verdict final.", h("div", { class: "toolbar", style: "margin:0" }, [h("a", { class: "btn", href: "#/sources?s=conf" }, "Comment ça se calcule"), exp])));
    var inp = h("input", { type: "search", placeholder: "Filtrer par nom, symbole ou industrie", value: f.q, "aria-label": "Filtrer" });
    var selI = h("select", { "aria-label": "Industrie" }, [h("option", { value: "" }, "Toutes les industries")].concat(SI.data.universe.industries.map(function (i) { return h("option", { value: i, selected: i === f.ind }, i); })));
    var selV = h("select", { "aria-label": "Valorisation" }, [h("option", { value: "" }, "Toutes les valorisations")].concat(VALS.map(function (i) { return h("option", { value: i, selected: i === f.val }, i); })));
    root.appendChild(h("div", { class: "toolbar" }, [inp, selI, selV]));
    root.appendChild(sum); root.appendChild(count);
    root.appendChild(h("div", { class: "tw", style: "max-height:72vh" }, h("table", { class: "matrix" }, [thead, tbody])));
    root.appendChild(h("div", { class: "card sec" }, [h("h2", null, "Comment lire la matrice"), h("ul", { class: "list" }, [
      h("li", null, "Chaque case dit si le signal est favorable (ACHAT), défavorable (VENTE) ou sans avis (NEUTRE). 6 achats ou plus = FORT ACHAT; 4 ou 5 = ACHAT; 3 ventes = PRUDENCE; 4 ou 5 ventes = VENTE; 6 ou plus = FORT VENTE."),
      h("li", null, "Valorisation : « Sous-évalué » et « Surévalué » viennent d'abord des listes éditoriales du rapport. Pour les autres sociétés, on compare le P/E prévisionnel à la médiane du secteur : moins de 0,85 = sous-évalué, plus de 1,5 = surévalué. Sans P/E saisi : N/D. Survolez l'étiquette pour voir la base du calcul."),
      h("li", null, "Les cases Fear & Greed, VIX et AAII décrivent le marché : elles sont identiques pour toutes les sociétés."),
      h("li", null, "Un titre sous-évalué avec un verdict ACHAT combine un prix attrayant et une bonne configuration technique; un titre surévalué avec un verdict VENTE ou PRUDENCE cumule prix élevé et signaux défavorables. Ce n'est pas un conseil en placement.")])]));

    var rank = { ACHAT: 1, NEUTRE: 0, VENTE: -1 };
    var keyf = {
      t: function (c) { return c.t; }, ind: function (c) { return c.ind; }, val: function (c) { return c.val ? c.val.label : ""; },
      score: function (c) { return c.conf.buy - c.conf.sell; }, verdict: function (c) { return c.conf.buy - c.conf.sell; }
    };
    function value(c, k) { if (keyf[k]) return keyf[k](c); var i = SIGCOL.map(function (x) { return x[0]; }).indexOf(k); return i >= 0 ? rank[c.conf.sigs[i]] : 0; }
    function rows() {
      var t = f.q.trim().toLowerCase();
      return U.filter(function (c) {
        return (!t || (c.t + " " + c.n + " " + c.ind).toLowerCase().indexOf(t) >= 0) && (!f.ind || c.ind === f.ind) && (!f.v || c.conf.verdict === f.v) && (!f.val || (c.val && c.val.label === f.val));
      }).sort(function (a, b) {
        var x = value(a, sort.k), y = value(b, sort.k);
        var r = typeof x === "string" ? x.localeCompare(y, "fr") : x - y;
        return (r || (b.conf.buy - b.conf.sell) - (a.conf.buy - a.conf.sell) || a.t.localeCompare(b.t)) * (r ? sort.dir : 1);
      });
    }
    var cur = [];
    function render() {
      cur = rows();
      var heads = [["t", "Symbole"], ["n", "Société"], ["ind", "Industrie"], ["val", "Valorisation"]].concat(SIGCOL.map(function (x) { return [x[0], x[0], x[1]]; })).concat([["score", "Score"], ["verdict", "Verdict"]]);
      thead.replaceChildren(h("tr", null, heads.map(function (x) {
        var sortable = x[0] !== "n";
        var th = h("th", { class: sortable ? "s" : "", scope: "col", title: x[2] || null, tabindex: sortable ? 0 : null, "aria-sort": sort.k === x[0] ? (sort.dir > 0 ? "ascending" : "descending") : null, "data-arrow": sort.dir > 0 ? "▲" : "▼" }, x[1]);
        if (sortable) { var go = function () { if (sort.k === x[0]) sort.dir *= -1; else { sort.k = x[0]; sort.dir = (x[0] === "t" || x[0] === "ind" || x[0] === "val") ? 1 : -1; } render(); }; th.addEventListener("click", go); th.addEventListener("keydown", function (e) { if (e.key === "Enter") go(); }); }
        return th;
      })));
      tbody.replaceChildren.apply(tbody, cur.map(function (c) {
        return h("tr", null, [h("td", { class: "tk" }, coLink(c)), h("td", { class: "nm", title: c.n }, c.n), h("td", null, h("a", { href: "#/i/" + enc(c.ind) }, c.ind)), h("td", null, valTag(c.val))]
          .concat(c.conf.sigs.map(function (sg) { return h("td", { class: "mc" }, cell(sg)); }))
          .concat([h("td", { class: "n" }, c.conf.buy + "↑ " + c.conf.sell + "↓"), h("td", null, tag(c.conf.verdict))]));
      }));
      count.textContent = cur.length + " société" + (cur.length > 1 ? "s" : "") + " sur " + U.length + (cur.length ? "" : " — aucun résultat : élargissez les filtres.");
      sum.replaceChildren.apply(sum, VERDICTS.map(function (v) {
        var n = U.filter(function (c) { return c.conf.verdict === v; }).length;
        var b = h("button", { type: "button", class: "chip", "aria-pressed": String(f.v === v) }, v + " · " + n);
        b.addEventListener("click", function () { f.v = f.v === v ? "" : v; render(); }); return b;
      }));
    }
    inp.addEventListener("input", function () { f.q = inp.value; render(); });
    selI.addEventListener("change", function () { f.ind = selI.value; render(); });
    selV.addEventListener("change", function () { f.val = selV.value; render(); });
    exp.addEventListener("click", function () {
      csv("confluence_" + META.date_iso + ".csv", ["Symbole", "Société", "Industrie", "Valorisation", "Base de la valorisation"].concat(SIGCOL.map(function (x) { return x[0]; }), ["Achats", "Ventes", "Verdict"]),
        cur.map(function (c) { return [c.t, c.n, c.ind, c.val ? c.val.label : "", c.val ? c.val.basis : ""].concat(c.conf.sigs, [c.conf.buy, c.conf.sell, c.conf.verdict]); }));
    });
    render();
    return root;
  }

  /* ── page : Industries ───────────────────────────────────── */
  function pageIndustries() {
    var st = industryStats().sort(function (a, c) { return (c.ytd || 0) - (a.ytd || 0); });
    var root = h("div");
    root.appendChild(page("Industries", "Rendements moyens (équipondérés) des sociétés suivies dans chaque industrie.", h("a", { class: "btn", href: "#/manage" }, "Gérer les titres par industrie")));
    root.appendChild(h("div", { class: "card" }, [h("h2", null, "Rendement moyen depuis janvier"), hbars(st.map(function (s) { return { label: s.name, v: s.ytd, href: "#/i/" + enc(s.name) }; }))]));
    var g = h("div", { class: "grid g3 sec" });
    st.forEach(function (s) {
      g.appendChild(h("a", { class: "card ind-card", href: "#/i/" + enc(s.name) }, [h("h3", null, s.name), h("div", { class: "meta-line" }, [h("span", null, s.n + " sociétés"), h("span", null, ["1 mois ", pctEl(s.m1, 1)]), h("span", null, ["1 an ", pctEl(s.y1, 1)]), h("span", null, "RSI moyen " + num(s.rsi, 1))]),
        h("p", { class: "note", style: "margin:8px 0 0" }, s.above + " sur " + s.n + " au-dessus de la MA200 · " + s.buy + " en achat · " + s.sell + " en vente")]));
    });
    root.appendChild(g);
    return root;
  }
  function pageIndustry(name) {
    var st = industryStats().filter(function (s) { return s.name === name; })[0];
    if (!st) return notFound("Industrie introuvable : " + name);
    var root = h("div");
    root.appendChild(h("div", { class: "crumb" }, [h("a", { href: "#/industries" }, "Industries"), " / " + name]));
    root.appendChild(page(name, st.n + " sociétés suivies. Cliquez sur une société pour voir son historique complet."));
    var k = h("div", { class: "grid g5" });
    k.appendChild(kpi("1 jour", pct(st.d1), "moyenne équipondérée", cls(st.d1)));
    k.appendChild(kpi("1 mois", pct(st.m1, 1), "moyenne équipondérée", cls(st.m1)));
    k.appendChild(kpi("Depuis janvier", pct(st.ytd, 1), "moyenne équipondérée", cls(st.ytd)));
    k.appendChild(kpi("RSI moyen", num(st.rsi, 1), st.above + " sur " + st.n + " au-dessus de la MA200"));
    root.appendChild(k);
    var holder = h("div", { class: "card sec" }, [h("p", { class: "loading" }, "Chargement des historiques…")]);
    root.appendChild(holder);
    Promise.all(st.list.map(function (c) { return loadTicker(c.t); })).then(function (all) {
      // indice équipondéré par rendements quotidiens moyens
      var maps = all.map(function (a) { var m = {}; a.dates.forEach(function (d, i) { m[d] = a.close[i]; }); return m; });
      var dates = all.reduce(function (p, a) { return a.dates.length > p.length ? a.dates : p; }, []);
      var idx = [100], prev = null;
      dates.forEach(function (d, i) {
        if (i === 0) return;
        var r = [];
        maps.forEach(function (m) { var a = m[dates[i - 1]], b = m[d]; if (a != null && b != null && a) r.push(b / a - 1); });
        idx.push(idx[idx.length - 1] * (1 + (r.length ? r.reduce(function (p, c) { return p + c; }, 0) / r.length : 0)));
      });
      var series = [{ name: "Indice équipondéré", d: dates, v: idx.map(function (v) { return +v.toFixed(3); }), w: 3 }];
      if (M.idx.SP500) series.push({ name: "S&P 500", d: M.idx.SP500.d, v: M.idx.SP500.v, color: "c3" });
      var members = st.list.length <= 6;
      if (members) st.list.forEach(function (c, i) { var a = all[i]; series.push({ name: c.t, d: a.dates, v: a.close, color: "c" + (i + 4), w: 1.5 }); });
      var ch = chart({ series: series, rebase: true, height: 300, fmt: function (z) { return num(z, 0); }, tipFmt: function (z) { return num(z, 1); }, label: "Indice de l'industrie" });
      holder.replaceChildren(h("div", { class: "ch" }, [h("h2", null, "Historique de l'industrie (base 100)"), rangeBar([ch], "1A")]), ch.el,
        h("p", { class: "note" }, "Indice équipondéré : chaque jour, rendement moyen des sociétés listées ci-dessous." + (members ? "" : " Les sociétés individuelles sont masquées au-delà de 6 pour garder le graphique lisible; comparez-les dans « Comparer ».")));
    }).catch(function (e) { holder.replaceChildren(h("p", null, "Impossible de charger l'historique : " + e.message)); });
    root.appendChild(h("div", { class: "sec" }, [h("h2", { style: "margin-bottom:10px" }, "Sociétés de l'industrie"), pageExplorerTable(st.list)]));
    root.appendChild(h("p", null, h("a", { class: "btn", href: "#/compare?t=" + st.list.slice(0, 6).map(function (c) { return c.t; }).join(",") }, "Comparer ces sociétés")));
    return root;
  }
  function pageExplorerTable(list) {
    var cols = [COLS[0], COLS[1], COLS[3], COLS[4], COLS[5], COLS[6], COLS[7], COLS[8], COLS[9], COLS[12]];
    return h("div", { class: "tw" }, h("table", null, [h("thead", null, h("tr", null, cols.map(function (c) { return h("th", { class: c.n ? "n" : "" }, c.l); }))),
      h("tbody", null, list.map(function (c) { return h("tr", null, cols.map(function (x) { return x.cell(c); })); }))]));
  }

  /* ── page : Société ──────────────────────────────────────── */
  function pageCompany(t) {
    var c = BYT[t];
    if (!c) return notFound("Société introuvable : " + t);
    var root = h("div");
    root.appendChild(h("div", { class: "crumb" }, [h("a", { href: "#/explorer" }, "Explorer"), " / ", h("a", { href: "#/i/" + enc(c.ind) }, c.ind), " / " + c.t]));
    root.appendChild(h("div", { class: "hero" }, [h("div", null, [h("h1", null, c.n + " (" + c.t + ")"), h("div", { class: "meta-line" }, [h("span", null, c.ind), c.sub ? h("span", null, c.sub) : null, h("span", null, c.lists.map(function (l) { return LISTS[l]; }).join(", "))])]),
      h("div", { class: "px" }, px(c.price)), h("div", { class: cls(c.chg1d) }, pct(c.chg1d) + " aujourd'hui"), tag(c.conf.verdict)]));
    var k = h("div", { class: "grid g5", style: "margin-top:12px" });
    k.appendChild(kpi("1 mois / 3 mois", pct(c.chg1m, 1) + " / " + pct(c.chg3m, 1), "6 mois : " + pct(c.chg6m, 1), cls(c.chg1m)));
    k.appendChild(kpi("Depuis janvier / 1 an", pct(c.ytd, 1) + " / " + pct(c.chg1y, 1), "", cls(c.ytd)));
    k.appendChild(kpi("52 semaines", px(c.lo52) + " – " + px(c.hi52), pct(c.from_hi, 1) + " sous le sommet"));
    k.appendChild(kpi("RSI (14) · " + c.trend, num(c.rsi, 1), c.rsi >= 70 ? "Surachat" : c.rsi <= 30 ? "Survente" : "Zone neutre"));
    k.lastChild.appendChild(h("a", { class: "note", href: "#/sources?s=tendance" }, "Que veut dire « " + c.trend + " » ?"));
    k.appendChild(kpi("Signal technique", c.signal, "MACD hist. " + num(c.macd_hist, 2)));
    if (c.ed && c.ed.target) k.appendChild(kpi("Cible des analystes", px(c.ed.target), pct(c.upside, 1) + " de potentiel", cls(c.upside)));
    root.appendChild(k);

    var body = h("div", { class: "sec" }, [h("p", { class: "loading" }, "Chargement de l'historique…")]);
    root.appendChild(body);
    loadTicker(t).then(function (a) {
      groups["co"] = [];
      var chP = chart({ series: [{ name: "Cours", d: a.dates, v: a.close, w: 2 }, { name: "MA50", d: a.dates, v: a.ma50, color: "c3", w: 1.5 }, { name: "MA200", d: a.dates, v: a.ma200, color: "c4", w: 1.5 }], group: "co", height: 300, label: "Cours et moyennes mobiles" });
      var chR = chart({ series: [{ name: "RSI (14)", d: a.dates, v: a.rsi }], group: "co", height: 150, yFixed: [0, 100], ref: [{ y: 70, label: "Surachat 70" }, { y: 30, label: "Survente 30" }], fmt: function (z) { return num(z, 0); }, tipFmt: function (z) { return num(z, 1); }, label: "RSI" });
      var chM = chart({ series: [{ name: "Histogramme", d: a.dates, v: a.macd_hist, type: "bar" }, { name: "MACD", d: a.dates, v: a.macd, color: "c1" }, { name: "Signal", d: a.dates, v: a.macd_sig, color: "c3" }], group: "co", height: 170, label: "MACD" });
      var bar = rangeBar([chP, chR, chM], "1A");
      var tech = h("div", { class: "card" }, [h("div", { class: "ch" }, [h("h2", null, "Cours et analyse technique"), h("div", { style: "display:flex;gap:8px;flex-wrap:wrap" }, [bar, h("button", { class: "btn", type: "button", onclick: function () {
        csv(t + "_historique.csv", ["Date", "Clôture", "MA50", "MA200", "RSI", "MACD", "Signal MACD", "Histogramme"], a.dates.map(function (d, i) { return [d, a.close[i], a.ma50[i], a.ma200[i], a.rsi[i], a.macd[i], a.macd_sig[i], a.macd_hist[i]]; }));
      } }, "Exporter l'historique (CSV)")])]),
        chP.el, h("h3", { style: "margin:14px 0 0" }, "RSI (14 jours)"), chR.el, h("h3", { style: "margin:14px 0 0" }, "MACD (12, 26, 9)"), chM.el,
        h("p", { class: "note" }, "Les trois graphiques partagent la même période et le même curseur.")]);
      body.replaceChildren(tech);

      // confluence
      var cf = h("div", { class: "conf" });
      c.conf.sigs.forEach(function (s, i) { cf.appendChild(h("div", null, [h("small", null, CONF[i]), tag(s)])); });
      body.appendChild(h("div", { class: "card sec" }, [h("div", { class: "ch" }, [h("h2", null, "Matrice de confluence du jour"), tag(c.conf.verdict)]), cf]));

      // fondamentaux + social
      var g = h("div", { class: "grid g2 sec" });
      var dl = h("dl", { class: "dl" });
      function row(a1, b1) { if (b1 != null && b1 !== "") { dl.appendChild(h("dt", null, a1)); dl.appendChild(h("dd", null, b1)); } }
      var ed = c.ed || {};
      row("P/E prévisionnel", ed.pe_fwd != null ? "~" + num(ed.pe_fwd, 1) : null); row("P/E médian du secteur", ed.sector_pe != null ? num(ed.sector_pe, 0) : null);
      row("Conviction", ed.conviction ? "★".repeat(ed.conviction) : null); row("Risque principal", ed.risk); row("Initiés (saisie)", ed.insider);
      row("Mentions Reddit 24 h", c.soc.men != null ? String(c.soc.men) : null); row("Rang ApeWisdom", c.soc.ape_rank != null ? "#" + c.soc.ape_rank : null);
      row("Rang StockTwits", c.soc.st_rank != null ? "#" + c.soc.st_rank : null); row("Pages Wikipédia (7 j)", c.soc.wiki_chg != null ? pct(c.soc.wiki_chg, 1) : null);
      row("YouTube (7 j)", c.soc.yt_views != null ? nf0.format(c.soc.yt_views) + " vues — " + (c.soc.yt_title || "") : null);
      row("Initiés SEC (45 j)", c.soc.buys != null ? "achats " + nf0.format(c.soc.buys) + " $ · ventes " + nf0.format(c.soc.sells || 0) + " $" : null);
      row("Note", c.note);
      g.appendChild(h("div", { class: "card" }, [h("h2", null, "Fondamentaux et signaux sociaux"), dl.children.length ? dl : h("p", { class: "note" }, "Aucune donnée éditoriale ni sociale pour cette société aujourd'hui."),
        h("p", { class: "note", style: "margin-top:8px" }, "P/E, cibles et convictions sont saisis à la main dans content.json (date : " + META.editorial_as_of + ").")]));

      var soc = a.soc || { d: [] }, ws = a.wiki;
      var scard = h("div", { class: "card" }, [h("h2", null, "Intérêt social au fil du temps")]);
      if (ws && ws.d && ws.d.length) {
        var chW = chart({ series: [{ name: "Pages vues Wikipédia / jour", d: ws.d, v: ws.v }], months: null, height: 170, fmt: function (z) { return num(z, 0); }, label: "Pages vues Wikipédia" });
        scard.appendChild(h("h3", { style: "margin:4px 0" }, "Pages vues Wikipédia (365 jours)")); scard.appendChild(chW.el);
      }
      if (soc.d.length >= 2 && soc.men.some(function (v) { return v != null; })) {
        var chS = chart({ series: [{ name: "Mentions Reddit / 24 h", d: soc.d, v: soc.men }], months: null, height: 150, fmt: function (z) { return num(z, 0); }, label: "Mentions Reddit" });
        scard.appendChild(h("h3", { style: "margin:12px 0 4px" }, "Mentions Reddit (ApeWisdom), cumulées chaque jour")); scard.appendChild(chS.el);
      } else {
        scard.appendChild(h("p", { class: "note", style: "margin-top:10px" }, "Les mentions Reddit, les rangs StockTwits et les achats/ventes d'initiés s'accumulent à chaque exécution quotidienne : le graphique apparaît après deux jours de collecte" + (soc.d.length ? " (" + soc.d.length + " jour recueilli)." : ".")));
      }
      g.appendChild(scard);
      body.appendChild(g);

      // instantanés
      var sn = (a.snaps || []).slice().reverse();
      var head = ["Date", "Cours", "Signal technique", "Verdict de confluence", "Achats", "Ventes", "RSI", "Tendance", "Social", "Initiés"];
      var rows = sn.map(function (s) { return [s.d, s.p, s.sig, s.v, s.b, s.s, s.rsi, s.tr, s.so, s["in"]]; });
      var exp = h("button", { class: "btn", type: "button", onclick: function () { csv(t + "_signaux.csv", head, rows); } }, "Exporter en CSV");
      body.appendChild(h("div", { class: "card sec" }, [h("div", { class: "ch" }, [h("h2", null, "Historique des signaux (instantanés quotidiens)"), exp]),
        h("p", { class: "note" }, "Un instantané est enregistré chaque jour d'exécution; l'historique commence à la première exécution (" + (sn.length ? sn[sn.length - 1].d : "—") + ")."),
        h("div", { class: "tw", style: "max-height:340px" }, h("table", null, [h("thead", null, h("tr", null, head.map(function (x, i) { return h("th", { class: i === 1 || i === 4 || i === 5 || i === 6 ? "n" : "" }, x); }))),
          h("tbody", null, rows.slice(0, 250).map(function (r) {
            return h("tr", null, [h("td", null, r[0]), h("td", { class: "n" }, px(r[1])), h("td", null, tag(r[2])), h("td", null, tag(r[3])), h("td", { class: "n" }, String(r[4])), h("td", { class: "n" }, String(r[5])), h("td", { class: "n" }, num(r[6], 1)), h("td", null, r[7]), h("td", null, tag(r[8])), h("td", null, tag(r[9]))]);
          }))]))]));
      body.appendChild(h("p", { style: "margin-top:14px" }, h("a", { class: "btn", href: "#/compare?t=" + t }, "Comparer avec d'autres sociétés")));
    }).catch(function (e) { body.replaceChildren(h("p", { class: "note" }, "Historique indisponible : " + e.message)); });
    return root;
  }

  /* ── page : Comparer ─────────────────────────────────────── */
  function pageCompare() {
    var q = parseQuery(), picked = (q.t || "").split(",").filter(function (x) { return BYT[x]; }).slice(0, 6);
    var root = h("div");
    root.appendChild(page("Comparer", "Jusqu'à 6 sociétés, rebasées à 100 au début de la période choisie."));
    var inp = h("input", { type: "search", list: "dl-co", placeholder: "Ajouter un symbole (ex. NVDA)", "aria-label": "Ajouter une société" });
    var dl = h("datalist", { id: "dl-co" }, U.map(function (c) { return h("option", { value: c.t }, c.n); }));
    var chipsBox = h("div", { class: "picked" }), out = h("div");
    function sync() { history.replaceState(null, "", "#/compare?t=" + picked.join(",")); }
    function add(v) { v = (v || "").toUpperCase().trim(); if (BYT[v] && picked.indexOf(v) < 0 && picked.length < 6) { picked.push(v); inp.value = ""; sync(); show(); } }
    inp.addEventListener("change", function () { add(inp.value); });
    inp.addEventListener("keydown", function (e) { if (e.key === "Enter") add(inp.value); });
    root.appendChild(h("div", { class: "toolbar" }, [inp, dl, h("button", { class: "btn", type: "button", onclick: function () { picked = []; sync(); show(); } }, "Vider")]));
    root.appendChild(chipsBox); root.appendChild(out);
    var seq = 0;
    function show() {
      chipsBox.replaceChildren.apply(chipsBox, picked.map(function (t) { return h("button", { type: "button", "aria-label": "Retirer " + t, onclick: function () { picked.splice(picked.indexOf(t), 1); sync(); show(); } }, t); }));
      if (picked.length < 1) { out.replaceChildren(h("p", { class: "note" }, "Choisissez au moins une société : tapez un symbole ci-dessus, ou partez d'une industrie.")); return; }
      var my = ++seq;
      out.replaceChildren(h("p", { class: "loading" }, "Chargement…"));
      Promise.all(picked.map(loadTicker)).then(function (all) {
        if (my !== seq) return;
        var ch = chart({ series: all.map(function (a, i) { return { name: a.t, d: a.dates, v: a.close, color: "c" + (i + 1) }; }), rebase: true, height: 320, fmt: function (z) { return num(z, 0); }, tipFmt: function (z) { return num(z, 1); }, label: "Comparaison rebasée" });
        var tb = h("div", { class: "tw", style: "margin-top:14px" }, h("table", null, [h("thead", null, h("tr", null, ["Symbole", "Société", "Industrie", "1 mois", "Depuis janv.", "1 an", "RSI", "Confluence"].map(function (x, i) { return h("th", { class: i > 2 && i < 7 ? "n" : "" }, x); }))),
          h("tbody", null, picked.map(function (t) {
            var c = BYT[t]; return h("tr", null, [h("td", { class: "tk" }, coLink(c)), h("td", null, c.n), h("td", null, c.ind), h("td", { class: "n" }, pctEl(c.chg1m, 1)), h("td", { class: "n" }, pctEl(c.ytd, 1)), h("td", { class: "n" }, pctEl(c.chg1y, 1)), h("td", { class: "n" }, num(c.rsi, 1)), h("td", null, tag(c.conf.verdict))]);
          }))]));
        out.replaceChildren(h("div", { class: "card" }, [h("div", { class: "ch" }, [h("h2", null, "Performance relative"), rangeBar([ch], "1A")]), ch.el]), tb);
      });
    }
    show();
    return root;
  }

  /* ── page : Historique du marché ─────────────────────────── */
  function pageHistory() {
    var root = h("div");
    root.appendChild(page("Historique du marché", "Indices sur 5 ans, sentiment (Fear & Greed, AAII) et instantanés quotidiens cumulés par la plateforme."));
    var sel = h("div", { class: "seg", role: "group", "aria-label": "Indice" }), cur = "SP500", holder = h("div");
    var okeys = ["SP500", "NASDAQ", "TSX", "VIX", "BTC"].filter(function (x) { return M.idx[x]; });
    function showIdx() {
      var s = M.idx[cur];
      var ch = chart({ series: [{ name: s.n, d: s.d, v: s.v }], height: 280, label: s.n });
      holder.replaceChildren(h("div", { class: "ch" }, [h("h2", null, s.n), rangeBar([ch], "3A")]), ch.el);
    }
    okeys.forEach(function (k) { sel.appendChild(h("button", { type: "button", "aria-pressed": String(k === cur), onclick: function (e) { cur = k; Array.prototype.forEach.call(sel.children, function (b) { b.setAttribute("aria-pressed", String(b === e.currentTarget)); }); showIdx(); } }, M.idx[k].n)); });
    root.appendChild(h("div", { class: "card" }, [h("div", { style: "margin-bottom:10px" }, sel), holder]));
    showIdx();

    var fgC = chart({ series: [{ name: "Actions (CNN)", d: M.fg_s.d, v: M.fg_s.v }, { name: "Crypto", d: M.fg_c.d, v: M.fg_c.v, color: "c3" }], yFixed: [0, 100], ref: [{ y: 75, label: "Cupidité" }, { y: 25, label: "Peur" }], height: 230, fmt: function (z) { return num(z, 0); }, label: "Fear & Greed" });
    root.appendChild(h("div", { class: "card sec" }, [h("div", { class: "ch" }, [h("h2", null, "Indice Fear & Greed"), rangeBar([fgC], "1A")]), fgC.el,
      h("p", { class: "note" }, "0 = peur extrême, 100 = cupidité extrême. Historique complet fourni par les sources; il se prolonge chaque jour.")]));

    var A = M.aaii;
    var aC = chart({ series: [{ name: "Haussiers", d: A.map(function (x) { return x.d; }), v: A.map(function (x) { return x.bull; }), color: "c2" }, { name: "Neutres", d: A.map(function (x) { return x.d; }), v: A.map(function (x) { return x.neutral; }), color: "c7" }, { name: "Baissiers", d: A.map(function (x) { return x.d; }), v: A.map(function (x) { return x.bear; }), color: "c5" }], months: null, height: 220, fmt: function (z) { return num(z, 0) + " %"; }, tipFmt: function (z) { return num(z, 1) + " %"; }, label: "Sondage AAII" });
    root.appendChild(h("div", { class: "card sec" }, [h("h2", null, "Sondage AAII (investisseurs particuliers)"), aC.el,
      A.length < 3 ? h("p", { class: "note" }, "Une lecture hebdomadaire est ajoutée chaque fois que content.json reçoit une nouvelle date AAII; la courbe se précise avec le temps.") : null]));
    if (M.aaii_signals.length) root.appendChild(h("div", { class: "card sec" }, [h("h2", null, "Repères historiques de l'écart AAII"), h("div", { class: "tw" }, h("table", null, [h("thead", null, h("tr", null, ["Période", "Écart", "Signal", "S&P 500 à 12 mois", "Leçon"].map(function (x) { return h("th", null, x); }))),
      h("tbody", null, M.aaii_signals.map(function (s) { return h("tr", null, [h("td", null, s.period), h("td", { class: "n" }, num(s.spread, 1)), h("td", null, s.signal), h("td", null, s.sp12), h("td", { style: "white-space:normal" }, s.lesson)]); }))]))]));

    var D = M.daily.slice().reverse(), keys = [];
    D.forEach(function (r) { Object.keys(r.n_sig || {}).forEach(function (k) { if (keys.indexOf(k) < 0) keys.push(k); }); });
    var head = ["Date", "F&G actions", "F&G crypto", "VIX", "% > MA200", "RSI moyen"].concat(keys);
    var rows = D.map(function (r) { return [r.d, r.fg_s, r.fg_c, r.vix, r.pct200, r.rsi_avg].concat(keys.map(function (k) { return (r.n_sig || {})[k] || 0; })); });
    root.appendChild(h("div", { class: "card sec" }, [h("div", { class: "ch" }, [h("h2", null, "Instantanés quotidiens de la plateforme"), h("button", { class: "btn", type: "button", onclick: function () { csv("instantanes_quotidiens.csv", head, rows); } }, "Exporter en CSV")]),
      h("p", { class: "note" }, "Un instantané par jour d'exécution : sentiment, VIX, part des titres au-dessus de la MA200, RSI moyen et nombre de sociétés par signal technique. Cet historique commence le " + META.history_from + "."),
      h("div", { class: "tw", style: "max-height:340px" }, h("table", null, [h("thead", null, h("tr", null, head.map(function (x, i) { return h("th", { class: i ? "n" : "" }, x); }))),
        h("tbody", null, rows.slice(0, 300).map(function (r) { return h("tr", null, r.map(function (v, i) { return h("td", { class: i ? "n" : "" }, i === 0 ? v : v == null ? "N/D" : num(v, i >= 6 ? 0 : 1)); })); }))]))]));

    var pa = (META.pdf && META.pdf.archive) || [];
    if (pa.length) root.appendChild(h("div", { class: "card sec" }, [h("h2", null, "Archives des rapports PDF"), h("p", { class: "note" }, "Les " + pa.length + " derniers rapports, du plus récent au plus ancien."),
      h("div", { class: "chips" }, pa.map(function (r) { return h("a", { class: "chip", href: r.f, target: "_blank", rel: "noopener", style: "text-decoration:none" }, r.d); }))]));
    var arch = M.archive.slice().reverse();
    root.appendChild(h("div", { class: "card sec" }, [h("h2", null, "Archive des faits saillants"),
      arch.length ? h("div", null, arch.map(function (a) { return h("details", { open: a === arch[0] }, [h("summary", null, "Éditorial du " + a.as_of), h("ul", { class: "list" }, a.items.map(function (t) { return h("li", null, t); }))]); })) : h("p", { class: "note" }, "Aucune archive pour l'instant.")]));
    return root;
  }

  /* ── page : Sources ──────────────────────────────────────── */
  function pageSources() {
    var root = h("div");
    root.appendChild(page("Sources et méthodes", "D'où viennent les données, comment chaque indicateur et chaque recommandation est calculé, et ce qui a répondu à la dernière exécution."));
    root.appendChild(h("div", { class: "card" }, [h("h2", null, "Dernière exécution (" + META.generated.replace("T", " ") + ")"), h("div", { class: "chips" }, META.status.map(function (s) { return h("span", { class: "tag " + (s.ok ? "t-buy" : "t-warn") }, s.n + " : " + (s.ok ? "OK" : "N/D")); })),
      h("p", { class: "note", style: "margin-top:10px" }, "N/D signifie que la source n'a pas répondu ce jour-là : aucune valeur n'est inventée. Le contenu éditorial (cibles, P/E, convictions) date du " + META.editorial_as_of + ".")]));
    root.appendChild(methodsSection());
    var c = SRC.catalogue || [];
    root.appendChild(h("div", { class: "sec" }, [h("h2", { style: "margin-bottom:10px" }, "Catalogue des canaux de social investing"), h("div", { class: "tw" }, h("table", null, [h("thead", null, h("tr", null, ["Canal", "Mesure", "Accès et coût", "Limites", "Statut"].map(function (x) { return h("th", null, x); }))),
      h("tbody", null, c.map(function (r) { return h("tr", null, [h("td", { class: "tk" }, r.canal), h("td", { style: "white-space:normal;min-width:220px" }, r.mesure), h("td", { style: "white-space:normal;min-width:180px" }, r.acces), h("td", { style: "white-space:normal;min-width:180px" }, r.limites), h("td", null, r.statut)]); }))]))]));
    var mw = SRC.manual_watch || {};
    if (mw.how) root.appendChild(h("div", { class: "card sec" }, [h("h2", null, "Veille manuelle (TikTok)"), h("p", null, mw.how), h("p", { class: "note" }, (mw.hashtags || []).join("  ")),
      (mw.items || []).length ? h("ul", { class: "list" }, mw.items.map(function (i) { return h("li", null, [i.date, " — ", i.canal, " : ", i.sujet, " (", i.observation, ")"]); })) : h("p", { class: "note" }, "Aucune observation saisie.")]));
    var br = SI.data.universe.brands || [];
    if (br.length) root.appendChild(h("div", { class: "card sec" }, [h("h2", null, "Marques à surveiller"), h("div", { class: "tw" }, h("table", null, [h("thead", null, h("tr", null, ["Marque", "Statut", "Thème", "Titre associé"].map(function (x) { return h("th", null, x); }))),
      h("tbody", null, br.map(function (b) { return h("tr", null, [h("td", { class: "tk" }, b.brand), h("td", null, b.status), h("td", null, b.theme), h("td", null, b.proxy && BYT[b.proxy] ? coLink(BYT[b.proxy]) : "—")]); }))]))]));
    return root;
  }

  /* ── page : Gérer les titres ─────────────────────────────── */
  var DRAFT_KEY = "si-watch-draft";
  function pageManage() {
    var W = (SI.data.universe.watch) || { add: [], remove: [], move: {}, missing: [] };
    var d = null;
    try { d = JSON.parse(lsGet(DRAFT_KEY) || "null"); } catch (e) { d = null; }
    if (!d) d = { add: (W.add || []).slice(), remove: (W.remove || []).slice(), move: Object.assign({}, W.move || {}) };
    var save = function () { lsSet(DRAFT_KEY, JSON.stringify(d)); render(); };
    var root = h("div"), out = h("div");
    root.appendChild(page("Gérer les titres suivis", "Ajoutez, retirez ou changez d'industrie les sociétés de la plateforme. Le site est statique : vos choix s'enregistrent dans le fichier watchlist.json du dépôt, puis s'appliquent à la prochaine exécution du robot."));
    root.appendChild(h("div", { class: "card" }, [h("h2", null, "Comment ça marche"), h("ol", { class: "list" }, [
      h("li", null, "Faites vos changements ci-dessous (ils sont gardés dans ce navigateur tant que vous ne les validez pas)."),
      h("li", null, "Cliquez sur « Copier le contenu », puis sur « Ouvrir watchlist.json dans GitHub », collez, et enregistrez (Commit changes)."),
      h("li", null, "Pour voir le résultat tout de suite : onglet Actions → « Rapport Social Investing quotidien » → Run workflow. Sinon, la prochaine exécution quotidienne le fera."),
      h("li", null, "Une société ajoutée reçoit son historique complet (5 ans) dès cette exécution. Une société retirée disparaît de la plateforme, mais son historique déjà enregistré reste dans le dépôt.")])]));
    if ((W.missing || []).length) root.appendChild(h("div", { class: "banner warn", style: "margin:14px 0" }, "Sans données au dernier passage : " + W.missing.join(", ") + ". Vérifiez le symbole (actions canadiennes : suffixe .TO, par exemple SHOP.TO; crypto : BTC-USD)."));

    var inds = SI.data.universe.industries.slice();
    var fT = h("input", { type: "text", placeholder: "Symbole (ex. META, SHOP.TO)", "aria-label": "Symbole", maxlength: 15, style: "width:200px" });
    var fN = h("input", { type: "text", placeholder: "Nom de la société", "aria-label": "Nom", style: "width:220px" });
    var fI = h("select", { "aria-label": "Industrie" }, inds.map(function (i) { return h("option", { value: i }, i); }).concat([h("option", { value: "__new" }, "Nouvelle industrie…")]));
    var fNew = h("input", { type: "text", placeholder: "Nom de l'industrie", "aria-label": "Nouvelle industrie", hidden: true, style: "width:200px" });
    var fW = h("input", { type: "text", placeholder: "Page Wikipédia (facultatif)", "aria-label": "Page Wikipédia", style: "width:200px" });
    var err = h("p", { class: "note", role: "alert" });
    fI.addEventListener("change", function () { fNew.hidden = fI.value !== "__new"; });
    var addBtn = h("button", { class: "btn pri", type: "button" }, "Ajouter à la liste");
    addBtn.addEventListener("click", function () {
      var t = fT.value.trim().toUpperCase(), ind = fI.value === "__new" ? fNew.value.trim() : fI.value;
      if (!/^[A-Z0-9][A-Z0-9.\-^=]{0,14}$/.test(t)) { err.textContent = "Symbole invalide : lettres, chiffres, point ou tiret seulement."; return; }
      if (!ind) { err.textContent = "Choisissez ou nommez une industrie."; return; }
      if (BYT[t] && d.remove.indexOf(t) < 0) { err.textContent = t + " est déjà suivi : changez son industrie dans le tableau."; return; }
      d.remove = d.remove.filter(function (x) { return x !== t; });
      d.add = d.add.filter(function (x) { return x.ticker !== t; });
      d.add.push({ ticker: t, name: fN.value.trim() || t, industry: ind, note: "", wiki: fW.value.trim() });
      err.textContent = ""; fT.value = fN.value = fW.value = fNew.value = ""; save();
    });
    root.appendChild(h("div", { class: "card sec" }, [h("h2", null, "Ajouter une société"), h("div", { class: "toolbar" }, [fT, fN, fI, fNew, fW, addBtn]), err,
      h("p", { class: "note" }, "Le symbole doit exister sur Yahoo Finance. Exemples : AAPL, SHOP.TO (TSX), RY.TO, BTC-USD.")]));
    root.appendChild(out);

    function render() {
      var rows = U.map(function (c) { return { t: c.t, n: c.n, ind: d.move[c.t] || c.ind, src: c.src, pend: false }; });
      d.add.forEach(function (a) { if (!BYT[a.ticker]) rows.push({ t: a.ticker, n: a.name, ind: a.industry, src: "ajout", pend: true }); });
      rows = rows.filter(function (r) { return true; }).sort(function (a, b) { return a.ind.localeCompare(b.ind, "fr") || a.t.localeCompare(b.t); });
      var allInds = rows.map(function (r) { return r.ind; }).concat(inds).filter(function (v, i, a) { return a.indexOf(v) === i; }).sort(function (a, b) { return a.localeCompare(b, "fr"); });
      var body = rows.map(function (r) {
        var removed = d.remove.indexOf(r.t) >= 0;
        var sel = h("select", { "aria-label": "Industrie de " + r.t, disabled: removed }, allInds.map(function (i) { return h("option", { value: i, selected: i === r.ind }, i); }));
        sel.addEventListener("change", function () {
          var a = d.add.filter(function (x) { return x.ticker === r.t; })[0];
          if (a) a.industry = sel.value; else if (BYT[r.t] && sel.value === BYT[r.t].ind && !(W.move || {})[r.t]) delete d.move[r.t]; else d.move[r.t] = sel.value;
          save();
        });
        var btn = h("button", { class: "btn", type: "button" }, removed ? "Rétablir" : "Retirer");
        btn.addEventListener("click", function () {
          if (removed) d.remove = d.remove.filter(function (x) { return x !== r.t; });
          else if (r.src === "ajout") { d.add = d.add.filter(function (x) { return x.ticker !== r.t; }); }
          else d.remove.push(r.t);
          save();
        });
        return h("tr", { style: removed ? "opacity:.5;text-decoration:line-through" : null }, [h("td", { class: "tk" }, r.pend ? r.t : coLink(BYT[r.t])), h("td", null, r.n), h("td", null, sel),
          h("td", null, r.pend ? h("span", { class: "tag t-warn" }, "En attente") : r.src === "ajout" ? h("span", { class: "tag t-buy" }, "Ajoutée") : h("span", { class: "tag t-neu" }, "Liste du rapport")), h("td", null, btn)]);
      });
      var cleaned = { _aide: "Fichier modifiable depuis le site (page « Gérer les titres ») ou directement ici. add = sociétés à suivre; remove = symboles à retirer de la plateforme; move = changer l'industrie d'un symbole.", add: d.add, remove: d.remove.slice().sort(), move: d.move };
      var json = JSON.stringify(cleaned, null, 2);
      var ta = h("textarea", { readonly: true, rows: 10, "aria-label": "Contenu de watchlist.json", style: "width:100%;font:12.5px ui-monospace,Menlo,monospace;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)" }, json);
      var copy = h("button", { class: "btn pri", type: "button" }, "Copier le contenu");
      copy.addEventListener("click", function () {
        var done = function () { copy.textContent = "Copié ✓"; setTimeout(function () { copy.textContent = "Copier le contenu"; }, 1800); };
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(json).then(done, function () { ta.select(); document.execCommand("copy"); done(); });
        else { ta.select(); document.execCommand("copy"); done(); }
      });
      var reset = h("button", { class: "btn", type: "button" }, "Annuler mes changements");
      reset.addEventListener("click", function () { try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* ignoré */ } d = { add: (W.add || []).slice(), remove: (W.remove || []).slice(), move: Object.assign({}, W.move || {}) }; render(); });
      var host = location.hostname, links = [];
      if (/\.github\.io$/.test(host)) {
        var user = host.split(".")[0], repo = location.pathname.split("/")[1] || "";
        if (repo) { links.push(h("a", { class: "btn", href: "https://github.com/" + user + "/" + repo + "/edit/main/watchlist.json", target: "_blank", rel: "noopener" }, "Ouvrir watchlist.json dans GitHub"));
          links.push(h("a", { class: "btn", href: "https://github.com/" + user + "/" + repo + "/actions/workflows/rapport_quotidien.yml", target: "_blank", rel: "noopener" }, "Ouvrir les Actions (Run workflow)")); }
      }
      var dirty = JSON.stringify({ add: d.add, remove: d.remove.slice().sort(), move: d.move }) !== JSON.stringify({ add: W.add || [], remove: (W.remove || []).slice().sort(), move: W.move || {} });
      out.replaceChildren(
        h("div", { class: "card sec" }, [h("div", { class: "ch" }, [h("h2", null, "Titres suivis (" + rows.length + ")"), dirty ? h("span", { class: "tag t-warn" }, "Changements non enregistrés dans GitHub") : h("span", { class: "tag t-neu" }, "Identique au dépôt")]),
          h("div", { class: "tw", style: "max-height:520px" }, h("table", null, [h("thead", null, h("tr", null, ["Symbole", "Société", "Industrie", "Origine", ""].map(function (x) { return h("th", null, x); }))), h("tbody", null, body)])),
          h("p", { class: "note", style: "margin-top:8px" }, "« Liste du rapport » : titres des listes éditoriales (content.json). Retirer un tel titre le masque de la plateforme; le PDF quotidien garde ses listes. Changer l'industrie ne modifie que la plateforme.")]),
        h("div", { class: "card sec" }, [h("div", { class: "ch" }, [h("h2", null, "Contenu de watchlist.json"), h("div", { class: "toolbar", style: "margin:0" }, [copy].concat(links, [reset]))]), ta,
          links.length ? null : h("p", { class: "note" }, "Dans GitHub : ouvrez le fichier watchlist.json à la racine du dépôt, cliquez sur le crayon, remplacez tout le contenu, puis Commit changes.")]));
    }
    render();
    return root;
  }

  /* ── guide : définitions et calculs ──────────────────────── */
  var METHODS = [
    { id: "prix", t: "Prix et variations", b: [
      ["p", "Le prix affiché est la dernière clôture (le rapport part après la fermeture, à 17 h). Les variations comparent cette clôture à une clôture passée."],
      ["ul", ["1 j : clôture du jour ÷ clôture de la veille − 1.", "1 mois, 3 mois, 6 mois, 1 an : on recule de 21, 63, 126 et 252 séances de bourse (une année boursière compte environ 252 jours).", "Depuis janv. : comparé à la dernière clôture de l'année précédente.", "52 semaines : plus bas et plus haut des 252 dernières séances. « Sous le sommet » = prix ÷ plus haut − 1."]],
      ["ex", "Exemple : un titre clôture à 90 $, son plus haut sur 52 semaines est 120 $. Il est à 90 ÷ 120 − 1 = −25 % sous son sommet. S'il valait 80 $ il y a 21 séances, sa variation sur 1 mois est 90 ÷ 80 − 1 = +12,5 %."]] },
    { id: "ma", t: "Moyennes mobiles : MA50 et MA200", b: [
      ["p", "La MA50 est la moyenne des 50 dernières clôtures, la MA200 celle des 200 dernières. Elles lissent le bruit quotidien : la MA50 suit la tendance des deux derniers mois, la MA200 la tendance de fond (environ 10 mois)."],
      ["ex", "Exemple : si le prix est au-dessus de sa MA200, le titre est généralement considéré en tendance haussière de long terme; en dessous, en tendance baissière. Cela décrit le passé, pas l'avenir."]] },
    { id: "tendance", t: "Tendance : Golden Cross, Death Cross, Neutre", b: [
      ["p", "La colonne Tendance compare la MA50 à la MA200."],
      ["table", { head: ["Tendance", "Condition", "Lecture"], rows: [
        ["Golden Cross (croisement doré)", "MA50 au-dessus de la MA200 d'au moins 0,5 %", "Élan récent supérieur à la tendance de fond : configuration haussière"],
        ["Death Cross (croisement de la mort)", "MA50 sous la MA200 d'au moins 0,5 %", "Élan récent inférieur à la tendance de fond : configuration baissière"],
        ["Neutre", "Écart de moins de 0,5 % entre les deux", "Les deux moyennes sont presque confondues : pas de direction claire"],
        ["N/D", "Moins de 200 jours d'historique", "Calcul impossible (société récemment inscrite en bourse)"]] }],
      ["p", "Précision : à proprement parler, le « croisement » est l'événement où la MA50 traverse la MA200. Cette plateforme affiche l'état actuel (au-dessus ou en dessous), qui peut durer des mois après l'événement."],
      ["ex", "Exemple : MA50 = 105 $ et MA200 = 100 $ → écart de +5 % → Golden Cross. MA50 = 94 $ et MA200 = 100 $ → −6 % → Death Cross. MA50 = 100,3 $ et MA200 = 100 $ → +0,3 % → Neutre."],
      ["p", "Limites : ce sont des indicateurs retardataires. Dans un marché sans direction, ils produisent de faux signaux, et un Death Cross apparaît souvent après une grande partie de la baisse."]] },
    { id: "rsi", t: "RSI (indice de force relative, 14 jours)", b: [
      ["p", "Le RSI mesure la vitesse des hausses par rapport aux baisses récentes, sur une échelle de 0 à 100 (méthode de Wilder, 14 jours). RSI = 100 − 100 ÷ (1 + RS), où RS = gain moyen ÷ perte moyenne des 14 derniers jours."],
      ["ul", ["Moins de 30 : survente (le titre a beaucoup baissé, un rebond est possible).", "Plus de 70 : surachat (le titre a beaucoup monté, un repli est possible).", "Entre 30 et 70 : zone neutre."]],
      ["ex", "Exemple : gain moyen de 1,2 $ et perte moyenne de 0,8 $ → RS = 1,5 → RSI = 100 − 100 ÷ 2,5 = 60 (neutre). Si la perte moyenne grimpe à 2,4 $ et le gain tombe à 0,6 $ → RS = 0,25 → RSI = 20 (survente)."],
      ["p", "Limite : un titre en forte tendance peut rester en surachat pendant des semaines."]] },
    { id: "macd", t: "MACD (12, 26, 9)", b: [
      ["p", "Le MACD mesure l'élan (momentum). Ligne MACD = moyenne mobile exponentielle sur 12 jours − celle sur 26 jours. Signal = moyenne exponentielle sur 9 jours de la ligne MACD. Histogramme = ligne − signal."],
      ["ul", ["Histogramme positif (barres vertes) : l'élan haussier s'accélère → signal ACHAT.", "Histogramme négatif (barres rouges) : l'élan baissier domine → signal VENTE."]],
      ["ex", "Exemple : ligne MACD = +2,1 et signal = +1,5 → histogramme = +0,6 → positif, donc haussier. Le changement de signe de l'histogramme (de négatif à positif) est le moment classique d'un « croisement haussier »."]] },
    { id: "signal", t: "Signal technique (colonne « Signal technique »)", b: [
      ["p", "Un score simple sur quatre tests, qui valent chacun +1, 0 ou −1."],
      ["table", { head: ["Test", "+1", "−1", "0"], rows: [
        ["RSI", "RSI < 30 (survente)", "RSI > 70 (surachat)", "Entre les deux"],
        ["MACD", "Histogramme > 0", "Histogramme ≤ 0", "—"],
        ["Prix et MA200", "Prix > MA200", "Prix ≤ MA200", "—"],
        ["MA50 et MA200", "MA50 > MA200", "MA50 ≤ MA200", "—"]] }],
      ["p", "Total de +3 ou plus : ACHAT. De −3 ou moins : VENTE. Entre −1 et −2 : PRUDENCE. Sinon (0, +1, +2) : NEUTRE. Il faut au moins 3 tests calculables, sinon N/D."],
      ["ex", "Exemple : RSI = 55 (0), histogramme positif (+1), prix au-dessus de la MA200 (+1), MA50 au-dessus de la MA200 (+1) → total +3 → ACHAT. Autre cas : RSI = 75 (−1), histogramme négatif (−1), prix sous la MA200 (−1), Death Cross (−1) → −4 → VENTE."]] },
    { id: "val", t: "Valorisation : P/E, médiane du secteur, cible et potentiel", b: [
      ["p", "Le P/E prévisionnel est le prix ÷ le bénéfice par action attendu sur 12 mois : il dit combien de dollars le marché paie pour 1 $ de bénéfice futur. On le compare à la médiane de son secteur (valeur saisie à la main dans content.json)."],
      ["p", "Signal P/E : ratio = P/E ÷ P/E médian du secteur. Moins de 0,85 : ACHAT (décote de plus de 15 %). Plus de 1,5 : VENTE (prime de plus de 50 %). Sinon NEUTRE. Sans P/E, NEUTRE."],
      ["ex", "Exemple : P/E de 17 et médiane de 28 → ratio 0,61 → ACHAT. P/E de 45 et médiane de 28 → ratio 1,61 → VENTE. P/E de 30 et médiane de 28 → 1,07 → NEUTRE."],
      ["p", "Potentiel de la cible = cible moyenne des analystes ÷ prix − 1. Conviction (étoiles de 1 à 5) = jugement saisi à la main. Ces trois valeurs ne se mettent pas à jour automatiquement : leur date figure sur la fiche de la société."],
      ["ex", "Exemple : prix de 100 $, cible de 130 $ → potentiel de +30 %. Un P/E bas peut aussi signaler un risque (bénéfices à leur sommet de cycle), d'où l'intérêt de la confluence."],
      ["p", "Colonne « Valorisation » (pages Confluence et Explorer) : « Sous-évalué » ou « Surévalué » si la société figure dans l'une des deux listes éditoriales du rapport; sinon on utilise le ratio P/E ÷ médiane du secteur (moins de 0,85 : sous-évalué; entre 0,85 et 1,5 : valeur juste; plus de 1,5 : surévalué). Sans P/E saisi : N/D, ce qui est le cas des sociétés suivies seulement pour leur cours (listes semi-conducteurs, cybersécurité, commerce de détail, titres ajoutés)."],
      ["ex", "Exemple : une société de la liste « sous-évaluées » avec un verdict ACHAT combine un prix attrayant et des signaux favorables. Une société « surévaluée » avec le verdict PRUDENCE cumule prix élevé et signaux défavorables."]] },
    { id: "sent", t: "Sentiment de marché : Fear & Greed, VIX, AAII", b: [
      ["p", "Ces trois signaux sont « contrariens » : on achète quand les autres ont peur, on se méfie quand tout le monde est euphorique."],
      ["table", { head: ["Indicateur", "ACHAT", "VENTE", "Qu'est-ce que c'est ?"], rows: [
        ["Fear & Greed (CNN, 0 à 100)", "44 ou moins (peur)", "74 ou plus (cupidité)", "Indice composite de 7 mesures de sentiment des marchés boursiers américains"],
        ["VIX", "Plus de 30 (panique)", "Moins de 15 (complaisance)", "Volatilité attendue du S&P 500 sur 30 jours, dite « indice de la peur »"],
        ["AAII (écart)", "Moins de −20 points", "Plus de +25 points", "Écart entre % d'investisseurs particuliers haussiers et % baissiers (sondage hebdomadaire)"]] }],
      ["ex", "Exemple AAII : 40,3 % haussiers et 39,0 % baissiers → écart de +1,3 point → NEUTRE. Avec 20 % haussiers et 45 % baissiers → −25 points → ACHAT (pessimisme extrême). Ces trois signaux sont les mêmes pour tous les titres : ils décrivent le marché, pas la société."]] },
    { id: "ma200s", t: "Signal MA200 (matrice de confluence)", b: [
      ["p", "Légèrement différent du test du signal technique : ratio = prix ÷ MA200. 1,00 ou plus : ACHAT. Moins de 0,95 : VENTE. Entre 0,95 et 1,00 : NEUTRE (zone de tolérance de 5 %)."],
      ["ex", "Exemple : prix de 97 $ et MA200 de 100 $ → 0,97 → NEUTRE. Prix de 90 $ → 0,90 → VENTE. Prix de 104 $ → 1,04 → ACHAT."]] },
    { id: "social", t: "Signaux sociaux et initiés", b: [
      ["ul", ["Social (mentions Reddit sur 24 h, via ApeWisdom) : moins de 5 mentions : NEUTRE (silence). De 5 à 299 : ACHAT (intérêt qui s'éveille). 300 et plus : VENTE (euphorie, risque de foule).", "À défaut d'ApeWisdom, mentions Reddit directes : 1 à 9 : ACHAT; 10 et plus : VENTE.", "Initiés (formulaire 4 de la SEC, 45 jours, titres américains) : achats en marché ouvert de 100 000 $ ou plus et supérieurs aux ventes : ACHAT. Ventes de 25 M$ ou plus sans aucun achat : VENTE. Sinon NEUTRE. Sans donnée de la SEC, la valeur saisie à la main est utilisée."]],
      ["ex", "Exemple : 147 mentions → ACHAT; 480 mentions → VENTE; 2 mentions → NEUTRE. Un dirigeant qui achète 400 000 $ d'actions sur le marché (sans vendre) est un signe de confiance plus fiable qu'une vente, car les dirigeants vendent pour toutes sortes de raisons (impôts, diversification)."],
      ["p", "Les rangs StockTwits, les pages vues Wikipédia et les vidéos YouTube sont affichés à titre d'information sur la fiche, mais n'entrent pas dans le verdict."]] },
    { id: "conf", t: "Confluence et verdict (9 signaux)", b: [
      ["p", "Pour chaque société, on compte combien des 9 signaux (P/E, Fear & Greed, VIX, RSI, MACD, MA200, Social, Initiés, AAII) disent ACHAT, VENTE ou NEUTRE. Plus plusieurs signaux indépendants concordent, plus la lecture est solide."],
      ["table", { head: ["Condition (évaluée dans cet ordre)", "Verdict"], rows: [
        ["6 achats ou plus", "FORT ACHAT"], ["4 ou 5 achats", "ACHAT"], ["6 ventes ou plus", "FORT VENTE"], ["4 ou 5 ventes", "VENTE"], ["3 ventes", "PRUDENCE"], ["Autrement", "NEUTRE"]] }],
      ["ex", "Exemple : P/E ACHAT, Fear & Greed NEUTRE, VIX VENTE, RSI NEUTRE, MACD ACHAT, MA200 ACHAT, Social ACHAT, Initiés NEUTRE, AAII NEUTRE → 4 achats et 1 vente → ACHAT. Autre exemple : 2 achats et 3 ventes → PRUDENCE."],
      ["p", "Si une société atteignait 4 achats et 4 ventes en même temps, l'achat est évalué en premier. Les signaux de marché (Fear & Greed, VIX, AAII) comptent chacun pour tous les titres : ils pèsent donc 3 des 9 points de toutes les sociétés."]] },
    { id: "agg", t: "Termes de la plateforme", b: [
      ["ul", ["Indice équipondéré (page d'une industrie) : chaque jour, moyenne simple des rendements de toutes les sociétés de l'industrie, enchaînée à partir de 100. Chaque société compte autant, quelle que soit sa taille.", "Base 100 : chaque courbe est ramenée à 100 au début de la période choisie, pour comparer des titres de prix très différents. 130 signifie +30 %.", "Au-dessus de la MA200 : nombre de sociétés d'une industrie dont le prix dépasse la MA200.", "Instantané quotidien : photo des signaux enregistrée chaque jour d'exécution; elle sert à bâtir l'historique des signaux, qui commence à la première exécution.", "N/D : la source n'a pas répondu ou l'historique est insuffisant. Aucune valeur n'est inventée.", "Listes « sous-évaluées / surévaluées » : sélection éditoriale du 13 octobre 2026, pas un calcul automatique."]]] },
    { id: "avert", t: "À garder en tête", b: [
      ["p", "Les signaux sont mécaniques et n'ont pas été validés par un test historique. Ils servent à repérer des titres à examiner, pas à décider seuls. Document informatif seulement; ne constitue pas un conseil en placement. Pour un placement dans une société, pensez aussi à l'effet fiscal (revenu de placement passif dans une société par actions)."]] }
  ];
  function methodsSection() {
    var wrap = h("div", { class: "sec", id: "methodes" }, [h("h2", { style: "margin-bottom:6px" }, "Guide : comment lire et calculer chaque chiffre"),
      h("p", { class: "note" }, "Toutes les formules utilisées par la plateforme, avec des exemples chiffrés (fictifs).")]);
    var qs = parseQuery().s;
    METHODS.forEach(function (m, i) {
      var det = h("details", { class: "card", id: "m-" + m.id, style: "margin-top:10px", open: qs ? m.id === qs : i === 0 }, [h("summary", { style: "cursor:pointer;font-weight:600;font-size:15px" }, m.t)]);
      m.b.forEach(function (x) {
        if (x[0] === "p") det.appendChild(h("p", { style: "margin:10px 0 0" }, x[1]));
        else if (x[0] === "ul") det.appendChild(h("ul", { class: "list" }, x[1].map(function (t) { return h("li", null, t); })));
        else if (x[0] === "ex") det.appendChild(h("p", { style: "margin:10px 0 0;padding:9px 12px;border-left:3px solid var(--green);background:var(--surface2);border-radius:0 6px 6px 0" }, x[1]));
        else if (x[0] === "table") det.appendChild(h("div", { class: "tw", style: "margin-top:10px" }, h("table", null, [h("thead", null, h("tr", null, x[1].head.map(function (c) { return h("th", null, c); }))),
          h("tbody", null, x[1].rows.map(function (r) { return h("tr", null, r.map(function (c) { return h("td", { style: "white-space:normal;min-width:120px" }, c); })); }))])));
      });
      wrap.appendChild(det);
    });
    return wrap;
  }

  function notFound(msg) { return h("div", { class: "empty" }, [h("h1", null, "Introuvable"), h("p", null, msg), h("a", { class: "btn pri", href: "#/explorer" }, "Explorer les sociétés")]); }
  function pageEmpty() {
    return h("div", { class: "empty" }, [h("h1", null, "Aucune donnée pour l'instant"),
      h("p", null, "La plateforme se remplit à la première exécution du robot quotidien."),
      h("p", null, "Dans GitHub : onglet Actions → « Rapport Social Investing quotidien » → Run workflow. Rechargez cette page ensuite.")]);
  }

  /* ── routeur, navigation, recherche ──────────────────────── */
  var NAV = [["#/", "Marché"], ["#/explorer", "Explorer"], ["#/confluence", "Confluence"], ["#/industries", "Industries"], ["#/compare", "Comparer"], ["#/history", "Historique"], ["#/manage", "Gérer les titres"], ["#/sources", "Sources et méthodes"]];
  function route() {
    var raw = location.hash.replace(/^#/, "") || "/", path = raw.split("?")[0], parts = path.split("/").filter(Boolean);
    tip.hidden = true; groups = {};
    var key = "#/" + (parts[0] || ""), node;
    if (META.empty) node = pageEmpty();
    else if (!parts.length) node = pageMarket();
    else if (parts[0] === "explorer") node = pageExplorer();
    else if (parts[0] === "confluence") node = pageConfluence();
    else if (parts[0] === "industries") node = pageIndustries();
    else if (parts[0] === "i") node = pageIndustry(decodeURIComponent(parts[1] || ""));
    else if (parts[0] === "t") node = pageCompany(decodeURIComponent(parts[1] || "").toUpperCase());
    else if (parts[0] === "compare") node = pageCompare();
    else if (parts[0] === "history") node = pageHistory();
    else if (parts[0] === "manage") node = pageManage();
    else if (parts[0] === "sources") node = pageSources();
    else node = notFound("Cette page n'existe pas.");
    main.replaceChildren(node);
    var tgt = parts[0] === "sources" && parseQuery().s ? document.getElementById("m-" + parseQuery().s) : null;
    var cur = parts[0] === "t" ? "#/explorer" : parts[0] === "i" ? "#/industries" : key;
    Array.prototype.forEach.call($("#nav").children, function (a) { if (a.getAttribute("href") === cur) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    if (tgt) tgt.scrollIntoView(); else window.scrollTo(0, 0);
    document.title = (parts[0] === "t" && BYT[(parts[1] || "").toUpperCase()] ? BYT[parts[1].toUpperCase()].n + " — " : "") + "Le Pinson Boursier";
  }
  function initSearch() {
    var inp = $("#gsearch"), ul = $("#gresults"), sel = -1, items = [];
    function close() { ul.hidden = true; sel = -1; }
    function go(it) { close(); inp.value = ""; location.hash = it.href; }
    function upd() {
      var t = inp.value.trim().toLowerCase();
      if (!t || !U) return close();
      items = [];
      U.forEach(function (c) { var s = (c.t + " " + c.n).toLowerCase(); if (s.indexOf(t) >= 0) items.push({ r: c.t.toLowerCase() === t ? 0 : c.t.toLowerCase().indexOf(t) === 0 ? 1 : 2, a: c.t, b: c.n, c: c.ind, href: "#/t/" + enc(c.t) }); });
      SI.data.universe.industries.forEach(function (i) { if (i.toLowerCase().indexOf(t) >= 0) items.push({ r: 1, a: "Industrie", b: i, c: "", href: "#/i/" + enc(i) }); });
      items.sort(function (x, y) { return x.r - y.r; }); items = items.slice(0, 8);
      ul.replaceChildren.apply(ul, items.map(function (it, i) { var li = h("li", { role: "option", "aria-selected": "false" }, [h("b", null, it.a), h("span", null, it.b), h("small", null, it.c)]); li.addEventListener("mousedown", function (e) { e.preventDefault(); go(it); }); return li; }));
      ul.hidden = !items.length; sel = -1;
    }
    inp.addEventListener("input", upd);
    inp.addEventListener("blur", function () { setTimeout(close, 100); });
    inp.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % (items.length || 1); Array.prototype.forEach.call(ul.children, function (li, i) { li.setAttribute("aria-selected", String(i === sel)); }); }
      else if (e.key === "Enter") { if (sel >= 0 && items[sel]) go(items[sel]); else if (items.length === 1) go(items[0]); else if (inp.value.trim()) { var v = inp.value.trim(); close(); inp.value = ""; location.hash = "#/explorer?q=" + enc(v); } }
      else if (e.key === "Escape") close();
    });
  }
  function init() {
    var nav = $("#nav");
    NAV.forEach(function (n) { nav.appendChild(h("a", { href: n[0] }, n[1])); });
    var themeBtn = $("#theme"), saved = lsGet("si-theme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);
    themeBtn.addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme:dark)").matches ? "dark" : "light");
      var nx = cur === "dark" ? "light" : "dark"; document.documentElement.setAttribute("data-theme", nx); lsSet("si-theme", nx); route();
    });
    load("data/meta.js").then(function () {
      META = SI.data.meta;
      var pb = $("#pdfbtn");
      if (META.pdf && pb) { pb.href = META.pdf.latest; pb.title = "Rapport PDF du " + META.date_fr + (META.pdf.size ? " (" + Math.round(META.pdf.size / 1024) + " Ko)" : ""); pb.hidden = false; }
      if (META.empty) { initBanner(); route(); return; }
      return Promise.all([load("data/universe.js"), load("data/market.js"), load("data/sources.js")]).then(function () {
        U = SI.data.universe.companies; BYT = {}; U.forEach(function (c) { BYT[c.t] = c; });
        M = SI.data.market; SRC = SI.data.sources;
        $("#foot-meta").textContent = "Données du " + META.date_fr + " · " + META.n + " sociétés · historique cumulé depuis le " + META.history_from + ".";
        initBanner(); initSearch(); route();
      });
    }).catch(function (e) {
      main.replaceChildren(h("div", { class: "empty" }, [h("h1", null, "Données introuvables"), h("p", null, e.message), h("p", null, "Vérifiez que le dossier docs/data existe et que le robot quotidien a tourné au moins une fois.")]));
    });
    window.addEventListener("hashchange", function () { if (META) route(); });
  }
  var META;
  function initBanner() {
    var b = $("#banner"); b.replaceChildren();
    var wrap = h("div", { class: "banner-wrap" });
    if (META.demo) wrap.appendChild(h("div", { class: "banner demo", role: "status" }, "Données de démonstration : cours et indicateurs synthétiques, aucune valeur réelle. Elles seront remplacées dès la première exécution réelle."));
    else if (!META.empty && daysAgo(META.date_iso) > 4) wrap.appendChild(h("div", { class: "banner warn", role: "status" }, "Dernière mise à jour il y a " + daysAgo(META.date_iso) + " jours (" + META.date_fr + ") : vérifiez le robot quotidien dans l'onglet Actions de GitHub."));
    b.appendChild(wrap);
  }
  init();
})();
