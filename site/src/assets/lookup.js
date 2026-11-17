/* Supplier lookup: client-side search over a compact JSON index of UK statutory reports.
   The index is lazy-loaded on first keystroke. No external requests. */
(function () {
  "use strict";
  var input = document.getElementById("lookup-q");
  var out = document.getElementById("lookup-results");
  var status = document.getElementById("lookup-status");
  if (!input || !out) return;
  var DATA = null, loading = null, NORM = null;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function norm(s) { return String(s).toLowerCase().replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim(); }
  function date(n) { var s = String(n); return parseInt(s.slice(6, 8), 10) + " " + MONTHS[parseInt(s.slice(4, 6), 10) - 1] + " " + s.slice(0, 4); }
  function num(v, unit) { return v === null || v === undefined ? "not reported" : (Math.round(v * 10) / 10) + (unit || ""); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }

  function load() {
    if (DATA) return Promise.resolve(DATA);
    if (loading) return loading;
    status.textContent = "Loading the index...";
    loading = fetch(input.getAttribute("data-index")).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (d) {
      DATA = d;
      NORM = d.rows.map(function (r) { return norm(r[0]); });
      return d;
    }).catch(function (e) {
      loading = null;
      status.textContent = "Could not load the index (" + e.message + "). The page needs to be served over HTTP.";
      throw e;
    });
    return loading;
  }

  function search(q) {
    var rows = DATA.rows, hits = [], i;
    var raw = q.trim();
    if (/^[A-Za-z]{0,2}\d{3,8}$/.test(raw)) {
      var m = raw.toUpperCase();
      var padded = /^\d+$/.test(m) ? ("00000000" + m).slice(-8) : m;
      for (i = 0; i < rows.length; i++) {
        if (rows[i][1] === padded) hits.push([0, i]);
        else if (rows[i][1].indexOf(m) === 0) hits.push([1, i]);
      }
    }
    var k = norm(raw);
    if (k.length >= 2) {
      var toks = k.split(" ");
      for (i = 0; i < rows.length; i++) {
        var n = NORM[i], ok = true;
        for (var t = 0; t < toks.length; t++) { if (n.indexOf(toks[t]) === -1) { ok = false; break; } }
        if (!ok) continue;
        var score = n === k ? 2 : (n.indexOf(k) === 0 ? 3 : (n.indexOf(k) !== -1 ? 4 : 5));
        hits.push([score, i]);
      }
    }
    hits.sort(function (a, b) {
      if (a[0] !== b[0]) return a[0] - b[0];
      var ra = rows[a[1]], rb = rows[b[1]];
      if (ra[12] !== rb[12]) return ra[12] - rb[12];           // current reports first
      return ra[0].length - rb[0].length || (ra[0] < rb[0] ? -1 : 1);
    });
    var seen = {}, res = [];
    hits.forEach(function (h) { if (!seen[h[1]]) { seen[h[1]] = 1; res.push(h[1]); } });
    return res;
  }

  function kv(parent, value, label) {
    var d = el("div"); d.appendChild(el("b", null, value)); d.appendChild(el("span", null, label)); parent.appendChild(d);
  }

  function card(r) {
    // r: [name, number, days, pct30, pct31_60, pct_over60, pct_late, terms_short, terms_long, max_contract, period_start, period_end, old, late_flag, report_id, group_idx]
    var li = el("li", "result");
    li.setAttribute("data-number", r[1]);
    li.setAttribute("data-days", r[2] === null ? "" : r[2]);
    li.appendChild(el("h3", null, r[0]));
    var meta = "Company number " + r[1] + " · Reporting period " + date(r[10]) + " to " + date(r[11]);
    if (r[15] !== null && r[15] !== undefined) meta += " · Matched to group: " + DATA.groups[r[15]];
    li.appendChild(el("p", "meta", meta));
    var g = el("div", "kv");
    kv(g, num(r[2]), "average reported days to pay");
    kv(g, num(r[3], "%"), "invoices paid within 30 days");
    kv(g, num(r[5], "%"), "invoices paid after more than 60 days");
    kv(g, num(r[6], "%"), "invoices not paid within agreed terms");
    li.appendChild(g);
    var terms = "Standard payment terms: ";
    if (r[7] === null) terms += "not reported";
    else if (r[8] === null || r[8] === r[7]) terms += r[7] + " days";
    else terms += r[7] + " to " + r[8] + " days";
    terms += ". Longest contractual payment period: " + (r[9] === null ? "not reported" : r[9] + " days") + ".";
    li.appendChild(el("p", "small", terms));
    if (r[13]) li.appendChild(el("p", "note warn", "The late share in this report does not fit the report's own payment bands. The company may have entered the on-time share. Read it with care."));
    if (r[12]) li.appendChild(el("p", "note warn", "This is an old report: the latest usable report for this company ended on " + date(r[11]) + ". Payment practice may have changed since."));
    var p = el("p", "src");
    var a = el("a", null, "Official report on GOV.UK (report " + r[14] + ")");
    a.href = DATA.report_base + r[14]; a.rel = "noopener";
    p.appendChild(document.createTextNode("Source: ")); p.appendChild(a);
    p.appendChild(document.createTextNode(". Figures as filed by the company."));
    li.appendChild(p);
    return li;
  }

  function render() {
    var q = input.value;
    out.textContent = "";
    if (q.trim().length < 2) { status.textContent = "Type at least two characters."; return; }
    var res = search(q), max = 25;
    if (!res.length) {
      status.textContent = "No UK statutory report found for “" + q.trim() + "”. Only large UK companies and LLPs have to report, and they report under their legal entity name.";
      return;
    }
    status.textContent = res.length + (res.length === 1 ? " company" : " companies") + " found" + (res.length > max ? ", showing the first " + max : "") + ".";
    var frag = document.createDocumentFragment();
    res.slice(0, max).forEach(function (i) { frag.appendChild(card(DATA.rows[i])); });
    out.appendChild(frag);
  }

  var timer = null;
  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () { load().then(render, function () {}); }, 90);
  });
  var pre = new URLSearchParams(window.location.search).get("q");
  if (pre) { input.value = pre; load().then(render, function () {}); }
})();
