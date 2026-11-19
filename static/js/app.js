/* Team Anesthesia - small progressive enhancements (works without JS too). */
(function () {
  "use strict";

  // Register the service worker (PWA / offline page).
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
    });
  }

  // "Install app": Android/desktop Chrome use the browser prompt; iPhone gets instructions.
  var installEls = document.querySelectorAll("[data-install-app]");
  var deferredPrompt = null;
  var standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
  function showInstall() { installEls.forEach(function (el) { el.classList.remove("d-none"); }); }
  function hideInstall() { installEls.forEach(function (el) { el.classList.add("d-none"); }); }
  if (!standalone) {
    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault();
      deferredPrompt = e;
      showInstall();
    });
    if (isIOS) showInstall();
  }
  window.addEventListener("appinstalled", hideInstall);
  installEls.forEach(function (el) {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.finally(function () { deferredPrompt = null; hideInstall(); });
      } else {
        var help = document.getElementById("install-help");
        if (help) help.classList.toggle("d-none");
        else alert("To install: tap the Share button, then 'Add to Home Screen'.");
      }
    });
  });

  // --- Back button -------------------------------------------------------------
  // Forms remember which page they were opened from (see core/backnav.py), so after
  // saving the app steps back to it and Back keeps working like on a normal website.
  var here = location.pathname + location.search;
  var cameFrom = "";
  if (document.referrer && document.referrer.indexOf(location.origin + "/") === 0) {
    var r = new URL(document.referrer);
    cameFrom = r.pathname + r.search;
  }
  document.querySelectorAll("input[data-back-field]").forEach(function (f) {
    var parts = (f.value || "").split("|");
    if (parts.length === 3 && /^\d+$/.test(parts[0])) {
      f.value = (parseInt(parts[0], 10) + 1) + "|" + parts[1] + "|" + parts[2];  // shown again after an error
    } else {
      f.value = "0|" + here + "|" + cameFrom;
    }
  });
  // A page restored from the phone's memory may be out of date: reload it.
  window.addEventListener("pageshow", function (e) { if (e.persisted) location.reload(); });
  // The app's back arrow works like the phone's Back button when there is a page to go back to.
  document.querySelectorAll("[data-back]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      if (cameFrom && history.length > 1) {
        e.preventDefault();
        history.back();
      }
    });
  });

  var fee = document.getElementById("id_fee");

  // "Payment already received" switch reveals amount + mode.
  var paidNow = document.getElementById("id_paid_now");
  var paidBox = document.getElementById("paid-now-fields");
  if (paidNow && paidBox) {
    var sync = function () {
      paidBox.classList.toggle("d-none", !paidNow.checked);
      var amount = document.getElementById("id_paid_amount");
      if (paidNow.checked && amount && !amount.value && fee) amount.placeholder = fee.value || "Amount";
    };
    paidNow.addEventListener("change", sync);
    sync();
  }

  // Auto-hide success messages.
  document.querySelectorAll(".toast-stack .alert-success, .toast-stack .alert-info").forEach(function (el) {
    setTimeout(function () {
      if (window.bootstrap) bootstrap.Alert.getOrCreateInstance(el).close();
    }, 3500);
  });

  // Confirm dangerous actions.
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      if (!window.confirm(el.getAttribute("data-confirm"))) e.preventDefault();
    });
  });
})();

/* "Pick from phone contacts": fills name + mobile from the phone's address book.
 * Uses the Contact Picker API (Chrome on Android, HTTPS). The button is always shown;
 * when something stops it from working, a short note under the button says why and
 * what to do (other browser, iPhone, contacts permission), instead of failing silently.
 * Markup: <button data-contact-pick data-name="#id_name" data-phone="#id_phone" hidden>
 */
(function () {
  "use strict";
  var ua = navigator.userAgent || "";
  var isIOS = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  var isAndroid = /Android/i.test(ua);
  var inAppBrowser = /; wv\)|FBAN|FBAV|Instagram|WhatsApp|GSA\//i.test(ua);
  var supported = "contacts" in navigator && "ContactsManager" in window &&
                  typeof navigator.contacts.select === "function";
  var PERMISSION_STEPS = "Allow Contacts for Chrome: phone <b>Settings &gt; Apps &gt; Chrome &gt; Permissions &gt; " +
    "Contacts &gt; Allow</b>. Then close the app fully, open it again and try once more.";

  function why() {
    if (isIOS) return "iPhone does not let web apps read your contacts (Apple's rule). Please type the name and number.";
    if (inAppBrowser) return "This page is open inside another app (e.g. WhatsApp/Gmail). Open the link in <b>Chrome</b>, or use the installed app.";
    if (isAndroid) return "This browser cannot open your contacts. Please open the app in <b>Chrome</b> (Samsung Internet and others do not support it).";
    if (!window.isSecureContext) return "Contacts can only be opened on the https:// address of the app.";
    return "Picking contacts works on Android phones in Chrome. Please type the name and number.";
  }

  document.querySelectorAll("[data-contact-pick]").forEach(function (btn) {
    btn.hidden = false;
    var note = document.createElement("div");
    note.className = "small text-muted mb-2 d-none";
    btn.insertAdjacentElement("afterend", note);
    function say(html) { note.innerHTML = html; note.classList.remove("d-none"); }

    btn.addEventListener("click", function () {
      note.classList.add("d-none");
      if (!supported) { say(why()); return; }
      var picking;
      try {
        picking = navigator.contacts.select(["name", "tel"], { multiple: false });
      } catch (err) {
        say("Could not open contacts (" + (err && err.name || "error") + "). " + PERMISSION_STEPS);
        return;
      }
      picking.then(function (picked) {
        if (!picked || !picked.length) {
          // Closing the list without choosing gives the same empty result as a blocked permission.
          say("No contact was chosen. If your contacts list did not open at all: " + PERMISSION_STEPS);
          return;
        }
        var c = picked[0];
        var name = document.querySelector(btn.dataset.name);
        var phone = document.querySelector(btn.dataset.phone);
        if (name && c.name && c.name.length) name.value = c.name[0];
        if (phone) {
          if (c.tel && c.tel.length) phone.value = c.tel[0].replace(/[^\d+]/g, "").slice(0, 20);
          else say("This contact has no phone number saved. Please type the number.");
        }
        [name, phone].forEach(function (el) { if (el) el.dispatchEvent(new Event("input", { bubbles: true })); });
      }).catch(function (err) {
        if (err && err.name === "InvalidStateError") return;  // the list is already open
        say("Could not open contacts (" + (err && err.name || "error") + "). " + PERMISSION_STEPS);
      });
    });
  });
})();
