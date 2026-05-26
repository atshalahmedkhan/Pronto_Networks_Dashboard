/**
 * GSAP animations — page load, scroll, hover, counters, score bars
 */

import { getDashboardStats } from "./data.js";

export function initAnimations() {
  if (typeof gsap === "undefined") return;

  gsap.registerPlugin(ScrollTrigger);

  runPageLoadTimeline();
  initCardHovers();
  initFilterClickAnimation();
}

function runPageLoadTimeline() {
  const tl = gsap.timeline({ defaults: { ease: "power3.out" } });

  tl.from(".navbar", {
    y: -60,
    opacity: 0,
    duration: 0.6,
  })
    .from(
      ".hero__title",
      { y: 40, opacity: 0, duration: 0.8 },
      0.2
    )
    .from(
      ".hero__subtitle",
      { y: 40, opacity: 0, duration: 0.8 },
      0.4
    )
    .from(
      ".stat-card",
      { y: 30, opacity: 0, duration: 0.6, stagger: 0.15 },
      0.5
    );

  animateCounters();
}

export function animateCounters(stats = getDashboardStats()) {
  const prospectsEl = document.querySelector('[data-counter="prospects"]');
  const scoreEl = document.querySelector('[data-counter="score"]');
  const emailsEl = document.querySelector('[data-counter="emails"]');
  const industriesEl = document.querySelector('[data-counter="industries"]');

  if (prospectsEl) {
    gsap.fromTo(
      prospectsEl,
      { innerText: 0 },
      {
        innerText: stats.prospects,
        duration: 1.4,
        ease: "power2.out",
        snap: { innerText: 1 },
        delay: 0.6,
      }
    );
  }

  if (scoreEl) {
    const counter = { val: 0 };
    gsap.to(counter, {
      val: stats.avgScore,
      duration: 1.4,
      ease: "power2.out",
      delay: 0.7,
      onUpdate: () => {
        scoreEl.textContent = counter.val.toFixed(1);
      },
    });
  }

  if (emailsEl) {
    gsap.fromTo(
      emailsEl,
      { innerText: 0 },
      {
        innerText: stats.emails,
        duration: 1.4,
        ease: "power2.out",
        snap: { innerText: 1 },
        delay: 0.8,
      }
    );
  }

  if (industriesEl) {
    gsap.fromTo(
      industriesEl,
      { innerText: 0 },
      {
        innerText: stats.industries,
        duration: 1.2,
        ease: "power2.out",
        snap: { innerText: 1 },
        delay: 0.9,
      }
    );
  }
}

export function animateScoreBars(container = document) {
  const fills = container.querySelectorAll(".score-bar__fill");
  if (!fills.length) return;

  gsap.set(fills, { width: "0%" });

  gsap.to(fills, {
    width: (i, el) => `${el.dataset.score}%`,
    duration: 1.4,
    ease: "power3.out",
    stagger: 0.1,
    delay: 0.3,
  });
}

export function initScrollTriggerCards(container = document) {
  const cards = container.querySelectorAll(".lead-card");
  if (!cards.length || typeof ScrollTrigger === "undefined") return;

  cards.forEach((card, i) => {
    gsap.from(card, {
      y: 50,
      opacity: 0,
      duration: 0.7,
      ease: "power3.out",
      scrollTrigger: {
        trigger: card,
        start: "top 88%",
        toggleActions: "play none none none",
        id: `card-${card.dataset.id}`,
      },
      delay: (i % 3) * 0.1,
    });
  });
}

function initCardHovers() {
  document.addEventListener(
    "mouseenter",
    (e) => {
      const card = e.target.closest(".lead-card");
      if (!card) return;
      gsap.to(card, { y: -6, duration: 0.3, ease: "power2.out" });
    },
    true
  );

  document.addEventListener(
    "mouseleave",
    (e) => {
      const card = e.target.closest(".lead-card");
      if (!card) return;
      gsap.to(card, { y: 0, duration: 0.3, ease: "power2.out" });
    },
    true
  );
}

function initFilterClickAnimation() {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;
    gsap.fromTo(
      btn,
      { scale: 1 },
      { scale: 1.05, duration: 0.1, yoyo: true, repeat: 1, ease: "power2.inOut" }
    );
  });
}

export function animateCopySuccess(button) {
  const originalBg = "#22c55e";
  const originalText = button.textContent;

  gsap.to(button, {
    backgroundColor: "#22c55e",
    duration: 0.3,
    onComplete: () => {
      button.textContent = "Copied!";
      gsap.to(button, {
        backgroundColor: originalBg,
        duration: 0.3,
        delay: 1.2,
        onComplete: () => {
          button.textContent = originalText;
        },
      });
    },
  });
}

export function staggerCardsIn(container) {
  const cards = container.querySelectorAll(".lead-card");
  gsap.fromTo(
    cards,
    { opacity: 0, y: 24 },
    {
      opacity: 1,
      y: 0,
      duration: 0.45,
      stagger: 0.08,
      ease: "power3.out",
      onComplete: () => {
        animateScoreBars(container);
        initScrollTriggerCards(container);
      },
    }
  );
}

export function fadeOutCards(cards, onComplete) {
  gsap.to(cards, {
    opacity: 0,
    y: -12,
    duration: 0.25,
    stagger: 0.04,
    ease: "power2.in",
    onComplete,
  });
}
