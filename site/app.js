"use strict";

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
  applyLang(saved);
}

init();
