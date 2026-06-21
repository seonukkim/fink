"use strict";

const snapshotElement = document.getElementById("ledger-snapshot");
const snapshot = JSON.parse(snapshotElement.textContent);

function text(value, fallback = "not recorded") {
  if (value === null || value === undefined) {
    return fallback;
  }
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

  if (snapshot.results.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent =
      "No measured result rows exist in RESULT_LEDGER.csv yet. This page does not claim metric values.";
    row.appendChild(cell);
    body.appendChild(row);
    count.textContent = "No measured rows";
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
  count.textContent = `${snapshot.results.length} measured row${snapshot.results.length === 1 ? "" : "s"}`;
}

function renderFigures() {
  const body = document.getElementById("figure-registry-rows");
  body.replaceChildren();
  const figures = snapshot.figures.filter((item) => text(item.site_section, "") !== "");

  if (figures.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = "No project-page figure rows are registered.";
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

function renderSnapshotDate() {
  const date = document.getElementById("snapshot-date");
  date.textContent = text(snapshot.generated_at);
}

renderResults();
renderFigures();
renderSnapshotDate();
