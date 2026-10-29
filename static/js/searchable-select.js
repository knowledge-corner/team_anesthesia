/* Searchable select ("type to search").
 *
 * Local mode:   <select data-searchable> - filters the select's own options.
 * Remote mode:  <select data-searchable data-search-url="/hospitals/search/"> - asks the
 *               server as you type (for long lists like the hospital directory). The
 *               endpoint returns {"results": [{"id", "label", "sub", "mine"}]}.
 *               Optional data-add-url shows a "+ Add ... not in the list" link.
 *
 * The original <select> stays in the form (hidden), so form posts, validation and
 * "change" listeners keep working. Local options are read afresh on every search, so a
 * page may rebuild them (optgroup labels become group headings); after changing the
 * options or the value from code, dispatch an "options-changed" event on the select. Matching is "contains", every typed word must
 * appear somewhere ("ruby cl" finds "Ruby Hall Clinic").
 */
(function () {
  "use strict";

  function normalise(text) {
    return (text || "").toLowerCase().replace(/[^a-z0-9ऀ-ॿ]+/g, " ").trim();
  }

  function escapeHtml(text) {
    return String(text || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function highlight(label, tokens) {
    var html = escapeHtml(label);
    tokens.forEach(function (token) {
      if (!token) return;
      var re = new RegExp("(" + token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
      html = html.replace(re, "<mark>$1</mark>");
    });
    return html;
  }

  function enhance(select) {
    if (select.dataset.searchableReady) return;
    select.dataset.searchableReady = "1";
    var remoteUrl = select.dataset.searchUrl || "";
    var addUrl = select.dataset.addUrl || "";
    var emptyOption = Array.prototype.find.call(select.options, function (o) { return o.value === ""; });
    var emptyLabel = emptyOption && /all /i.test(emptyOption.text) ? emptyOption.text : "";

    var wrapper = document.createElement("div");
    wrapper.className = "combo";
    var input = document.createElement("input");
    input.type = "text";
    input.className = "form-control combo-input" + (select.classList.contains("form-select-sm") ? " form-control-sm" : "");
    input.autocomplete = "off";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-autocomplete", "list");
    input.placeholder = select.dataset.placeholder || "Type to search";
    if (select.id) {
      input.id = select.id + "_search";
      var label = document.querySelector('label[for="' + select.id + '"]');
      if (label) label.setAttribute("for", input.id);
    }
    var caret = document.createElement("i");
    caret.className = "bi bi-search combo-caret";
    var menu = document.createElement("div");
    menu.className = "combo-menu";
    menu.setAttribute("role", "listbox");

    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(input);
    wrapper.appendChild(caret);
    wrapper.appendChild(menu);
    wrapper.appendChild(select);
    select.classList.add("d-none");
    select.tabIndex = -1;

    function localOptions() {
      return Array.prototype.map.call(select.options, function (o) {
        var group = o.parentNode && o.parentNode.tagName === "OPTGROUP" ? o.parentNode.label : "";
        return { value: o.value, label: o.text, sub: "", group: group, key: normalise(o.text), empty: o.value === "" };
      });
    }
    var visible = [];
    var active = -1;
    var timer = null;
    var requestNo = 0;

    function selectedLabel() {
      var opt = select.options[select.selectedIndex];
      return opt && opt.value !== "" ? opt.text : "";
    }

    function paint(items, tokens, query, loading) {
      visible = items;
      var lastGroup = "";
      var html = items.map(function (o, i) {
        var head = "";
        if (o.group && o.group !== lastGroup) head = '<div class="combo-group">' + escapeHtml(o.group) + "</div>";
        lastGroup = o.group || lastGroup;
        var cls = "combo-item" + (o.value === select.value ? " selected" : "") + (o.empty ? " text-muted" : "");
        var sub = o.sub ? '<div class="combo-sub">' + escapeHtml(o.sub) + "</div>" : "";
        var badge = o.mine ? '<span class="combo-mine">Mine</span>' : "";
        return head + '<div class="' + cls + '" role="option" data-index="' + i + '"><div class="d-flex justify-content-between gap-2"><span>' +
          highlight(o.label, tokens) + "</span>" + badge + "</div>" + sub + "</div>";
      }).join("");
      if (loading) html += '<div class="combo-empty">Searching...</div>';
      else if (!items.length) html += '<div class="combo-empty">No match for "' + escapeHtml(query) + '"</div>';
      if (addUrl) {
        var sep = addUrl.indexOf("?") === -1 ? "?" : "&";
        html += '<a class="combo-add" href="' + addUrl + sep + "name=" + encodeURIComponent(query || "") + '"><i class="bi bi-plus-circle"></i> Add a hospital not in the list</a>';
      }
      menu.innerHTML = html;
      active = items.length ? 0 : -1;
      paintActive();
    }

    function render(query) {
      var tokens = normalise(query).split(" ").filter(Boolean);
      if (!remoteUrl) {
        paint(localOptions().filter(function (o) {
          if (o.empty) return tokens.length === 0;
          return tokens.every(function (t) { return o.key.indexOf(t) !== -1; });
        }), tokens, query);
        return;
      }
      var head = emptyLabel && !tokens.length ? [{ value: "", label: emptyLabel, empty: true }] : [];
      paint(head, tokens, query, true);
      clearTimeout(timer);
      var mine = ++requestNo;
      timer = setTimeout(function () {
        fetch(remoteUrl + (remoteUrl.indexOf("?") === -1 ? "?" : "&") + "q=" + encodeURIComponent(query), { credentials: "same-origin" })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (mine !== requestNo) return; // a newer search is running
            var items = head.concat((data.results || []).map(function (r) {
              return { value: String(r.id), label: r.label, sub: r.sub, mine: r.mine, group: r.group || "" };
            }));
            paint(items, tokens, query);
          })
          .catch(function () { if (mine === requestNo) paint(head, tokens, query); });
      }, query ? 220 : 0);
    }

    function paintActive() {
      var items = menu.querySelectorAll(".combo-item");
      items.forEach(function (el, i) { el.classList.toggle("active", i === active); });
      if (items[active]) items[active].scrollIntoView({ block: "nearest" });
    }

    function open() { wrapper.classList.add("open"); input.setAttribute("aria-expanded", "true"); }
    function close() { wrapper.classList.remove("open"); input.setAttribute("aria-expanded", "false"); }

    function choose(option) {
      if (remoteUrl && option.value && !Array.prototype.some.call(select.options, function (o) { return o.value === option.value; })) {
        var opt = document.createElement("option");
        opt.value = option.value;
        opt.text = option.sub ? option.label + " - " + option.sub : option.label;
        select.appendChild(opt);
      }
      var changed = select.value !== option.value;
      select.value = option.value;
      input.value = option.empty ? "" : selectedLabel();
      close();
      if (changed) select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    input.value = selectedLabel();

    input.addEventListener("focus", function () { input.select(); render(""); open(); });
    input.addEventListener("input", function () { render(input.value); open(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (!wrapper.classList.contains("open")) { render(input.value); open(); }
        active = Math.min(active + 1, visible.length - 1);
        paintActive();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        active = Math.max(active - 1, 0);
        paintActive();
      } else if (e.key === "Enter") {
        if (wrapper.classList.contains("open") && visible[active]) {
          e.preventDefault();
          choose(visible[active]);
        }
      } else if (e.key === "Escape") {
        input.value = selectedLabel();
        close();
      }
    });
    menu.addEventListener("mousedown", function (e) {
      if (e.target.closest(".combo-add")) return; // normal link
      var item = e.target.closest(".combo-item");
      if (!item) return;
      e.preventDefault();
      choose(visible[parseInt(item.dataset.index, 10)]);
    });
    input.addEventListener("blur", function () {
      setTimeout(function () {
        if (!wrapper.classList.contains("open")) return;
        var typed = normalise(input.value);
        var exact = visible.filter(function (o) { return !o.empty && normalise(o.label) === typed; });
        if (exact.length === 1) {
          choose(exact[0]);
        } else if (!typed && emptyOption) {
          choose({ value: "", label: "", empty: true });
        } else {
          input.value = selectedLabel();
          close();
        }
      }, 150);
    });
    select.addEventListener("change", function () {
      if (document.activeElement !== input) input.value = selectedLabel();
    });
    select.addEventListener("options-changed", function () {
      if (document.activeElement !== input) input.value = selectedLabel();
    });
  }

  document.querySelectorAll("select[data-searchable]").forEach(enhance);
  window.enhanceSearchableSelect = enhance;
})();
