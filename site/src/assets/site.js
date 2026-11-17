/* The Chase Index: table sort/filter and chart tooltips. Vanilla JS, no dependencies. */
(function () {
  "use strict";

  // ---- tooltips for chart marks ----
  var tip = document.getElementById("tip");
  if (tip) {
    var show = function (el, x, y) {
      tip.textContent = el.getAttribute("data-tip");
      tip.style.display = "block";
      var w = tip.offsetWidth, vw = document.documentElement.clientWidth;
      tip.style.left = Math.max(4, Math.min(x + 12, vw - w - 4)) + "px";
      tip.style.top = Math.max(4, y - tip.offsetHeight - 10) + "px";
    };
    document.addEventListener("mousemove", function (e) {
      var el = e.target.closest ? e.target.closest("[data-tip]") : null;
      if (el) show(el, e.clientX, e.clientY); else tip.style.display = "none";
    });
    document.addEventListener("focusin", function (e) {
      var el = e.target.closest ? e.target.closest("[data-tip]") : null;
      if (el) { var r = el.getBoundingClientRect(); show(el, r.left + r.width / 2, r.top); }
    });
    document.addEventListener("focusout", function () { tip.style.display = "none"; });
  }

  // ---- sortable, filterable tables ----
  Array.prototype.forEach.call(document.querySelectorAll("table[data-sortable]"), function (table) {
    var tbody = table.tBodies[0];
    var rows = Array.prototype.slice.call(tbody.rows);
    var heads = table.querySelectorAll("th[data-col]");

    function key(row, col, numeric) {
      var td = row.cells[col];
      var v = td.getAttribute("data-v");
      if (v === null) v = td.textContent.trim();
      if (!numeric) return v.toLowerCase();
      return v === "" ? null : parseFloat(v);
    }
    function sortBy(th, dir) {
      var col = parseInt(th.getAttribute("data-col"), 10);
      var numeric = th.getAttribute("data-type") === "num";
      rows.sort(function (a, b) {
        var x = key(a, col, numeric), y = key(b, col, numeric);
        if (x === null && y === null) return 0;
        if (x === null) return 1;            // empty values always last
        if (y === null) return -1;
        if (x < y) return dir === "ascending" ? -1 : 1;
        if (x > y) return dir === "ascending" ? 1 : -1;
        return 0;
      });
      Array.prototype.forEach.call(heads, function (h) { h.removeAttribute("aria-sort"); });
      th.setAttribute("aria-sort", dir);
      var frag = document.createDocumentFragment();
      rows.forEach(function (r) { frag.appendChild(r); });
      tbody.appendChild(frag);
    }
    Array.prototype.forEach.call(heads, function (th) {
      var btn = th.querySelector("button.sort");
      if (!btn) return;
      btn.addEventListener("click", function () {
        var cur = th.getAttribute("aria-sort");
        var first = th.getAttribute("data-type") === "num" ? "descending" : "ascending";
        var dir = !cur ? first : (cur === "ascending" ? "descending" : "ascending");
        sortBy(th, dir);
      });
    });

    var box = document.querySelector('[data-filter-for="' + table.id + '"]');
    if (!box) return;
    var qEl = box.querySelector("[data-f=q]"), cEl = box.querySelector("[data-f=country]"),
        sEl = box.querySelector("[data-f=sector]"), pEl = box.querySelector("[data-f=proxy]"),
        count = box.querySelector("[data-count]"), more = document.querySelector('[data-more-for="' + table.id + '"]');
    var LIMIT = 50, showAll = false;
    if (more) more.addEventListener("click", function () { showAll = true; apply(); });
    var sortBy0 = sortBy;
    sortBy = function (th, dir) { sortBy0(th, dir); apply(); };
    function apply() {
      var q = qEl ? qEl.value.trim().toLowerCase() : "", c = cEl ? cEl.value : "", s = sEl ? sEl.value : "";
      var proxy = pEl ? pEl.checked : true, n = 0;
      rows.forEach(function (r) {
        var ok = (!q || r.getAttribute("data-name").indexOf(q) !== -1) &&
                 (!c || r.getAttribute("data-country") === c) &&
                 (!s || r.getAttribute("data-sector") === s) &&
                 (proxy || r.getAttribute("data-reported") === "1");
        if (ok) n++;
        r.hidden = !ok || (!showAll && n > LIMIT);
      });
      if (count) count.textContent = n + (n === 1 ? " group" : " groups");
      if (more) { more.hidden = showAll || n <= LIMIT; more.textContent = "Show all " + n + " groups"; }
    }
    [qEl, cEl, sEl, pEl].forEach(function (el) {
      if (el) { el.addEventListener("input", apply); el.addEventListener("change", apply); }
    });
    apply();
  });
})();
