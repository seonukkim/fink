"use strict";

const snapshot = JSON.parse(document.getElementById("ledger-snapshot").textContent);

const I18N = {
  en: {
    rowsZero: "No measured rows",
    rows: (n) => `${n} measured row${n === 1 ? "" : "s"}`,
    emptyResults:
      "No measured result rows exist in RESULT_LEDGER.csv yet. This page does not claim metric values.",
    emptyFigures: "No project-page figure rows are registered.",
  },
  ko: {
    rowsZero: "측정 행 없음",
    rows: (n) => `측정 행 ${n}개`,
    emptyResults:
      "RESULT_LEDGER.csv에 측정된 결과 행이 아직 없습니다. 이 페이지는 지표 값을 주장하지 않습니다.",
    emptyFigures: "등록된 프로젝트 페이지 그림 행이 없습니다.",
  },
};

let lang = "en";

function text(value, fallback = "not recorded") {
  if (value === null || value === undefined) return fallback;
  const cleaned = String(value).trim();
  return cleaned.length > 0 ? cleaned : fallback;
}

function td(value) {
  const cell = document.createElement("td");
  cell.textContent = text(value);
  return cell;
}

function statusCell(value) {
  const cell = document.createElement("td");
  const pill = document.createElement("span");
  pill.className = "status-pill";
  pill.textContent = text(value);
  cell.appendChild(pill);
  return cell;
}

function renderResults() {
  const body = document.getElementById("result-ledger-rows");
  const count = document.getElementById("result-count");
  body.replaceChildren();

  if (!snapshot.results || snapshot.results.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = I18N[lang].emptyResults;
    row.appendChild(cell);
    body.appendChild(row);
    if (count) count.textContent = I18N[lang].rowsZero;
    return;
  }

  for (const item of snapshot.results) {
    const row = document.createElement("tr");
    row.append(
      td(item.metric),
      td(item.value),
      statusCell(item.status),
      td(item.artifact_path),
      td(item.notes),
    );
    body.appendChild(row);
  }
  if (count) count.textContent = I18N[lang].rows(snapshot.results.length);
}

function renderFigures() {
  const body = document.getElementById("figure-registry-rows");
  body.replaceChildren();
  const figures = (snapshot.figures || []).filter((item) => text(item.site_section, "") !== "");

  if (figures.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = I18N[lang].emptyFigures;
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  for (const item of figures) {
    const row = document.createElement("tr");
    row.append(
      td(item.figure_id),
      td(item.title),
      td(item.source_artifact),
      td(item.site_section),
      statusCell(item.status),
    );
    body.appendChild(row);
  }
}

function applyLang(next) {
  lang = next === "ko" ? "ko" : "en";
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
  // Dynamic (data-derived) strings depend on language too.
  renderResults();
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
  const date = document.getElementById("snapshot-date");
  if (date) date.textContent = text(snapshot.generated_at);
  renderFigures();
  applyLang(saved);
}

init();
