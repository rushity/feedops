/**
 * FeedOps Frontend Interactions
 * Owner: Dhruv (Dashboard & Frontend Lead)
 * Vanilla JS only - zero external dependencies.
 */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Feed Refresh Form Protection: Prevent accidental duplicate clicks & show loading spinner
  const refreshForms = document.querySelectorAll(".refresh-form");
  refreshForms.forEach((form) => {
    form.addEventListener("submit", (e) => {
      const btn = form.querySelector(".refresh-btn");
      if (!btn) return;

      if (btn.classList.contains("is-loading") || btn.disabled) {
        e.preventDefault();
        return false;
      }

      // Lock button to prevent double-submit
      btn.disabled = true;
      btn.classList.add("is-loading");
      btn.setAttribute("aria-busy", "true");

      const icon = btn.querySelector(".refresh-icon");
      if (icon) {
        icon.classList.add("spin-animation");
      }

      const textSpan = btn.querySelector(".btn-text");
      if (textSpan) {
        textSpan.textContent = "Refreshing...";
      }

      // Proactively submit the form natively
      form.submit();
    });
  });

  // 2. Add Feed Form: Client-side validation enhancement
  const addFeedForm = document.getElementById("feed-add-form");
  if (addFeedForm) {
    const urlInput = document.getElementById("feed-url");
    const urlError = document.getElementById("feed-url-error");
    const submitBtn = document.getElementById("btn-add-feed-submit");

    const validateUrl = () => {
      if (!urlInput || !urlError) return true;
      const val = urlInput.value.trim();

      if (!val) {
        urlInput.classList.add("is-invalid");
        urlError.textContent = "Feed URL is required.";
        urlError.style.display = "block";
        return false;
      }

      if (!/^https?:\/\/.+/i.test(val)) {
        urlInput.classList.add("is-invalid");
        urlError.textContent = "Feed URL must start with http:// or https://";
        urlError.style.display = "block";
        return false;
      }

      urlInput.classList.remove("is-invalid");
      urlError.textContent = "";
      urlError.style.display = "none";
      return true;
    };

    if (urlInput) {
      urlInput.addEventListener("input", () => {
        if (urlInput.classList.contains("is-invalid")) {
          validateUrl();
        }
      });
    }

    addFeedForm.addEventListener("submit", (e) => {
      if (!validateUrl()) {
        e.preventDefault();
        if (urlInput) urlInput.focus();
        return false;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.classList.add("is-loading");
        const btnText = submitBtn.querySelector("span") || submitBtn;
        if (btnText && btnText !== submitBtn) {
          btnText.textContent = "Adding...";
        }
      }
    });
  }

  // 3. Dismissible Alert Banners
  const dismissButtons = document.querySelectorAll(".alert-dismiss");
  dismissButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const alert = btn.closest(".alert");
      if (alert) {
        alert.style.transition = "opacity 0.2s ease, transform 0.2s ease";
        alert.style.opacity = "0";
        alert.style.transform = "translateY(-4px)";
        setTimeout(() => {
          alert.remove();
        }, 200);
      }
    });
  });

  // 4. Safe Relative / Local Time Formatting for Timestamps
  const timeElements = document.querySelectorAll("time[data-timestamp]");
  timeElements.forEach((el) => {
    const raw = el.getAttribute("data-timestamp");
    if (!raw) return;

    try {
      const date = new Date(raw);
      if (!isNaN(date.getTime())) {
        // Keep precise UTC/ISO string in title for screen readers / tooltips
        el.setAttribute("title", date.toUTCString());
      }
    } catch (_) {
      // Keep original text on any parsing failure
    }
  });
});
