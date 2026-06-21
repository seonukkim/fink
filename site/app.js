"use strict";

function currentLang() {
  return document.body.classList.contains("lang-ko") ? "ko" : "en";
}

function applyLang(next) {
  const lang = next === "ko" ? "ko" : "en";
  document.documentElement.lang = lang;
  document.body.classList.toggle("lang-ko", lang === "ko");
  document.body.classList.toggle("lang-en", lang === "en");
  for (const el of document.querySelectorAll("[data-en]")) {
    const value = el.dataset[lang];
    if (value !== undefined) el.textContent = value;
  }
  for (const btn of document.querySelectorAll(".lang-switch button")) {
    btn.classList.toggle("is-active", btn.dataset.lang === lang);
  }
  try {
    localStorage.setItem("fink-lang", lang);
  } catch (err) {
    /* storage unavailable: ignore */
  }
}

async function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (err) {
    /* fall through to the legacy path */
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "absolute";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok;
  } catch (err) {
    return false;
  }
}

function initCopyButtons() {
  for (const btn of document.querySelectorAll(".copy-btn")) {
    btn.addEventListener("click", async () => {
      const target = document.querySelector(btn.dataset.copy);
      if (!target) return;
      const ok = await copyText(target.textContent.trim());
      const lang = currentLang();
      btn.textContent = ok
        ? (lang === "ko" ? "복사됨" : "Copied")
        : (lang === "ko" ? "복사 실패" : "Copy failed");
      btn.classList.add("is-done");
      window.setTimeout(() => {
        btn.classList.remove("is-done");
        const label = btn.dataset[lang];
        if (label !== undefined) btn.textContent = label;
      }, 1600);
    });
  }
}

function init() {
  let saved = "en";
  try {
    saved = localStorage.getItem("fink-lang") || "en";
  } catch (err) {
    saved = "en";
  }
  for (const btn of document.querySelectorAll(".lang-switch button")) {
    btn.addEventListener("click", () => applyLang(btn.dataset.lang));
  }
  initCopyButtons();
  applyLang(saved);
}

init();
