// Chase Index workspace: lists, side panel, status, shortcuts, search, dinner copy. No network calls.
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // ---------------------------------------------------------------- helpers
  var toastEl = $("#toast"), toastT;
  function toast(msg) {
    if (!toastEl) { toastEl = document.createElement("div"); toastEl.className = "toast"; toastEl.setAttribute("role", "status"); document.body.appendChild(toastEl); }
    toastEl.textContent = msg; toastEl.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(function () { toastEl.hidden = true; }, 1600);
  }
  function csvCell(v) { v = String(v == null ? "" : v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
  function fallback(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) { /* clipboard unavailable */ }
    document.body.removeChild(ta);
  }
  function copy(text, btn) {
    var done = function () { if (!btn) return; var t = btn.textContent; btn.textContent = "Copied"; setTimeout(function () { btn.textContent = t; }, 1200); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(text); done(); });
    } else { fallback(text); done(); }
  }
  function download(text, name) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" })); a.download = name;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }
  function store(key, val) {
    try { if (val === undefined) return JSON.parse(localStorage.getItem(key) || "{}") || {}; localStorage.setItem(key, JSON.stringify(val)); return true; }
    catch (e) { return val === undefined ? {} : false; }
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("button.copy[data-copy]");
    if (b) { e.stopPropagation(); copy(b.getAttribute("data-copy"), b); }
  });

  // ---------------------------------------------------------------- filters (trigger feed): <div class="filters" data-target="#x">
  $$(".filters").forEach(function (box) {
    var target = $(box.getAttribute("data-target"));
    if (!target) return;
    var selects = $$("select[data-filter]", box), win = $("select[data-window]", box), count = $(".count", box);
    function isoDay(offset) { var d = new Date(); d.setDate(d.getDate() + offset); return d.toISOString().slice(0, 10); }
    function apply() {
      var rows = $$("[data-frow]", target), n = 0, today = isoDay(0), from = win && /^\d+$/.test(win.value) ? isoDay(-Number(win.value)) : null;
      rows.forEach(function (r) {
        var ok = true;
        selects.forEach(function (s) {
          var v = r.getAttribute("data-" + s.getAttribute("data-filter"));
          if (s.value && v !== s.value) ok = false;
          if (!s.value && s.dataset.hideOnAll && v === s.dataset.hideOnAll) ok = false;   // "All" can still leave one type out
        });
        if (win && win.value) {
          var dt = r.getAttribute("data-date") || "";
          if (win.value === "up" ? dt <= today : (dt < from || dt > today)) ok = false;
        }
        r.hidden = !ok; if (ok) n++;
      });
      $$("section.tsec", target).forEach(function (s) {
        var vis = $$("[data-frow]", s).filter(function (r) { return !r.hidden; }).length, c = $(".tgroup .faint", s);
        s.hidden = !vis; if (c) c.textContent = vis;
      });
      if (count) count.textContent = n + " of " + rows.length;
    }
    selects.concat(win ? [win] : []).forEach(function (s) { s.addEventListener("change", apply); });
    apply();
  });

  // ---------------------------------------------------------------- side panel: rows with a <template class="detail">
  var panel = $("#panel"), pbody = panel && $(".pbody", panel), current = null;
  function rows() { return $$("[data-list] [data-frow]").filter(function (r) { return !r.hidden && r.offsetParent !== null; }); }
  function mark(r) { $$(".cur").forEach(function (x) { x.classList.remove("cur"); }); if (r) r.classList.add("cur"); current = r; }
  function openPanel(r) {
    if (!panel || !r) return;
    var t = $("template.detail", r);
    if (!t) return;
    pbody.innerHTML = ""; pbody.appendChild(t.content.cloneNode(true));
    panel.hidden = false; panel.scrollTop = 0; mark(r);
  }
  function closePanel() { if (panel && !panel.hidden) { panel.hidden = true; if (current) current.focus(); } }
  if (panel) {
    $(".pclose", panel).addEventListener("click", closePanel);
    $$("[data-list] [data-frow]").forEach(function (r) {
      r.addEventListener("click", function (e) {
        if (e.target.closest("button, a, input, select, label")) return;
        openPanel(r);
      });
      r.addEventListener("focus", function () { mark(r); });
    });
  }

  // ---------------------------------------------------------------- queue: tabs, status pills, export
  var list = $("#queue");
  if (list) {
    $$(".tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        $$(".tab").forEach(function (t) { t.setAttribute("aria-selected", t === tab ? "true" : "false"); });
        var k = tab.dataset.tab;
        $$(".qrow", list).forEach(function (r) {
          r.hidden = !(k === "all" || (k === "dinner" ? r.dataset.play === "dinner_invite" : r.dataset.contact === k));
        });
        if (current && current.hidden) { closePanel(); mark(null); }
      });
    });
  }
  var STATUS_KEY = "chase-workspace-status-v1";
  var CYCLE = ["todo", "contacted", "meeting", "not_now"], LABEL = { todo: "To do", contacted: "Contacted", meeting: "Meeting", not_now: "Not now" };
  var EXPORT = { contacted: ["contacted", ""], meeting: ["meeting", ""], not_now: ["not_a_fit", "not now"] };
  function paintStatus(b, s) { b.dataset.status = s; b.textContent = LABEL[s]; var r = b.closest(".qrow"); if (r) r.dataset.status = s; }
  var saved = store(STATUS_KEY);
  $$("button.spill").forEach(function (b) {
    var x = saved[b.dataset.cid];
    if (x && EXPORT[x.status]) paintStatus(b, x.status);
    b.addEventListener("click", function (e) {
      e.stopPropagation();
      var next = CYCLE[(CYCLE.indexOf(b.dataset.status) + 1) % CYCLE.length], m = store(STATUS_KEY);
      if (next === "todo") delete m[b.dataset.cid];
      else m[b.dataset.cid] = { status: next, company: b.dataset.company, play: b.dataset.play, date: new Date().toISOString().slice(0, 10) };
      paintStatus(b, next);
      if (!store(STATUS_KEY, m)) toast("Could not save: browser storage is unavailable");
    });
  });
  var exp = $("#export-status");
  if (exp) exp.addEventListener("click", function () {
    var m = store(STATUS_KEY), ids = Object.keys(m).filter(function (k) { return EXPORT[m[k].status]; }).sort();
    if (!ids.length) return toast("No status set yet: everything is To do");
    download(["company_id,company,status,reason,date,play"].concat(ids.map(function (k) {
      var x = m[k], ex = EXPORT[x.status];
      return [k, x.company, ex[0], ex[1], x.date, x.play].map(csvCell).join(",");
    })).join("\n") + "\n", "accounts_status.csv");
    toast(ids.length + " status rows exported");
  });

  // ---------------------------------------------------------------- keyboard: j / k move, Enter opens, c copies, Esc closes, ? help
  var help = $("#kbd-help");
  function toggleHelp(show) { if (help) help.hidden = show == null ? !help.hidden : !show; }
  $$("[data-help]").forEach(function (b) { b.addEventListener("click", function () { toggleHelp(); }); });
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var t = e.target, tag = t && t.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable)) return;
    if (e.key === "?") { e.preventDefault(); return toggleHelp(); }
    if (e.key === "Escape") { toggleHelp(false); return closePanel(); }
    var rs = rows(), i = rs.indexOf(current);
    if (!rs.length) return;
    if (e.key === "j" || e.key === "k") {
      e.preventDefault();
      i = i < 0 ? 0 : Math.max(0, Math.min(rs.length - 1, i + (e.key === "j" ? 1 : -1)));
      rs[i].focus(); mark(rs[i]);
      if (panel && !panel.hidden) openPanel(rs[i]);
    } else if (e.key === "Enter" && i >= 0 && (t === rs[i] || t === document.body)) {
      e.preventDefault(); openPanel(rs[i]);
    } else if (e.key === "c" && i >= 0) {
      var tpl = $("template.detail", rs[i]), b = tpl && tpl.content.querySelector("button.copy[data-copy]");
      if (b) { copy(b.getAttribute("data-copy"), null); toast("Copied: " + (($(".co-n b", rs[i]) || {}).textContent || "")); }
    }
  });

  // ---------------------------------------------------------------- top bar: theme switch and account search ("/" focuses)
  var root = document.documentElement, THEME_KEY = "chase-workspace-theme";
  function scheme() { return root.getAttribute("data-theme") || (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); }
  $$("[data-theme-toggle]").forEach(function (b) {
    var label = function () { b.textContent = scheme() === "dark" ? "Light" : "Dark"; };
    label();
    b.addEventListener("click", function () {
      var next = scheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* not remembered */ }
      label();
    });
  });
  var search = $("#acct-search");
  function go() {
    var v = search.value.trim().toLowerCase(), opts = $$("#acct-list option");
    if (!v) return;
    var hit = opts.filter(function (o) { return o.value.toLowerCase() === v; })[0] ||
              opts.filter(function (o) { return o.value.toLowerCase().indexOf(v) === 0; })[0] ||
              opts.filter(function (o) { return o.value.toLowerCase().indexOf(v) >= 0; })[0];
    if (!hit) return toast("No account matches “" + search.value + "”");
    location.href = search.dataset.up + "accounts/" + hit.dataset.id + ".html";
  }
  if (search) {
    search.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); go(); }
      if (e.key === "Escape") { search.value = ""; search.blur(); }
    });
    search.addEventListener("input", function (e) {   // picking a datalist entry fills the exact name: jump straight away
      var v = search.value.toLowerCase();
      if ((e.inputType === "insertReplacementText" || e.inputType == null) && $$("#acct-list option").some(function (o) { return o.value.toLowerCase() === v; })) go();
    });
    document.addEventListener("keydown", function (e) {
      var tag = e.target && e.target.tagName;
      if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey && tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
        e.preventDefault(); e.stopImmediatePropagation(); search.focus(); search.select();
      }
    }, true);
  }

  // ---------------------------------------------------------------- dinner builder: select, copy, invite status (localStorage) and export
  var INV_KEY = "chase-workspace-invites-v1";
  var INV = ["", "invited", "accepted", "declined"], INV_LABEL = { "": "To invite", invited: "Invited", accepted: "Confirmed", declined: "Declined" };
  $$(".dinner").forEach(function (card) {
    var city = card.getAttribute("data-city"), date = card.getAttribute("data-date") || "";
    var rs = $$("tr[data-row]", card), count = $(".count", card), inv = store(INV_KEY);
    function picked() { return rs.filter(function (r) { return $("input", r).checked; }); }
    function refresh() {
      rs.forEach(function (r) { r.classList.toggle("off", !$("input", r).checked); });
      if (count) count.textContent = picked().length + " of " + rs.length + " selected";
    }
    rs.forEach(function (r) {
      $("input", r).addEventListener("change", refresh);
      var b = $("button.ipill", r), k = city + "|" + r.dataset.cid;
      var paint = function (s) { b.dataset.inv = s; r.dataset.inv = s; b.textContent = INV_LABEL[s]; };
      if (inv[k] && INV_LABEL[inv[k].status]) paint(inv[k].status);
      b.addEventListener("click", function (e) {
        e.stopPropagation();
        var next = INV[(INV.indexOf(b.dataset.inv || "") + 1) % INV.length], m = store(INV_KEY);
        if (!next) delete m[k]; else m[k] = { status: next, city: city, account_name: r.dataset.company };
        paint(next);
        if (!store(INV_KEY, m)) toast("Could not save: browser storage is unavailable");
      });
    });
    $$("button[data-act]", card).forEach(function (b) {
      b.addEventListener("click", function () {
        var act = b.getAttribute("data-act");
        if (act === "all" || act === "none") { rs.forEach(function (r) { $("input", r).checked = act === "all"; }); return refresh(); }
        if (act === "inv-export") {
          var m = store(INV_KEY), keys = Object.keys(m).filter(function (k) { return m[k].city === city; }).sort();
          if (!keys.length) return toast("No invite status set for " + city + " yet");
          download(["city,date,account_name,status"].concat(keys.map(function (k) {
            return [city, date, m[k].account_name, m[k].status].map(csvCell).join(",");
          })).join("\n") + "\n", "dinner_attendees_" + city + ".csv");
          return toast(keys.length + " invite rows exported");
        }
        var sel = picked(), when = date || "date tbc", text;
        if (act === "csv") {
          text = ["city,date,company,tier,hq_city,local_link,hook,source_url"].concat(sel.map(function (r) {
            return [city, when, r.dataset.company, r.dataset.tier, r.dataset.hq, r.dataset.local, r.dataset.hook, r.dataset.source].map(csvCell).join(",");
          })).join("\n");
        } else {
          text = city.charAt(0).toUpperCase() + city.slice(1) + " dinner (" + when + "), " + sel.length + " accounts\n\n" +
            sel.map(function (r, i) { return (i + 1) + ". " + r.dataset.company + " (T" + r.dataset.tier + ", " + (r.dataset.hq || "HQ unknown") + ")\n   " + r.dataset.hook + "\n   Source: " + r.dataset.source; }).join("\n\n");
        }
        copy(text, b);
      });
    });
    refresh();
  });
})();
