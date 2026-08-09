/* GreatAPI admin behaviour.
 *
 * Deliberately tiny and dependency-free. Loaded synchronously in <head> so the
 * saved theme is applied before first paint -- deferring it would show a flash
 * of the wrong colour scheme on every navigation.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "greatapi-theme";

  /* Runs immediately, before <body> exists. */
  try {
    var saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark") {
      document.documentElement.setAttribute("data-theme", saved);
    }
  } catch (err) {
    /* Private mode or blocked storage: fall back to the OS preference. */
  }

  function currentTheme() {
    var explicit = document.documentElement.getAttribute("data-theme");
    if (explicit) return explicit;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function syncToggles(theme) {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(theme === "dark"));
      var label = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
    });
  }

  /* Only an explicit click is stored. Persisting the auto-detected theme on
     first load would pin the admin to whatever the OS happened to prefer that
     day, and later OS changes would be ignored. */
  function chooseTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (err) {
      /* Not fatal: the choice just will not persist. */
    }
    syncToggles(theme);
  }

  function initTheme() {
    syncToggles(currentTheme());
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        chooseTheme(currentTheme() === "dark" ? "light" : "dark");
      });
    });

    /* Follow the OS while the user has not chosen for themselves. */
    var media = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function () {
      var stored = null;
      try {
        stored = localStorage.getItem(STORAGE_KEY);
      } catch (err) {
        /* ignore */
      }
      if (stored !== "light" && stored !== "dark") {
        syncToggles(media.matches ? "dark" : "light");
      }
    };
    if (media.addEventListener) media.addEventListener("change", onChange);
  }

  function initSidebar() {
    var sidebar = document.querySelector("[data-sidebar]");
    var toggle = document.querySelector("[data-menu-toggle]");
    if (!sidebar || !toggle) return;

    function setOpen(open) {
      sidebar.setAttribute("data-open", String(open));
      toggle.setAttribute("aria-expanded", String(open));
      var scrim = document.querySelector(".scrim");
      if (open && !scrim) {
        scrim = document.createElement("div");
        scrim.className = "scrim";
        scrim.addEventListener("click", function () {
          setOpen(false);
        });
        document.body.appendChild(scrim);
      } else if (!open && scrim) {
        scrim.remove();
      }
    }

    toggle.addEventListener("click", function () {
      setOpen(sidebar.getAttribute("data-open") !== "true");
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") setOpen(false);
    });
  }

  /* Any control that changes state irreversibly asks first. */
  function initConfirms() {
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!window.confirm(form.getAttribute("data-confirm"))) {
          event.preventDefault();
        }
      });
    });
  }

  function initCopyButtons() {
    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        var target = document.querySelector(button.getAttribute("data-copy"));
        if (!target) return;
        var text = target.textContent.trim();
        var done = function () {
          var original = button.textContent;
          button.textContent = "Copied";
          setTimeout(function () {
            button.textContent = original;
          }, 1400);
        };
        if (navigator.clipboard) {
          navigator.clipboard.writeText(text).then(done, function () {});
        }
      });
    });
  }

  /* Submit the search box on Enter without needing a visible button. */
  function initSearch() {
    document.querySelectorAll("[data-autosubmit]").forEach(function (input) {
      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && input.form) {
          event.preventDefault();
          input.form.submit();
        }
      });
    });
  }

  /* Filter dropdowns apply on change. Wired here rather than with an inline
     `onchange`, which the admin's Content-Security-Policy blocks. */
  function initFilters() {
    document
      .querySelectorAll("select[data-autosubmit-select]")
      .forEach(function (select) {
        select.addEventListener("change", function () {
          if (select.form) select.form.submit();
        });
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTheme();
    initSidebar();
    initConfirms();
    initCopyButtons();
    initSearch();
    initFilters();
  });
})();
