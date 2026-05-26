/**
 * Pronto Networks — canvas particle network background
 */

const PARTICLE_COUNT = 100;
const CONNECT_DISTANCE = 130;
const REPEL_RADIUS = 180;
const REPEL_FORCE_MAX = 2;
const MAX_SPEED = 0.3;
const PULSE_INTERVAL_MS = 3000;
const PULSE_DURATION_MS = 1500;

/** @type {{ x: number, y: number, vx: number, vy: number, radius: number, color: string, baseRadius: number, type: string }[]} */
let particles = [];
/** @type {{ particleIndex: number, startTime: number } | null} */
let activePulse = null;
let mouseX = -9999;
let mouseY = -9999;
let canvas;
let ctx;
let animationId;
let pulseTimer;

function randomType() {
  const r = Math.random();
  if (r < 0.6) {
    return {
      type: "small",
      radius: 1,
      color: "rgba(34, 197, 94, 0.5)",
    };
  }
  if (r < 0.9) {
    return {
      type: "medium",
      radius: 1.5,
      color: "rgba(255, 255, 255, 0.15)",
    };
  }
  return {
    type: "large",
    radius: 2,
    color: "rgba(34, 197, 94, 0.8)",
  };
}

function createParticles(width, height) {
  particles = [];
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const t = randomType();
    const angle = Math.random() * Math.PI * 2;
    const speed = Math.random() * MAX_SPEED;
    particles.push({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      radius: t.radius,
      baseRadius: t.radius,
      color: t.color,
      type: t.type,
    });
  }
}

function resizeCanvas() {
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const w = window.innerWidth;
  const h = window.innerHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  if (particles.length === 0) {
    createParticles(w, h);
  } else {
    particles.forEach((p) => {
      p.x = Math.min(Math.max(p.x, 0), w);
      p.y = Math.min(Math.max(p.y, 0), h);
    });
  }
}

function triggerPulse() {
  if (particles.length === 0) return;
  activePulse = {
    particleIndex: Math.floor(Math.random() * particles.length),
    startTime: performance.now(),
  };
}

function drawPulseRing(p, progress) {
  const t = progress;
  const ringRadius = p.baseRadius + (8 - p.baseRadius) * Math.sin(t * Math.PI);
  const alpha = 0.3 * (1 - t);

  ctx.beginPath();
  ctx.arc(p.x, p.y, ringRadius, 0, Math.PI * 2);
  ctx.strokeStyle = `rgba(34, 197, 94, ${alpha})`;
  ctx.lineWidth = 1;
  ctx.stroke();

  p.radius = p.baseRadius + (8 - p.baseRadius) * Math.sin(t * Math.PI);
}

function updateParticles(width, height, now) {
  particles.forEach((p, i) => {
    const dx = p.x - mouseX;
    const dy = p.y - mouseY;
    const dist = Math.hypot(dx, dy);

    if (dist < REPEL_RADIUS && dist > 0) {
      const force = ((REPEL_RADIUS - dist) / REPEL_RADIUS) * REPEL_FORCE_MAX;
      p.vx += (dx / dist) * force;
      p.vy += (dy / dist) * force;
    }

    const speed = Math.hypot(p.vx, p.vy);
    if (speed > MAX_SPEED) {
      p.vx = (p.vx / speed) * MAX_SPEED;
      p.vy = (p.vy / speed) * MAX_SPEED;
    }

    p.x += p.vx;
    p.y += p.vy;

    if (p.x <= p.radius) {
      p.x = p.radius;
      p.vx = Math.abs(p.vx) * 0.95;
    } else if (p.x >= width - p.radius) {
      p.x = width - p.radius;
      p.vx = -Math.abs(p.vx) * 0.95;
    }

    if (p.y <= p.radius) {
      p.y = p.radius;
      p.vy = Math.abs(p.vy) * 0.95;
    } else if (p.y >= height - p.radius) {
      p.y = height - p.radius;
      p.vy = -Math.abs(p.vy) * 0.95;
    }

    p.radius = p.baseRadius;

    if (activePulse && activePulse.particleIndex === i) {
      const elapsed = now - activePulse.startTime;
      const progress = Math.min(elapsed / PULSE_DURATION_MS, 1);
      drawPulseRing(p, progress);
      if (progress >= 1) {
        activePulse = null;
      }
    }
  });
}

function drawConnections() {
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const a = particles[i];
      const b = particles[j];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      if (dist < CONNECT_DISTANCE) {
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = "rgba(34, 197, 94, 0.08)";
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }
    }
  }
}

function drawParticles() {
  particles.forEach((p) => {
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
    ctx.fillStyle = p.color;
    ctx.fill();
  });
}

function animate(now) {
  const w = window.innerWidth;
  const h = window.innerHeight;
  ctx.clearRect(0, 0, w, h);

  updateParticles(w, h, now);
  drawConnections();
  drawParticles();

  animationId = requestAnimationFrame(animate);
}

function onMouseMove(e) {
  mouseX = e.clientX;
  mouseY = e.clientY;
}

function onMouseLeave() {
  mouseX = -9999;
  mouseY = -9999;
}

export function initBackground() {
  canvas = document.getElementById("bg-canvas");
  if (!canvas) return;

  ctx = canvas.getContext("2d");
  resizeCanvas();

  window.addEventListener("resize", resizeCanvas);
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseleave", onMouseLeave);

  pulseTimer = setInterval(triggerPulse, PULSE_INTERVAL_MS);
  triggerPulse();

  animationId = requestAnimationFrame(animate);
}

document.addEventListener("DOMContentLoaded", initBackground);
