// Chase Index workspace: table filters and dinner list copy. No network calls.
(function () {
  "use strict";

  // filters: <div class="filters" data-target="#table"> with <select data-filter="attr">
  document.querySelectorAll(".filters").forEach(function (box) {
    var table = document.querySelector(box.getAttribute("data-target"));
    if (!table) return;
    var selects = box.querySelectorAll("select[data-filter]");
    var count = box.querySelector(".count");
    function apply() {
      var n = 0, rows = table.querySelectorAll("tbody tr, .qrow");
      rows.forEach(function (tr) {
        var ok = true;
        selects.forEach(function (s) {
          if (s.value && tr.getAttribute("data-" + s.getAttribute("data-filter")) !== s.value) ok = false;
        });
        tr.hidden = !ok;
        if (ok) n++;
      });
      if (count) count.textContent = n + " of " + rows.length + " shown";
    }
    selects.forEach(function (s) { s.addEventListener("change", apply); });
    apply();
  });

  // queue: expand / collapse all, copy an opener
  document.querySelectorAll("[data-toggle-all]").forEach(function (b) {
    var list = document.querySelector(b.getAttribute("data-toggle-all"));
    if (!list) return;
    b.addEventListener("click", function () {
      var items = list.querySelectorAll("details:not([hidden])");
      var open = Array.prototype.some.call(items, function (d) { return !d.open; });
      items.forEach(function (d) { d.open = open; });
      b.textContent = open ? "Collapse all" : "Expand all";
    });
  });
  document.querySelectorAll("button.copy[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () { copy(b.getAttribute("data-copy"), b); });
  });

  // dinner builder
  function csvCell(v) { v = String(v == null ? "" : v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
  function copy(text, btn) {
    var done = function () { var t = btn.textContent; btn.textContent = "Copied"; setTimeout(function () { btn.textContent = t; }, 1200); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(text); done(); });
    } else { fallback(text); done(); }
  }
  function fallback(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) { /* clipboard unavailable */ }
    document.body.removeChild(ta);
  }
  document.querySelectorAll(".dinner").forEach(function (card) {
    var rows = Array.prototype.slice.call(card.querySelectorAll("tr[data-row]"));
    var count = card.querySelector(".count");
    function picked() { return rows.filter(function (r) { return r.querySelector("input").checked; }); }
    function refresh() {
      rows.forEach(function (r) { r.classList.toggle("off", !r.querySelector("input").checked); });
      if (count) count.textContent = picked().length + " of " + rows.length + " selected";
    }
    rows.forEach(function (r) { r.querySelector("input").addEventListener("change", refresh); });
    card.querySelectorAll("button[data-act]").forEach(function (b) {
      b.addEventListener("click", function () {
        var act = b.getAttribute("data-act");
        if (act === "all" || act === "none") {
          rows.forEach(function (r) { r.querySelector("input").checked = act === "all"; });
          return refresh();
        }
        var city = card.getAttribute("data-city"), date = card.getAttribute("data-date") || "date tbc";
        var sel = picked();
        var text;
        if (act === "csv") {
          text = ["city,date,company,tier,hq_city,local_link,hook,source_url"].concat(sel.map(function (r) {
            return [city, date, r.dataset.company, r.dataset.tier, r.dataset.hq, r.dataset.local, r.dataset.hook, r.dataset.source].map(csvCell).join(",");
          })).join("\n");
        } else {
          text = city.charAt(0).toUpperCase() + city.slice(1) + " dinner (" + date + "), " + sel.length + " accounts\n\n" +
            sel.map(function (r, i) { return (i + 1) + ". " + r.dataset.company + " (T" + r.dataset.tier + ", " + (r.dataset.hq || "HQ unknown") + ")\n   " + r.dataset.hook + "\n   Source: " + r.dataset.source; }).join("\n\n");
        }
        copy(text, b);
      });
    });
    refresh();
  });
})();
