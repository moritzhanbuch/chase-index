// Chase Index workspace: filters, queue status, keyboard shortcuts and dinner list copy. No network calls.
(function () {
  "use strict";

  var refilter = [];
  // filters: <div class="filters" data-target="#table"> with <select data-filter="attr">
  document.querySelectorAll(".filters").forEach(function (box) {
    var table = document.querySelector(box.getAttribute("data-target"));
    if (!table) return;
    var selects = box.querySelectorAll("select[data-filter]");
    var count = box.querySelector(".count");
    var win = box.querySelector("select[data-window]");
    function isoDay(offset) { var d = new Date(); d.setDate(d.getDate() + offset); return d.toISOString().slice(0, 10); }
    function apply() {
      var n = 0, rows = table.querySelectorAll("tbody tr, .qrow"), today = isoDay(0), from = win && /^\d+$/.test(win.value) ? isoDay(-Number(win.value)) : null;
      rows.forEach(function (tr) {
        var ok = true;
        selects.forEach(function (s) {
          var v = tr.getAttribute("data-" + s.getAttribute("data-filter"));
          if (s.value && v !== s.value) ok = false;
          // "All" can still leave one type out (e.g. dinner triggers), until that type is picked explicitly
          if (!s.value && s.dataset.hideOnAll && v === s.dataset.hideOnAll) ok = false;
        });
        if (win && win.value) {
          var dt = tr.getAttribute("data-date") || "";
          if (win.value === "up" ? dt <= today : (dt < from || dt > today)) ok = false;
        }
        tr.hidden = !ok;
        if (ok) n++;
      });
      if (count) count.textContent = n + " of " + rows.length + " shown";
    }
    selects.forEach(function (s) { s.addEventListener("change", apply); });
    if (win) win.addEventListener("change", apply);
    refilter.push(apply);
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

  // queue: per-account status, kept in this browser only (localStorage) and exported in the config/status/ CSV format
  var KEY = "chase-workspace-status-v1";
  var EXPORT = { contacted: ["contacted", ""], meeting: ["meeting", ""], not_now: ["not_a_fit", "not now"] };
  function readStatus() { try { return JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { return {}; } }
  function writeStatus(m) { try { localStorage.setItem(KEY, JSON.stringify(m)); return true; } catch (e) { return false; } }
  var statusMap = readStatus();
  var stCounts = document.querySelector(".strip .st-counts");
  function countStatus() {
    if (!stCounts) return;
    var c = { contacted: 0, meeting: 0, not_now: 0 };
    document.querySelectorAll(".qrow").forEach(function (r) { if (c[r.dataset.status] != null) c[r.dataset.status]++; });
    var parts = [];
    if (c.contacted) parts.push("<b>" + c.contacted + "</b> contacted");
    if (c.meeting) parts.push("<b>" + c.meeting + "</b> meeting");
    if (c.not_now) parts.push("<b>" + c.not_now + "</b> not now");
    stCounts.innerHTML = parts.join(" · ");
  }
  document.querySelectorAll("select.status").forEach(function (sel) {
    var row = sel.closest(".qrow"), cid = sel.dataset.cid, saved = statusMap[cid];
    if (saved && EXPORT[saved.status]) { sel.value = saved.status; row.dataset.status = saved.status; }
    // a select inside <summary> must not toggle the row
    sel.addEventListener("click", function (e) { e.stopPropagation(); });
    sel.addEventListener("keydown", function (e) { e.stopPropagation(); });
    sel.addEventListener("change", function () {
      statusMap = readStatus();
      if (sel.value === "todo") delete statusMap[cid];
      else statusMap[cid] = { status: sel.value, company: sel.dataset.company, play: sel.dataset.play, date: new Date().toISOString().slice(0, 10) };
      row.dataset.status = sel.value;
      if (!writeStatus(statusMap)) toast("Could not save: browser storage is unavailable");
      countStatus();
      refilter.forEach(function (f) { f(); });
    });
  });
  document.querySelectorAll(".qrow>summary").forEach(function (s) {
    s.addEventListener("click", function (e) { if (e.target.closest(".c-status")) e.preventDefault(); });
  });
  countStatus();
  var exp = document.getElementById("export-status");
  if (exp) exp.addEventListener("click", function () {
    var m = readStatus(), ids = Object.keys(m).filter(function (k) { return EXPORT[m[k].status]; }).sort();
    if (!ids.length) return toast("No status set yet: everything is To do");
    var lines = ["company_id,company,status,reason,date,play"].concat(ids.map(function (k) {
      var x = m[k], ex = EXPORT[x.status];
      return [k, x.company, ex[0], ex[1], x.date, x.play].map(csvCell).join(",");
    }));
    download(lines.join("\n") + "\n", "accounts_status.csv");
    toast(ids.length + " status rows exported");
  });

  // queue: keyboard shortcuts (j / k move, Enter expand, c copy opener, ? help)
  var toastEl = document.getElementById("toast"), toastT;
  function toast(msg) {
    if (!toastEl) { toastEl = document.createElement("div"); toastEl.className = "toast"; toastEl.setAttribute("role", "status"); toastEl.hidden = true; document.body.appendChild(toastEl); }
    toastEl.textContent = msg; toastEl.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(function () { toastEl.hidden = true; }, 1600);
  }
  var help = document.getElementById("kbd-help");
  function toggleHelp(show) { if (help) help.hidden = show == null ? !help.hidden : !show; }
  document.querySelectorAll("[data-help]").forEach(function (b) { b.addEventListener("click", function () { toggleHelp(); }); });
  var list = document.getElementById("queue");
  function rowsVisible() { return list ? Array.prototype.filter.call(list.querySelectorAll(".qrow"), function (r) { return !r.hidden; }) : []; }
  function current() { return list ? list.querySelector(".qrow.cur") : null; }
  function setCurrent(r) {
    var c = current(); if (c) c.classList.remove("cur");
    if (!r) return;
    r.classList.add("cur");
    r.querySelector("summary").focus();
  }
  if (list) list.addEventListener("focusin", function (e) {
    var r = e.target.closest(".qrow");
    if (r && !r.classList.contains("cur")) { var c = current(); if (c) c.classList.remove("cur"); r.classList.add("cur"); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var t = e.target, tag = t && t.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable)) return;
    if (e.key === "?") { e.preventDefault(); return toggleHelp(); }
    if (e.key === "Escape") return toggleHelp(false);
    if (!list) return;
    var rows = rowsVisible(), i = rows.indexOf(current());
    if (e.key === "j" || e.key === "k") {
      e.preventDefault();
      if (!rows.length) return;
      i = i < 0 ? 0 : Math.max(0, Math.min(rows.length - 1, i + (e.key === "j" ? 1 : -1)));
      setCurrent(rows[i]);
    } else if (e.key === "Enter" && i >= 0 && t === document.body) {
      e.preventDefault(); rows[i].open = !rows[i].open;
    } else if (e.key === "c" && i >= 0) {
      var b = rows[i].querySelector("button.copy[data-copy]");
      if (b) { copy(b.getAttribute("data-copy"), b); toast("Opener copied: " + rows[i].querySelector(".c-co strong").textContent); }
    }
  });

  // top bar: theme toggle (remembered per browser) and account search ("/" focuses it)
  var root = document.documentElement, THEME_KEY = "chase-workspace-theme";
  function scheme() { return root.getAttribute("data-theme") || (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); }
  document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
    var label = function () { b.textContent = scheme() === "dark" ? "Light" : "Dark"; };
    label();
    b.addEventListener("click", function () {
      var next = scheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* not remembered */ }
      label();
    });
  });
  var search = document.getElementById("acct-search");
  function go() {
    if (!search) return false;
    var v = search.value.trim().toLowerCase(), opts = Array.prototype.slice.call(document.querySelectorAll("#acct-list option"));
    if (!v) return false;
    var hit = opts.filter(function (o) { return o.value.toLowerCase() === v; })[0] ||
              opts.filter(function (o) { return o.value.toLowerCase().indexOf(v) === 0; })[0] ||
              opts.filter(function (o) { return o.value.toLowerCase().indexOf(v) >= 0; })[0];
    if (!hit) { toast("No account matches \u201c" + search.value + "\u201d"); return false; }
    location.href = search.dataset.up + "accounts/" + hit.dataset.id + ".html";
    return true;
  }
  if (search) {
    search.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); go(); }
      if (e.key === "Escape") { search.value = ""; search.blur(); }
    });
    // picking an entry from the datalist fills the exact name: jump straight away
    search.addEventListener("input", function (e) {
      var v = search.value.toLowerCase();
      if (e.inputType === "insertReplacementText" || e.inputType == null) {
        if (Array.prototype.some.call(document.querySelectorAll("#acct-list option"), function (o) { return o.value.toLowerCase() === v; })) go();
      }
    });
    document.addEventListener("keydown", function (e) {
      var tag = e.target && e.target.tagName;
      if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey && tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
        e.preventDefault(); e.stopImmediatePropagation(); search.focus(); search.select();
      }
    }, true);
  }

  // dinner builder: invite status per city and account, kept in this browser, exported as dinner_attendees.csv
  var INV_KEY = "chase-workspace-invites-v1";
  function readInv() { try { return JSON.parse(localStorage.getItem(INV_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function writeInv(m) { try { localStorage.setItem(INV_KEY, JSON.stringify(m)); return true; } catch (e) { return false; } }
  document.querySelectorAll(".dinner").forEach(function (card) {
    var city = card.getAttribute("data-city"), inv = readInv();
    card.querySelectorAll("tr[data-row]").forEach(function (r) {
      var sel = r.querySelector("select.inv"), k = city + "|" + r.dataset.cid;
      if (!sel) return;
      if (inv[k]) { sel.value = inv[k].status; r.dataset.inv = inv[k].status; }
      sel.addEventListener("change", function () {
        var m = readInv();
        if (!sel.value) delete m[k]; else m[k] = { status: sel.value, city: city, account_name: r.dataset.company };
        r.dataset.inv = sel.value;
        if (!writeInv(m)) toast("Could not save: browser storage is unavailable");
      });
    });
    var b = card.querySelector('button[data-act="inv-export"]');
    if (b) b.addEventListener("click", function (e) {
      e.stopImmediatePropagation();
      var m = readInv(), keys = Object.keys(m).filter(function (k) { return m[k].city === city; });
      if (!keys.length) return toast("No invite status set for " + city + " yet");
      var date = card.getAttribute("data-date") || "";
      download(["city,date,account_name,status"].concat(keys.sort().map(function (k) {
        return [city, date, m[k].account_name, m[k].status].map(csvCell).join(",");
      })).join("\n") + "\n", "dinner_attendees_" + city + ".csv");
      toast(keys.length + " invite rows exported");
    });
  });
  function download(text, name) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" })); a.download = name;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  // dinner builder: select and copy
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
        if (act === "inv-export") return;
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
