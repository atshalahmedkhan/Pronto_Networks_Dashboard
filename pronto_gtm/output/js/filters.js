/**
 * Filters, search, sort, render, copy — dashboard interactivity
 */

import { LEADS, INDUSTRY_FILTERS } from "./data.js";
import {
  initAnimations,
  animateScoreBars,
  initScrollTriggerCards,
  staggerCardsIn,
  fadeOutCards,
  animateCopySuccess,
} from "./animations.js";

let activeFilter = "all";
let searchQuery = "";
let sortDescending = true;
let displayedLeads = [...LEADS];

const gridEl = () => document.getElementById("leads-grid");
const filtersContainer = () => document.getElementById("filters");
const searchInput = () => document.getElementById("search");
const sortBtn = () => document.getElementById("sort-btn");

function scoreClass(score) {
  if (score >= 8) return "high";
  if (score >= 6) return "mid";
  return "low";
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function matchesFilter(lead) {
  const industryMatch =
    activeFilter === "all" || lead.industry === activeFilter;
  const q = searchQuery.toLowerCase().trim();
  const searchMatch =
    !q ||
    lead.name.toLowerCase().includes(q) ||
    lead.industry.toLowerCase().includes(q);
  return industryMatch && searchMatch;
}

function getFilteredLeads() {
  return displayedLeads.filter(matchesFilter);
}

function sortLeads(leads) {
  return [...leads].sort((a, b) =>
    sortDescending ? b.score - a.score : a.score - b.score
  );
}

function renderCard(lead) {
  const sc = scoreClass(lead.score);
  const pct = lead.score * 10;

  return `
    <article class="lead-card" data-id="${lead.id}" data-industry="${escapeHtml(lead.industry)}">
      <div class="lead-card__header">
        <h2 class="lead-card__name">
          <a href="${escapeHtml(lead.website)}" target="_blank" rel="noopener noreferrer">
            ${escapeHtml(lead.name)}
          </a>
        </h2>
        <span class="industry-badge" style="color:${lead.industryColor}; border-color:${lead.industryColor}">
          ${escapeHtml(lead.industry)}
        </span>
      </div>

      <div class="score-row">
        <span class="score-row__number ${sc}">${lead.score}</span>
        <div class="score-bar">
          <div class="score-bar__fill ${sc}" data-score="${pct}" style="width:0%"></div>
        </div>
      </div>

      <div class="lead-card__meta">
        <div class="meta-row">
          <span class="meta-row__label">Decision maker</span>
          <span class="meta-row__value">${escapeHtml(lead.target)}</span>
        </div>
        <div class="meta-row">
          <span class="meta-row__label">Pain point</span>
          <span class="meta-row__value">${escapeHtml(lead.pain)}</span>
        </div>
        <div class="meta-row">
          <span class="meta-row__label">Pronto product fit</span>
          <span class="meta-row__value meta-row__value--product">${escapeHtml(lead.product)}</span>
        </div>
      </div>

      <div class="email-section">
        <p class="email-section__label">Cold email</p>
        <div class="email-box" data-email-id="${lead.id}">${escapeHtml(lead.email)}</div>
        <button type="button" class="copy-btn" data-copy-id="${lead.id}" aria-label="Copy email">
          Copy Email
        </button>
      </div>
    </article>
  `;
}

function renderGrid(leads, animate = true) {
  const grid = gridEl();
  if (!grid) return;

  const sorted = sortLeads(leads);

  if (sorted.length === 0) {
    grid.classList.add("empty-state");
    grid.innerHTML = `<p class="empty-state__text">No leads match your filters.</p>`;
    return;
  }

  grid.classList.remove("empty-state");
  const html = sorted.map(renderCard).join("");

  if (!animate) {
    grid.innerHTML = html;
    animateScoreBars(grid);
    initScrollTriggerCards(grid);
    return;
  }

  const existing = grid.querySelectorAll(".lead-card");
  if (existing.length) {
    fadeOutCards(existing, () => {
      if (typeof ScrollTrigger !== "undefined") {
        ScrollTrigger.getAll().forEach((t) => t.kill());
      }
      grid.innerHTML = html;
      staggerCardsIn(grid);
    });
  } else {
    grid.innerHTML = html;
    staggerCardsIn(grid);
  }
}

function renderFilterButtons() {
  const container = filtersContainer();
  if (!container) return;

  container.innerHTML = INDUSTRY_FILTERS.map(
    (f) => `
    <button type="button" class="filter-btn${f.key === activeFilter ? " active" : ""}"
      data-filter="${escapeHtml(f.key)}">
      ${escapeHtml(f.label)}
    </button>
  `
  ).join("");
}

function setActiveFilterButton(key) {
  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.filter === key);
  });
}

function updateResultsCount(visibleCount) {
  const el = document.getElementById("results-count");
  if (!el) return;
  el.innerHTML = `Showing <strong>${visibleCount}</strong> of <strong>${LEADS.length}</strong> companies`;
}

function applyFiltersAndRender(animate = true) {
  const filtered = getFilteredLeads();
  updateResultsCount(filtered.length);
  renderGrid(filtered, animate);
}

function initFilters() {
  renderFilterButtons();

  filtersContainer()?.addEventListener("click", (e) => {
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;
    activeFilter = btn.dataset.filter;
    setActiveFilterButton(activeFilter);
    applyFiltersAndRender(true);
  });
}

function initSearch() {
  const input = searchInput();
  if (!input) return;

  input.addEventListener("input", () => {
    searchQuery = input.value;
    applyFiltersAndRender(true);
  });
}

function initSort() {
  const btn = sortBtn();
  if (!btn) return;

  btn.addEventListener("click", () => {
    sortDescending = !sortDescending;
    btn.classList.toggle("desc", sortDescending);
    btn.querySelector(".sort-btn__label").textContent = sortDescending
      ? "Score: High → Low"
      : "Score: Low → High";
    applyFiltersAndRender(true);
  });
}

function initCopyButtons() {
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".copy-btn");
    if (!btn) return;

    const id = btn.dataset.copyId;
    const box = document.querySelector(`[data-email-id="${id}"]`);
    if (!box) return;

    try {
      await navigator.clipboard.writeText(box.textContent.trim());
      animateCopySuccess(btn);
    } catch {
      const range = document.createRange();
      range.selectNodeContents(box);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
      document.execCommand("copy");
      sel?.removeAllRanges();
      animateCopySuccess(btn);
    }
  });
}

function init() {
  displayedLeads = [...LEADS];
  updateResultsCount(getFilteredLeads().length);
  renderGrid(getFilteredLeads(), false);
  initFilters();
  initSearch();
  initSort();
  initCopyButtons();
  initAnimations();

  requestAnimationFrame(() => {
    animateScoreBars(gridEl());
    initScrollTriggerCards(gridEl());
  });
}

document.addEventListener("DOMContentLoaded", init);
