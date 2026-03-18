window.OrbArena = window.OrbArena || {};

const canvas = document.getElementById('game-canvas');
const ctx = canvas.getContext('2d');
const minimapCanvas = document.getElementById('minimap');
const minimapCtx = minimapCanvas.getContext('2d');
const scoreDisplay = document.getElementById('score-display').querySelector('span');
const leaderboardList = document.getElementById('leaderboard-list');
const boostBtn = document.getElementById('boost-btn');
const shootBtn = document.getElementById('shoot-btn');
const mineBtn = document.getElementById('mine-btn');
const powerupHud = document.getElementById('powerup-hud');
const disasterHud = document.getElementById('disaster-hud');

const ZOOM_MIN = 0.55;
const ZOOM_MAX = 1.0;
const ZOOM_MAX_MOBILE = 0.75;
const ZOOM_RADIUS_START = 30;
const ZOOM_RADIUS_END = 120;
const TOUCH_SENSITIVITY = 3;
const MAX_PARTICLES = 800;
const vfxShakeDecay = 0.9;

function isMobile() { return OrbArena.state.isTouchDevice || window.innerWidth <= 768; }

function getZoomForRadius(radius) {
    const maxZoom = isMobile() ? ZOOM_MAX_MOBILE : ZOOM_MAX;
    if (radius <= ZOOM_RADIUS_START) return maxZoom;
    if (radius >= ZOOM_RADIUS_END) return ZOOM_MIN;
    const t = (radius - ZOOM_RADIUS_START) / (ZOOM_RADIUS_END - ZOOM_RADIUS_START);
    return maxZoom - t * (maxZoom - ZOOM_MIN);
}

function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    const minimapSize = window.innerWidth <= 768 ? 100 : 150;
    minimapCanvas.width = minimapSize;
    minimapCanvas.height = minimapSize;
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

// ── VFX System ──

function spawnParticle(config) {
    const ns = OrbArena.state;
    if (ns.particles.length >= MAX_PARTICLES) return;
    ns.particles.push({
        x: config.x, y: config.y,
        vx: config.vx || 0, vy: config.vy || 0,
        radius: config.radius || 3,
        color: config.color || '#ffffff',
        alpha: config.alpha || 1.0,
        life: config.life || 30,
        maxLife: config.life || 30,
    });
}

function updateParticles() {
    const particles = OrbArena.state.particles;
    for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i];
        p.x += p.vx; p.y += p.vy;
        p.vx *= 0.95; p.vy *= 0.95;
        p.life--;
        p.alpha = Math.max(0, p.life / p.maxLife);
        p.radius *= 0.98;
        if (p.life <= 0) { particles[i] = particles[particles.length - 1]; particles.pop(); }
    }
}

function renderParticles() {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    const vw = canvas.width / ns.currentZoom;
    const vh = canvas.height / ns.currentZoom;
    for (let i = 0; i < ns.particles.length; i++) {
        const p = ns.particles[i];
        const sx = p.x - state.camera.x;
        const sy = p.y - state.camera.y;
        if (sx < -20 || sx > vw + 20 || sy < -20 || sy > vh + 20) continue;
        ctx.globalAlpha = p.alpha;
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(sx, sy, Math.max(0.5, p.radius), 0, Math.PI * 2);
        ctx.fill();
    }
    ctx.globalAlpha = 1;
}

function spawnOrbBurst(x, y, color, radius, isGolden) {
    const count = isGolden ? 12 : 6;
    for (let i = 0; i < count; i++) {
        const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.5;
        const speed = 1.5 + Math.random() * 2.5;
        spawnParticle({ x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
            radius: isGolden ? 3.5 : 2.5, color, life: isGolden ? 25 : 18 });
    }
}

function triggerScreenShake(intensity) {
    OrbArena.state.vfxShakeIntensity = Math.max(OrbArena.state.vfxShakeIntensity, intensity);
}

function spawnStrikeImpact(x, y) {
    const state = OrbArena.state.state;
    const near = !state.you || !state.you.alive || Math.hypot(x - state.you.x, y - state.you.y) < 600;
    if (!near) return;
    for (let i = 0; i < 12; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = 2 + Math.random() * 5;
        spawnParticle({ x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
            radius: 4 + Math.random() * 6, color: Math.random() < 0.5 ? '#ff3300' : '#ff7700',
            life: 20 + Math.floor(Math.random() * 12) });
    }
    spawnParticle({ x, y, vx: 0, vy: 0, radius: 18, color: '#ffdd66', life: 7 });
    OrbArena.audio.sfx.meteorImpact();
    triggerScreenShake(6);
}

function updateScreenShake() {
    const ns = OrbArena.state;
    if (ns.vfxShakeIntensity > 0.1) {
        ns.vfxShakeX = (Math.random() - 0.5) * ns.vfxShakeIntensity;
        ns.vfxShakeY = (Math.random() - 0.5) * ns.vfxShakeIntensity;
        ns.vfxShakeIntensity *= vfxShakeDecay;
    } else {
        ns.vfxShakeIntensity = 0; ns.vfxShakeX = 0; ns.vfxShakeY = 0;
    }
}

function isNearPlayer(x, y, range) {
    const state = OrbArena.state.state;
    if (!state.you || !state.you.alive) return false;
    const dx = x - state.you.x, dy = y - state.you.y;
    return (dx * dx + dy * dy) < range * range;
}

function detectOrbConsumption(newData) {
    const ns = OrbArena.state;
    const sfx = OrbArena.audio.sfx;
    const currentEnergyIds = new Set();
    const currentGoldenIds = new Set();
    if (newData.energy_orbs) newData.energy_orbs.forEach(o => currentEnergyIds.add(o.id));
    if (newData.golden_orbs) newData.golden_orbs.forEach(o => currentGoldenIds.add(o.id));
    for (const [id, orb] of ns.prevEnergyOrbs) {
        if (!currentEnergyIds.has(id)) {
            spawnOrbBurst(orb.x, orb.y, orb.color, orb.radius, false);
            if (isNearPlayer(orb.x, orb.y, 200)) sfx.orbPickup();
        }
    }
    for (const [id, orb] of ns.prevGoldenOrbs) {
        if (!currentGoldenIds.has(id)) {
            spawnOrbBurst(orb.x, orb.y, '#ffd700', orb.radius, true);
            if (isNearPlayer(orb.x, orb.y, 200)) sfx.goldenPickup();
        }
    }
    const currentSpikeIds = new Set();
    if (newData.spike_orbs) newData.spike_orbs.forEach(o => currentSpikeIds.add(o.id));
    for (const [id, orb] of ns.prevSpikeOrbs) {
        if (!currentSpikeIds.has(id) && isNearPlayer(orb.x, orb.y, 200)) sfx.spikeHit();
    }
    ns.prevSpikeOrbs = new Map();
    if (newData.spike_orbs) newData.spike_orbs.forEach(o => ns.prevSpikeOrbs.set(o.id, o));
    const currentMineIds = new Set();
    if (newData.mines) newData.mines.forEach(m => currentMineIds.add(m.id));
    for (const [id, mine] of ns.prevMines) {
        if (!currentMineIds.has(id) && isNearPlayer(mine.x, mine.y, 300)) sfx.mineExplode();
    }
    ns.prevMines = new Map();
    if (newData.mines) newData.mines.forEach(m => ns.prevMines.set(m.id, m));
    ns.prevEnergyOrbs = new Map();
    if (newData.energy_orbs) newData.energy_orbs.forEach(o => ns.prevEnergyOrbs.set(o.id, o));
    ns.prevGoldenOrbs = new Map();
    if (newData.golden_orbs) newData.golden_orbs.forEach(o => ns.prevGoldenOrbs.set(o.id, o));
}

function spawnKillEffects(x, y, scoreDelta, victimColor, consumerRadius) {
    const ns = OrbArena.state;
    ns.killPopups.push({ x, y, text: '+' + scoreDelta, time: Date.now(), duration: 1500 });
    ns.killRings.push({ x, y, color: victimColor, startRadius: consumerRadius,
        maxRadius: consumerRadius * 3, time: Date.now(), duration: 500 });
}

function updateKillEffects() {
    const ns = OrbArena.state;
    const now = Date.now();
    for (let i = ns.killPopups.length - 1; i >= 0; i--) {
        if (now - ns.killPopups[i].time > ns.killPopups[i].duration) ns.killPopups.splice(i, 1);
    }
    for (let i = ns.killRings.length - 1; i >= 0; i--) {
        if (now - ns.killRings[i].time > ns.killRings[i].duration) ns.killRings.splice(i, 1);
    }
}

function renderKillRings() {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    const now = Date.now();
    const vw = canvas.width / ns.currentZoom;
    const vh = canvas.height / ns.currentZoom;
    for (let i = 0; i < ns.killRings.length; i++) {
        const ring = ns.killRings[i];
        const elapsed = now - ring.time;
        const t = elapsed / ring.duration;
        if (t >= 1) continue;
        const sx = ring.x - state.camera.x, sy = ring.y - state.camera.y;
        const currentRadius = ring.startRadius + (ring.maxRadius - ring.startRadius) * t;
        if (sx + currentRadius < 0 || sx - currentRadius > vw || sy + currentRadius < 0 || sy - currentRadius > vh) continue;
        ctx.strokeStyle = ring.color;
        ctx.globalAlpha = 0.5 * (1 - t);
        ctx.lineWidth = 4 * (1 - t) + 1;
        ctx.beginPath(); ctx.arc(sx, sy, currentRadius, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.globalAlpha = 1;
}

function renderKillPopups() {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    const now = Date.now();
    const vw = canvas.width / ns.currentZoom;
    const vh = canvas.height / ns.currentZoom;
    for (let i = 0; i < ns.killPopups.length; i++) {
        const popup = ns.killPopups[i];
        const elapsed = now - popup.time;
        const t = elapsed / popup.duration;
        if (t >= 1) continue;
        const sx = popup.x - state.camera.x, sy = popup.y - state.camera.y;
        if (sx < -100 || sx > vw + 100 || sy < -100 || sy > vh + 100) continue;
        const rise = elapsed * 0.03;
        const alpha = t < 0.67 ? 1.0 : 1.0 - ((t - 0.67) / 0.33);
        ctx.globalAlpha = alpha;
        ctx.font = '700 16px "Share Tech Mono", monospace';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillStyle = '#000'; ctx.fillText(popup.text, sx + 1, sy - rise + 1);
        ctx.fillStyle = '#ffdd44'; ctx.fillText(popup.text, sx, sy - rise);
    }
    ctx.globalAlpha = 1;
}

// ── HUD Updaters ──

function updateBoostButton() {
    const state = OrbArena.state.state;
    if (!state.you || !state.you.alive) { boostBtn.style.display = 'none'; return; }
    if (isMobile()) boostBtn.style.display = 'flex';
    const hasWormhole = state.you.wormhole_held;
    const hasTrail = state.you.trail_held;
    if (hasWormhole) {
        boostBtn.classList.remove('boosting', 'cooldown'); boostBtn.textContent = 'WORMHOLE';
    } else if (state.you.is_boosting) {
        boostBtn.classList.add('boosting'); boostBtn.classList.remove('cooldown'); boostBtn.textContent = 'BOOST!';
    } else if (state.you.boost_ready) {
        boostBtn.classList.remove('boosting', 'cooldown'); boostBtn.textContent = hasTrail ? 'TRON' : 'BOOST';
    } else {
        boostBtn.classList.remove('boosting'); boostBtn.classList.add('cooldown'); boostBtn.textContent = 'WAIT';
    }
}

function updateShootButton() {
    const state = OrbArena.state.state;
    if (!state.you || !state.you.alive || (state.challengeMode && state.challengeName === 'rally_run')) {
        shootBtn.style.display = 'none'; return;
    }
    if (isMobile()) shootBtn.style.display = 'flex';
    if (state.you.radius < OrbArena.config.PROJECTILE_MIN_RADIUS) {
        shootBtn.classList.add('cooldown'); shootBtn.textContent = 'GROW';
    } else if (state.you.shoot_ready) {
        shootBtn.classList.remove('cooldown'); shootBtn.textContent = 'SHOOT';
    } else {
        shootBtn.classList.add('cooldown'); shootBtn.textContent = 'WAIT';
    }
}

function updateMineButton() {
    const state = OrbArena.state.state;
    if (!state.you || !state.you.alive || !state.you.mines_remaining || state.you.mines_remaining <= 0) {
        mineBtn.style.display = 'none'; return;
    }
    if (isMobile()) { mineBtn.style.display = 'flex'; mineBtn.textContent = `MINE (${state.you.mines_remaining})`; }
}

function updatePowerUpHud() {
    const state = OrbArena.state.state;
    const POWERUP_COLORS = OrbArena.config.POWERUP_COLORS;
    if (!state.you || !state.you.alive) { powerupHud.style.display = 'none'; return; }
    if (state.you.wormhole_held) {
        powerupHud.style.display = 'block';
        powerupHud.style.background = 'rgba(0, 40, 35, 0.85)';
        powerupHud.style.borderColor = 'rgba(0, 210, 170, 0.7)';
        powerupHud.style.color = '#00e0b0';
        powerupHud.textContent = 'WORMHOLE - READY'; return;
    }
    if (!state.you.active_powerup) { powerupHud.style.display = 'none'; return; }
    const pu = POWERUP_COLORS[state.you.active_powerup];
    if (!pu) { powerupHud.style.display = 'none'; return; }
    powerupHud.style.display = 'block';
    powerupHud.style.background = pu.bg;
    powerupHud.style.borderColor = pu.border;
    powerupHud.style.color = pu.text;
    powerupHud.textContent = `${pu.name}: ${Math.ceil(state.you.powerup_remaining)}s`;
}

function updateDisasterHud() {
    const state = OrbArena.state.state;
    const DISASTER_NAMES = OrbArena.config.DISASTER_NAMES;
    const d = state.disaster;
    if (!d) { disasterHud.style.display = 'none'; return; }
    if (d.warning) {
        disasterHud.style.display = 'block'; disasterHud.className = 'warning';
        const name = DISASTER_NAMES[d.warning] || d.warning;
        disasterHud.textContent = `WARNING: ${name} INCOMING (${Math.ceil(d.warning_remaining)}s)`;
    } else if (d.active) {
        disasterHud.style.display = 'block';
        const name = DISASTER_NAMES[d.active] || d.active;
        let extraClass = '';
        if (d.active === 'fog_of_war') extraClass = ' fog';
        else if (d.active === 'feeding_frenzy') extraClass = ' frenzy';
        disasterHud.className = 'active' + extraClass;
        const remaining = d.remaining != null ? ` (${Math.ceil(d.remaining)}s)` : '';
        disasterHud.textContent = `${name}${remaining}`;
    } else { disasterHud.style.display = 'none'; }
}

// ── Update Loop ──

function update() {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    if (!state.playing) return;

    let targetPlayer = state.you;
    if (state.connectionMode === 'spectate') {
        if (state.players && state.players.length > 0) {
            targetPlayer = state.players.reduce((highest, player) =>
                player.score > (highest?.score || 0) ? player : highest, state.players[0]);
        } else {
            targetPlayer = { x: state.world.width / 2, y: state.world.height / 2, radius: 20 };
        }
    }
    if (!targetPlayer) return;

    const strikePhase = state.challengeData && state.challengeData.strike_phase;
    if (strikePhase === 'danger_close' || strikePhase === 'barrage') {
        ns.targetZoom = 0.38;
        ns.currentZoom += (ns.targetZoom - ns.currentZoom) * 0.035;
    } else {
        ns.targetZoom = getZoomForRadius(targetPlayer.radius || 20);
        ns.currentZoom += (ns.targetZoom - ns.currentZoom) * 0.08;
    }

    const viewW = canvas.width / ns.currentZoom;
    const viewH = canvas.height / ns.currentZoom;
    state.camera.x = targetPlayer.x - viewW / 2;
    state.camera.y = targetPlayer.y - viewH / 2;

    if (state.you && state.you.alive) {
        state.lastScore = state.you.score;
        scoreDisplay.textContent = state.you.score;
    }

    updateLeaderboard();
    updateBoostButton();
    updateShootButton();
    updateMineButton();
    updatePowerUpHud();
    updateDisasterHud();

    if (state.you && state.you.active_powerup === 'rapid_fire') {
        if (ns.isMouseDown && !ns.isTouchDevice) {
            const worldX = ns.mouseX / ns.currentZoom + state.camera.x;
            const worldY = ns.mouseY / ns.currentZoom + state.camera.y;
            OrbArena.network.sendShoot(worldX, worldY);
        } else if (ns.isShootBtnHeld && state.you.alive) {
            OrbArena.network.sendShoot(
                state.you.x + (ns.touchCurrent ? (ns.touchCurrent.x - (ns.touchOrigin ? ns.touchOrigin.x : 0)) * TOUCH_SENSITIVITY : 0),
                state.you.y + (ns.touchCurrent ? (ns.touchCurrent.y - (ns.touchOrigin ? ns.touchOrigin.y : 0)) * TOUCH_SENSITIVITY : 0)
            );
        }
    }

    if (Date.now() % 33 < 17) OrbArena.network.sendMovement();
    updateParticles();
    updateScreenShake();
    updateKillEffects();
}

function updateLeaderboard() {
    const state = OrbArena.state.state;
    leaderboardList.innerHTML = '';
    state.leaderboard.forEach((entry, index) => {
        const li = document.createElement('li');
        const nameSpan = document.createElement('span');
        nameSpan.textContent = `${index + 1}. ${entry.name}`;
        const scoreSpan = document.createElement('span');
        scoreSpan.textContent = entry.score;
        li.appendChild(nameSpan); li.appendChild(scoreSpan);
        if (state.you && entry.name === state.you.name) li.className = 'you';
        leaderboardList.appendChild(li);
    });
}

// ── Disaster Rendering ──

function drawBlackHole(bh, progress) {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    const screenX = bh.x - state.camera.x, screenY = bh.y - state.camera.y;
    if (isOffScreen(screenX, screenY, 600)) return;
    const r = bh.radius, t = Date.now() / 1000;
    const pullRange = 500 * progress;
    const diskGrad = ctx.createRadialGradient(screenX, screenY, r, screenX, screenY, pullRange);
    diskGrad.addColorStop(0, 'rgba(80, 0, 120, 0.4)');
    diskGrad.addColorStop(0.3, 'rgba(40, 0, 80, 0.2)');
    diskGrad.addColorStop(0.6, 'rgba(20, 0, 50, 0.1)');
    diskGrad.addColorStop(1, 'transparent');
    ctx.fillStyle = diskGrad;
    ctx.beginPath(); ctx.arc(screenX, screenY, pullRange, 0, Math.PI * 2); ctx.fill();
    for (let i = 0; i < 3; i++) {
        const ringR = r * (1.5 + i * 0.8);
        ctx.strokeStyle = `rgba(150, 50, 255, ${0.3 - i * 0.08})`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(screenX, screenY, ringR, ringR * 0.4, t * (1 + i * 0.3) + i, 0, Math.PI * 2);
        ctx.stroke();
    }
    const coreGrad = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, r);
    coreGrad.addColorStop(0, 'rgba(0, 0, 0, 1)');
    coreGrad.addColorStop(0.7, 'rgba(0, 0, 0, 0.95)');
    coreGrad.addColorStop(1, 'rgba(30, 0, 60, 0.8)');
    ctx.fillStyle = coreGrad;
    ctx.beginPath(); ctx.arc(screenX, screenY, r, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = `rgba(200, 100, 255, ${0.5 + Math.sin(t * 5) * 0.2})`;
    ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(screenX, screenY, r + 2, 0, Math.PI * 2); ctx.stroke();
    for (let i = 0; i < 8; i++) {
        const angle = t * 2 + i * Math.PI / 4;
        const dist = r + 8 + Math.sin(t * 3 + i) * 5;
        ctx.fillStyle = `rgba(200, 150, 255, ${0.6 + Math.sin(t * 4 + i) * 0.3})`;
        ctx.beginPath(); ctx.arc(screenX + Math.cos(angle) * dist, screenY + Math.sin(angle) * dist, 2, 0, Math.PI * 2); ctx.fill();
    }
}

function drawMeteorImpact(meteor) {
    const state = OrbArena.state.state;
    const screenX = meteor.x - state.camera.x, screenY = meteor.y - state.camera.y;
    if (isOffScreen(screenX, screenY, 100)) return;
    const r = meteor.radius;
    const flashGrad = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, r * 2);
    flashGrad.addColorStop(0, 'rgba(255, 200, 50, 0.8)');
    flashGrad.addColorStop(0.3, 'rgba(255, 100, 0, 0.5)');
    flashGrad.addColorStop(0.6, 'rgba(255, 50, 0, 0.2)');
    flashGrad.addColorStop(1, 'transparent');
    ctx.fillStyle = flashGrad;
    ctx.beginPath(); ctx.arc(screenX, screenY, r * 2, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = 'rgba(255, 150, 50, 0.6)'; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(screenX, screenY, r, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = 'rgba(255, 255, 200, 0.9)';
    ctx.beginPath(); ctx.arc(screenX, screenY, 5, 0, Math.PI * 2); ctx.fill();
}

function drawFogOfWar(fogRadius) {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    if (!state.you || !state.you.alive) return;
    const screenX = state.you.x - state.camera.x, screenY = state.you.y - state.camera.y;
    const vw = canvas.width / ns.currentZoom, vh = canvas.height / ns.currentZoom;
    ctx.save();
    ctx.fillStyle = 'rgb(5, 5, 20)';
    ctx.beginPath();
    ctx.rect(0, 0, vw, vh);
    ctx.arc(screenX, screenY, fogRadius, 0, Math.PI * 2, true);
    ctx.fill('evenodd');
    const edgeGrad = ctx.createRadialGradient(screenX, screenY, fogRadius * 0.65, screenX, screenY, fogRadius);
    edgeGrad.addColorStop(0, 'rgba(5, 5, 20, 0)');
    edgeGrad.addColorStop(1, 'rgb(5, 5, 20)');
    ctx.fillStyle = edgeGrad;
    ctx.beginPath(); ctx.arc(screenX, screenY, fogRadius, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
    const t = Date.now() / 1000;
    for (let i = 0; i < 12; i++) {
        const angle = t * 0.3 + i * Math.PI / 6;
        const dist = fogRadius - 20 + Math.sin(t + i) * 30;
        ctx.fillStyle = `rgba(100, 100, 150, ${0.15 + Math.sin(t * 2 + i) * 0.1})`;
        ctx.beginPath();
        ctx.arc(screenX + Math.cos(angle) * dist, screenY + Math.sin(angle) * dist, 15 + Math.sin(t + i * 2) * 5, 0, Math.PI * 2);
        ctx.fill();
    }
}

function drawSupernova(nova) {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    const screenX = nova.x - state.camera.x, screenY = nova.y - state.camera.y;
    const elapsed = nova.time;
    const pulseCount = nova.pulse_count || 5;
    const pulseInterval = nova.pulse_interval || 1.5;
    const pulseExpand = nova.pulse_expand || 1.2;
    for (let p = 0; p < pulseCount; p++) {
        const pulseStart = p * pulseInterval;
        const pulseElapsed = elapsed - pulseStart;
        if (pulseElapsed >= 0 && pulseElapsed < 0.3) {
            const flashAlpha = (1 - pulseElapsed / 0.3) * (0.25 - p * 0.03);
            ctx.fillStyle = `rgba(255, 255, 255, ${Math.max(0, flashAlpha)})`;
            ctx.fillRect(0, 0, canvas.width / ns.currentZoom, canvas.height / ns.currentZoom);
            break;
        }
    }
    for (let p = 0; p < pulseCount; p++) {
        const pulseStart = p * pulseInterval;
        const pulseElapsed = elapsed - pulseStart;
        if (pulseElapsed < 0) continue;
        const fadeTime = pulseExpand + 0.5;
        if (pulseElapsed > fadeTime) continue;
        const expandT = Math.min(1, pulseElapsed / pulseExpand);
        const waveRadius = nova.radius * expandT;
        const alpha = Math.max(0, 1 - pulseElapsed / fadeTime);
        if (waveRadius < 5) continue;
        const r = 255, g = Math.max(40, 220 - p * 20), b = Math.max(20, 60 - p * 5);
        const bandWidth = Math.max(8, 60 - pulseElapsed * 20);
        const innerR = Math.max(1, waveRadius - bandWidth);
        const outerR = waveRadius + bandWidth;
        const flameGrad = ctx.createRadialGradient(screenX, screenY, innerR, screenX, screenY, outerR);
        flameGrad.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0)`);
        flameGrad.addColorStop(0.3, `rgba(${r}, ${Math.min(255, g + 60)}, ${b}, ${alpha * 0.5})`);
        flameGrad.addColorStop(0.5, `rgba(255, ${Math.min(255, g + 100)}, ${Math.min(255, b + 80)}, ${alpha * 0.85})`);
        flameGrad.addColorStop(0.7, `rgba(${r}, ${Math.min(255, g + 60)}, ${b}, ${alpha * 0.5})`);
        flameGrad.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);
        ctx.fillStyle = flameGrad;
        ctx.beginPath(); ctx.arc(screenX, screenY, outerR, 0, Math.PI * 2);
        ctx.arc(screenX, screenY, Math.max(0, innerR), 0, Math.PI * 2, true); ctx.fill('evenodd');
        ctx.strokeStyle = `rgba(255, ${Math.min(255, g + 120)}, ${Math.min(255, b + 100)}, ${alpha * 0.9})`;
        ctx.lineWidth = Math.max(2, 4 - pulseElapsed * 1.5);
        ctx.beginPath(); ctx.arc(screenX, screenY, waveRadius, 0, Math.PI * 2); ctx.stroke();
        if (pulseElapsed < pulseExpand) {
            const hazeR = Math.max(1, waveRadius * 0.85);
            const hazeGrad = ctx.createRadialGradient(screenX, screenY, hazeR * 0.3, screenX, screenY, hazeR);
            hazeGrad.addColorStop(0, `rgba(255, 200, 100, ${alpha * 0.15})`);
            hazeGrad.addColorStop(0.6, `rgba(${r}, ${g}, ${b}, ${alpha * 0.08})`);
            hazeGrad.addColorStop(1, 'transparent');
            ctx.fillStyle = hazeGrad;
            ctx.beginPath(); ctx.arc(screenX, screenY, hazeR, 0, Math.PI * 2); ctx.fill();
        }
        const emberCount = 24;
        for (let i = 0; i < emberCount; i++) {
            const angle = i * Math.PI * 2 / emberCount + pulseElapsed * 1.2 + p * 0.7;
            const wobble = Math.sin(elapsed * 6 + i * 2.5 + p) * bandWidth * 0.6;
            const dist = waveRadius + wobble;
            const px = screenX + Math.cos(angle) * dist, py = screenY + Math.sin(angle) * dist;
            const emberAlpha = alpha * (0.4 + Math.sin(elapsed * 8 + i * 3) * 0.3);
            const emberSize = Math.max(1, (3.5 - pulseElapsed * 1.2) * (0.6 + Math.random() * 0.4));
            ctx.fillStyle = `rgba(255, ${180 + Math.floor(Math.random() * 75)}, ${Math.floor(Math.random() * 60)}, ${emberAlpha})`;
            ctx.beginPath(); ctx.arc(px, py, emberSize, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = `rgba(${r}, ${g}, 0, ${emberAlpha * 0.3})`;
            ctx.beginPath(); ctx.arc(px, py, emberSize * 2.5, 0, Math.PI * 2); ctx.fill();
        }
    }
    const coreFade = Math.max(0, 1 - elapsed / (pulseCount * pulseInterval + pulseExpand));
    const coreAlpha = Math.max(0, 0.6 * Math.sin(elapsed * 4) * coreFade);
    if (coreAlpha > 0) {
        const outerGlow = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, 80);
        outerGlow.addColorStop(0, `rgba(255, 200, 100, ${coreAlpha * 0.4})`);
        outerGlow.addColorStop(0.5, `rgba(255, 100, 30, ${coreAlpha * 0.2})`);
        outerGlow.addColorStop(1, 'transparent');
        ctx.fillStyle = outerGlow; ctx.beginPath(); ctx.arc(screenX, screenY, 80, 0, Math.PI * 2); ctx.fill();
        const coreGrad = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, 30);
        coreGrad.addColorStop(0, `rgba(255, 255, 240, ${coreAlpha})`);
        coreGrad.addColorStop(0.6, `rgba(255, 180, 60, ${coreAlpha * 0.6})`);
        coreGrad.addColorStop(1, 'transparent');
        ctx.fillStyle = coreGrad; ctx.beginPath(); ctx.arc(screenX, screenY, 30, 0, Math.PI * 2); ctx.fill();
    }
}

function drawEarthquakeShake(progress) {
    if (progress > 0 && progress < 1) {
        const intensity = Math.sin(progress * Math.PI) * 8;
        ctx.translate((Math.random() - 0.5) * intensity, (Math.random() - 0.5) * intensity);
    }
}

function drawFrenzyOverlay(progress) {
    const pulse = Math.sin(Date.now() / 200) * 0.15 + 0.2;
    const thickness = 4;
    const ns = OrbArena.state;
    const w = canvas.width / ns.currentZoom, h = canvas.height / ns.currentZoom;
    ctx.fillStyle = `rgba(0, 255, 100, ${pulse})`;
    ctx.fillRect(0, 0, w, thickness);
    ctx.fillRect(0, h - thickness, w, thickness);
    ctx.fillRect(0, 0, thickness, h);
    ctx.fillRect(w - thickness, 0, thickness, h);
}

function renderDisasterEffects() {
    const state = OrbArena.state.state;
    if (!state.disaster) return;
    if (state.disaster.active === 'black_hole' && state.disaster.black_hole)
        drawBlackHole(state.disaster.black_hole, state.disaster.progress || 0);
    if (state.disaster.active === 'meteor_shower' && state.disaster.meteors)
        state.disaster.meteors.forEach(m => drawMeteorImpact(m));
    if (state.disaster.active === 'supernova' && state.disaster.supernova)
        drawSupernova(state.disaster.supernova);
}

// ── isOffScreen (used throughout draw functions) ──
function isOffScreen(screenX, screenY, margin) {
    const ns = OrbArena.state;
    return screenX < -margin || screenX > canvas.width / ns.currentZoom + margin ||
           screenY < -margin || screenY > canvas.height / ns.currentZoom + margin;
}

// ── Draw Functions ──

function drawGrid() {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    const gridSize = 50;
    ctx.strokeStyle = 'rgba(255, 140, 0, 0.045)'; ctx.lineWidth = 1;
    const vw = canvas.width / ns.currentZoom, vh = canvas.height / ns.currentZoom;
    const startX = -state.camera.x % gridSize, startY = -state.camera.y % gridSize;
    for (let x = startX; x < vw; x += gridSize) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, vh); ctx.stroke(); }
    for (let y = startY; y < vh; y += gridSize) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(vw, y); ctx.stroke(); }
}

function drawBoundary() {
    const state = OrbArena.state.state;
    const x = -state.camera.x, y = -state.camera.y;
    ctx.strokeStyle = 'rgba(122, 61, 0, 0.45)'; ctx.lineWidth = 2;
    ctx.setLineDash([8, 6]); ctx.strokeRect(x, y, state.world.width, state.world.height); ctx.setLineDash([]);
    const gLeft = ctx.createLinearGradient(x, y, x + 100, y);
    gLeft.addColorStop(0, 'rgba(255, 140, 0, 0.15)'); gLeft.addColorStop(1, 'transparent');
    ctx.fillStyle = gLeft; ctx.fillRect(x, y, 100, state.world.height);
    const gRight = ctx.createLinearGradient(x + state.world.width, y, x + state.world.width - 100, y);
    gRight.addColorStop(0, 'rgba(255, 140, 0, 0.15)'); gRight.addColorStop(1, 'transparent');
    ctx.fillStyle = gRight; ctx.fillRect(x + state.world.width - 100, y, 100, state.world.height);
    const gTop = ctx.createLinearGradient(x, y, x, y + 100);
    gTop.addColorStop(0, 'rgba(255, 140, 0, 0.15)'); gTop.addColorStop(1, 'transparent');
    ctx.fillStyle = gTop; ctx.fillRect(x, y, state.world.width, 100);
    const gBottom = ctx.createLinearGradient(x, y + state.world.height, x, y + state.world.height - 100);
    gBottom.addColorStop(0, 'rgba(255, 140, 0, 0.15)'); gBottom.addColorStop(1, 'transparent');
    ctx.fillStyle = gBottom; ctx.fillRect(x, y + state.world.height - 100, state.world.width, 100);
}

function drawEnergyOrb(orb) {
    const state = OrbArena.state.state;
    const screenX = orb.x - state.camera.x, screenY = orb.y - state.camera.y;
    if (isOffScreen(screenX, screenY, 50)) return;
    ctx.save();
    ctx.shadowBlur = 11; ctx.shadowColor = orb.color + 'aa';
    const orbGrad = ctx.createRadialGradient(screenX - orb.radius * 0.25, screenY - orb.radius * 0.25, orb.radius * 0.1, screenX, screenY, orb.radius);
    orbGrad.addColorStop(0, orb.color + 'ff'); orbGrad.addColorStop(1, orb.color);
    ctx.fillStyle = orbGrad;
    ctx.beginPath(); ctx.arc(screenX, screenY, orb.radius, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
}

function drawSpikeOrb(orb) {
    const state = OrbArena.state.state;
    const screenX = orb.x - state.camera.x, screenY = orb.y - state.camera.y;
    if (isOffScreen(screenX, screenY, 50)) return;
    ctx.save();
    ctx.shadowBlur = 8; ctx.shadowColor = 'rgba(255,34,0,0.6)';
    const spikeCount = 8, innerRadius = orb.radius * 0.55, outerRadius = orb.radius * 1.4;
    ctx.beginPath();
    for (let i = 0; i < spikeCount * 2; i++) {
        const angle = (i / (spikeCount * 2)) * Math.PI * 2 - Math.PI / 2;
        const radius = i % 2 === 0 ? outerRadius : innerRadius;
        const px = screenX + Math.cos(angle) * radius, py = screenY + Math.sin(angle) * radius;
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    }
    ctx.closePath(); ctx.fillStyle = '#661100'; ctx.fill();
    ctx.strokeStyle = '#ff2200'; ctx.lineWidth = 0.8; ctx.stroke();
    ctx.restore();
}

function drawGoldenOrb(orb) {
    const state = OrbArena.state.state;
    const screenX = orb.x - state.camera.x, screenY = orb.y - state.camera.y;
    if (isOffScreen(screenX, screenY, 50)) return;
    const glow = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, orb.radius * 4);
    glow.addColorStop(0, 'rgba(255, 215, 0, 0.6)'); glow.addColorStop(0.5, 'rgba(255, 180, 0, 0.3)'); glow.addColorStop(1, 'transparent');
    ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(screenX, screenY, orb.radius * 4, 0, Math.PI * 2); ctx.fill();
    const orbGrad = ctx.createRadialGradient(screenX - 3, screenY - 3, 0, screenX, screenY, orb.radius);
    orbGrad.addColorStop(0, '#fff7aa'); orbGrad.addColorStop(0.5, '#ffd700'); orbGrad.addColorStop(1, '#b8860b');
    ctx.fillStyle = orbGrad; ctx.beginPath(); ctx.arc(screenX, screenY, orb.radius, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#fff';
    const sparkleAngle = Date.now() / 200;
    for (let i = 0; i < 4; i++) {
        const angle = sparkleAngle + (i * Math.PI / 2);
        ctx.beginPath(); ctx.arc(screenX + Math.cos(angle) * orb.radius * 0.6, screenY + Math.sin(angle) * orb.radius * 0.6, 2, 0, Math.PI * 2); ctx.fill();
    }
}

function drawPowerUpOrb(orb) {
    const state = OrbArena.state.state;
    const screenX = orb.x - state.camera.x, screenY = orb.y - state.camera.y;
    if (isOffScreen(screenX, screenY, 60)) return;
    const t = Date.now() / 1000, pulse = 1 + Math.sin(t * 3) * 0.08;
    ctx.save();
    ctx.shadowBlur = 14 + Math.sin(t * 3) * 6; ctx.shadowColor = 'rgba(255,0,136,0.7)';
    const orbGrad = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, orb.radius * pulse);
    orbGrad.addColorStop(0, '#ff88cc'); orbGrad.addColorStop(1, '#cc0066');
    ctx.fillStyle = orbGrad; ctx.beginPath(); ctx.arc(screenX, screenY, orb.radius * pulse, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur = 0; ctx.strokeStyle = 'rgba(255,100,180,0.5)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(screenX, screenY, orb.radius * pulse * 0.6, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();
    ctx.fillStyle = '#fff'; ctx.font = `bold ${orb.radius * 1.2}px "Share Tech Mono", monospace`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('?', screenX, screenY + 1);
}

function drawMinePickup(pickup) {
    const state = OrbArena.state.state;
    const screenX = pickup.x - state.camera.x, screenY = pickup.y - state.camera.y;
    if (isOffScreen(screenX, screenY, pickup.radius * 2)) return;
    const pulse = Math.sin(Date.now() / 200) * 0.3 + 0.7;
    const glow = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, pickup.radius * 2);
    glow.addColorStop(0, `rgba(150, 150, 150, ${pulse})`); glow.addColorStop(1, 'transparent');
    ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(screenX, screenY, pickup.radius * 2, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#666'; ctx.beginPath(); ctx.arc(screenX, screenY, pickup.radius, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#cc0000'; ctx.font = `bold ${pickup.radius * 1.3}px Arial`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('✦', screenX, screenY);
}

function drawMine(mine) {
    const state = OrbArena.state.state;
    const screenX = mine.x - state.camera.x, screenY = mine.y - state.camera.y;
    if (isOffScreen(screenX, screenY, mine.radius * 2)) return;
    const flash = mine.armed ? (Math.sin(Date.now() / 150) * 0.5 + 0.5) : 0.3;
    ctx.strokeStyle = `rgba(255, 100, 0, ${flash})`; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(screenX, screenY, mine.radius + 10, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = mine.color; ctx.beginPath(); ctx.arc(screenX, screenY, mine.radius, 0, Math.PI * 2); ctx.fill();
    for (let i = 0; i < 8; i++) {
        const angle = i * Math.PI / 4;
        ctx.beginPath(); ctx.moveTo(screenX, screenY);
        ctx.lineTo(screenX + Math.cos(angle) * mine.radius * 1.5, screenY + Math.sin(angle) * mine.radius * 1.5);
        ctx.strokeStyle = '#ff3300'; ctx.lineWidth = 2; ctx.stroke();
    }
}

function drawTrailSegments() {
    const state = OrbArena.state.state;
    const segments = state.trailSegments;
    if (!segments || segments.length === 0) return;
    for (const seg of segments) {
        const screenX = seg.x - state.camera.x, screenY = seg.y - state.camera.y;
        if (isOffScreen(screenX, screenY, 24)) continue;
        const alpha = Math.min(1, seg.ttl / 5.0);
        const glow = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, 22);
        glow.addColorStop(0, `${seg.color}${Math.round(alpha * 0.6 * 255).toString(16).padStart(2, '0')}`);
        glow.addColorStop(0.5, `${seg.color}${Math.round(alpha * 0.2 * 255).toString(16).padStart(2, '0')}`);
        glow.addColorStop(1, 'transparent');
        ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(screenX, screenY, 22, 0, Math.PI * 2); ctx.fill();
        ctx.save();
        ctx.globalAlpha = alpha * 0.9; ctx.shadowColor = seg.color; ctx.shadowBlur = 16;
        ctx.fillStyle = seg.color; ctx.beginPath(); ctx.arc(screenX, screenY, 8, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = alpha * 0.7; ctx.shadowBlur = 6; ctx.fillStyle = '#ffffff';
        ctx.beginPath(); ctx.arc(screenX, screenY, 3.5, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
    }
}

function drawWormholePortal(portal) {
    const state = OrbArena.state.state;
    const screenX = portal.x - state.camera.x, screenY = portal.y - state.camera.y;
    const r = 22;
    if (isOffScreen(screenX, screenY, r + 40)) return;
    ctx.save();
    const t = Date.now() / 1000;
    const glowGrad = ctx.createRadialGradient(screenX, screenY, r, screenX, screenY, r + 30);
    glowGrad.addColorStop(0, 'rgba(0, 200, 160, 0.25)'); glowGrad.addColorStop(1, 'transparent');
    ctx.fillStyle = glowGrad; ctx.beginPath(); ctx.arc(screenX, screenY, r + 30, 0, Math.PI * 2); ctx.fill();
    for (let i = 0; i < 2; i++) {
        const ringR = r * (1.4 + i * 0.7);
        ctx.save();
        ctx.strokeStyle = `rgba(0, 210, 170, ${0.4 - i * 0.1})`; ctx.lineWidth = 1.5;
        ctx.translate(screenX, screenY); ctx.rotate(t * (1.5 + i * 0.4) + i); ctx.scale(1, 0.4);
        ctx.beginPath(); ctx.arc(0, 0, ringR, 0, Math.PI * 2); ctx.stroke();
        ctx.restore();
    }
    const coreGrad = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, r);
    coreGrad.addColorStop(0, 'rgba(0, 0, 0, 1)'); coreGrad.addColorStop(0.7, 'rgba(0, 0, 0, 0.95)');
    coreGrad.addColorStop(1, 'rgba(0, 40, 30, 0.8)');
    ctx.fillStyle = coreGrad; ctx.beginPath(); ctx.arc(screenX, screenY, r, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = `rgba(0, 230, 180, ${0.6 + Math.sin(t * 6) * 0.2})`; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(screenX, screenY, r + 1, 0, Math.PI * 2); ctx.stroke();
    for (let i = 0; i < 6; i++) {
        const angle = t * 2.5 + i * Math.PI / 3;
        const dist = r + 5 + Math.sin(t * 3 + i) * 3;
        ctx.fillStyle = `rgba(0, 220, 180, ${0.7 + Math.sin(t * 4 + i) * 0.3})`;
        ctx.beginPath(); ctx.arc(screenX + Math.cos(angle) * dist, screenY + Math.sin(angle) * dist, 2, 0, Math.PI * 2); ctx.fill();
    }
    if (portal.traveling) {
        const trailGrad = ctx.createLinearGradient(screenX, screenY, screenX - portal.dx * 30, screenY - portal.dy * 30);
        trailGrad.addColorStop(0, 'rgba(0, 200, 160, 0.4)'); trailGrad.addColorStop(1, 'transparent');
        ctx.strokeStyle = trailGrad; ctx.lineWidth = r * 0.8; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(screenX, screenY); ctx.lineTo(screenX - portal.dx * 30, screenY - portal.dy * 30); ctx.stroke();
    }
    ctx.restore();
}

function drawWormholeExit(worldX, worldY, progress) {
    const state = OrbArena.state.state;
    const screenX = worldX - state.camera.x, screenY = worldY - state.camera.y;
    const r = 22;
    if (isOffScreen(screenX, screenY, r + 60)) return;
    const scale = 1 + progress * 1.5, alpha = 1 - progress;
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.strokeStyle = 'rgba(0, 230, 180, 0.9)'; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(screenX, screenY, r * scale, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = 'rgba(100, 255, 220, 0.5)'; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(screenX, screenY, r * scale * 1.6, 0, Math.PI * 2); ctx.stroke();
    if (progress < 0.3) {
        const flashAlpha = (0.3 - progress) / 0.3;
        const coreGrad = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, r * 1.5);
        coreGrad.addColorStop(0, `rgba(200, 255, 240, ${flashAlpha})`); coreGrad.addColorStop(1, 'transparent');
        ctx.fillStyle = coreGrad; ctx.beginPath(); ctx.arc(screenX, screenY, r * 1.5, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
}

function drawProjectile(proj) {
    const state = OrbArena.state.state;
    const screenX = proj.x - state.camera.x, screenY = proj.y - state.camera.y;
    if (isOffScreen(screenX, screenY, 30)) return;
    if (proj.owner_id === 'strike') {
        const angle = Math.atan2(proj.dy, proj.dx);
        ctx.strokeStyle = 'rgba(255, 80, 0, 0.75)'; ctx.lineWidth = 8; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(screenX, screenY); ctx.lineTo(screenX - Math.cos(angle) * 28, screenY - Math.sin(angle) * 28); ctx.stroke();
        ctx.save(); ctx.translate(screenX, screenY); ctx.rotate(angle);
        ctx.fillStyle = '#ff3300'; ctx.fillRect(-12, -4, 24, 8);
        ctx.beginPath(); ctx.moveTo(12, 0); ctx.lineTo(19, -4); ctx.lineTo(19, 4); ctx.closePath(); ctx.fill();
        ctx.restore();
        const glow = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, 22);
        glow.addColorStop(0, 'rgba(255, 60, 0, 0.65)'); glow.addColorStop(1, 'transparent');
        ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(screenX, screenY, 22, 0, Math.PI * 2); ctx.fill();
        return;
    }
    if (proj.homing) {
        const angle = Math.atan2(proj.dy, proj.dx);
        ctx.strokeStyle = 'rgba(255, 150, 0, 0.6)'; ctx.lineWidth = 8;
        ctx.beginPath(); ctx.moveTo(screenX, screenY); ctx.lineTo(screenX - Math.cos(angle) * 20, screenY - Math.sin(angle) * 20); ctx.stroke();
        ctx.save(); ctx.translate(screenX, screenY); ctx.rotate(angle);
        ctx.fillStyle = proj.color; ctx.fillRect(-12, -4, 24, 8);
        ctx.beginPath(); ctx.moveTo(12, 0); ctx.lineTo(18, -4); ctx.lineTo(18, 4); ctx.closePath(); ctx.fill();
        ctx.restore();
        const glow = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, 20);
        glow.addColorStop(0, 'rgba(255, 200, 0, 0.6)'); glow.addColorStop(1, 'transparent');
        ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(screenX, screenY, 20, 0, Math.PI * 2); ctx.fill();
    } else {
        const glow = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, proj.radius * 3);
        glow.addColorStop(0, proj.color + '80'); glow.addColorStop(1, 'transparent');
        ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(screenX, screenY, proj.radius * 3, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = proj.color; ctx.beginPath(); ctx.arc(screenX, screenY, proj.radius, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = 'rgba(255, 255, 255, 0.8)'; ctx.beginPath(); ctx.arc(screenX, screenY, proj.radius * 0.4, 0, Math.PI * 2); ctx.fill();
    }
}

function drawTrack() {
    const state = OrbArena.state.state;
    const wps = state.welcomeTrackWaypoints;
    if (!wps || wps.length < 2) return;
    const HALF_W = 175;
    ctx.save();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.07)'; ctx.lineWidth = HALF_W * 2; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(wps[0][0] - state.camera.x, wps[0][1] - state.camera.y);
    for (let i = 1; i < wps.length; i++) ctx.lineTo(wps[i][0] - state.camera.x, wps[i][1] - state.camera.y);
    ctx.stroke();
    ctx.strokeStyle = 'rgba(255, 255, 100, 0.12)'; ctx.lineWidth = 3; ctx.setLineDash([40, 60]);
    ctx.beginPath(); ctx.moveTo(wps[0][0] - state.camera.x, wps[0][1] - state.camera.y);
    for (let i = 1; i < wps.length; i++) ctx.lineTo(wps[i][0] - state.camera.x, wps[i][1] - state.camera.y);
    ctx.stroke(); ctx.setLineDash([]);
    const sfX = wps[0][0], sfY = wps[0][1];
    const tdx = wps[1][0] - sfX, tdy = wps[1][1] - sfY;
    const tLen = Math.sqrt(tdx * tdx + tdy * tdy);
    const tux = tdx / tLen, tuy = tdy / tLen;
    const tnx = -tuy, tny = tux;
    const trackAngle = Math.atan2(tuy, tux);
    const sqH = 50, sqW = 16, count = Math.round(HALF_W * 2 / sqH);
    for (let i = 0; i < count; i++) {
        const t = -HALF_W + sqH * i + sqH / 2;
        const bx = (sfX + tnx * t) - state.camera.x, by = (sfY + tny * t) - state.camera.y;
        ctx.save(); ctx.translate(bx, by); ctx.rotate(trackAngle);
        ctx.fillStyle = i % 2 === 0 ? 'rgba(255,255,255,0.82)' : 'rgba(0,0,0,0.70)';
        ctx.fillRect(-sqW / 2, -sqH / 2, sqW, sqH); ctx.restore();
    }
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.55)'; ctx.lineWidth = 2; ctx.lineCap = 'butt';
    ctx.beginPath();
    ctx.moveTo((sfX + tnx * HALF_W) - state.camera.x, (sfY + tny * HALF_W) - state.camera.y);
    ctx.lineTo((sfX - tnx * HALF_W) - state.camera.x, (sfY - tny * HALF_W) - state.camera.y);
    ctx.stroke();
    ctx.restore();
}

function drawCheckpointArrow() {
    const state = OrbArena.state.state;
    if (!state.you || !state.challengeData || state.challengeData.type !== 'rally_run') return;
    const cpIdx = state.challengeData.checkpoint;
    const orb = state.goldenOrbs && state.goldenOrbs.find(o => o.id === `checkpoint_${cpIdx}`);
    if (!orb) return;
    const px = state.you.x - state.camera.x, py = state.you.y - state.camera.y;
    const ox = orb.x - state.camera.x, oy = orb.y - state.camera.y;
    const dx = ox - px, dy = oy - py;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 80) return;
    const angle = Math.atan2(dy, dx);
    const arrowDist = state.you.radius + 35;
    ctx.save();
    ctx.translate(px + Math.cos(angle) * arrowDist, py + Math.sin(angle) * arrowDist);
    ctx.rotate(angle); ctx.fillStyle = 'rgba(255, 215, 0, 0.75)';
    ctx.beginPath(); ctx.moveTo(12, 0); ctx.lineTo(-8, -7); ctx.lineTo(-4, 0); ctx.lineTo(-8, 7); ctx.closePath(); ctx.fill();
    ctx.restore();
}

function drawRallyCountdown() {
    const state = OrbArena.state.state;
    if (!state.challengeData || state.challengeData.type !== 'rally_run') return;
    const countdown = state.challengeData.countdown || 0;
    const now = Date.now();
    const showGo = state.rallyGoUntil && now < state.rallyGoUntil;
    if (countdown <= 0 && !showGo) return;
    const cx = canvas.width / 2, cy = canvas.height / 2;
    let text, alpha, scale, glowColor;
    if (showGo) {
        const t = (now - (state.rallyGoUntil - 900)) / 900;
        text = 'GO!'; alpha = Math.max(0, 1 - t); scale = 1.0 + t * 0.5; glowColor = '#00ff88';
    } else {
        const digit = Math.ceil(countdown);
        const sinceAppeared = now - (state.rallyCountdownDigitTime || now);
        const scaleT = Math.min(1, sinceAppeared / 300);
        scale = 1.6 - scaleT * 0.6;
        alpha = sinceAppeared < 700 ? 1.0 : Math.max(0, 1 - (sinceAppeared - 700) / 250);
        text = String(digit); glowColor = '#ff6600';
    }
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, alpha));
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const fontSize = Math.round(canvas.height * 0.22 * scale);
    ctx.font = `900 ${fontSize}px 'Segoe UI', Arial, sans-serif`;
    ctx.shadowColor = glowColor; ctx.shadowBlur = 60;
    ctx.strokeStyle = 'rgba(0,0,0,0.85)'; ctx.lineWidth = Math.max(4, Math.round(fontSize / 10));
    ctx.strokeText(text, cx, cy);
    ctx.fillStyle = '#ffffff'; ctx.fillText(text, cx, cy);
    ctx.restore();
}

function drawTurret(turret, active) {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    const sx = turret.x - state.camera.x, sy = turret.y - state.camera.y;
    const vw = canvas.width / ns.currentZoom, vh = canvas.height / ns.currentZoom;
    if (sx < -60 || sx > vw + 60 || sy < -60 || sy > vh + 60) return;
    const size = 20;
    const angle = Math.atan2(2500 - turret.y, 2500 - turret.x);
    ctx.save(); ctx.translate(sx, sy); ctx.rotate(angle);
    if (active) { ctx.shadowColor = '#ff3300'; ctx.shadowBlur = 18; }
    ctx.fillStyle = active ? '#441100' : '#220a00'; ctx.strokeStyle = active ? '#ff4400' : '#553300'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(0, 0, size, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = active ? '#ff3300' : '#663300';
    ctx.beginPath(); ctx.moveTo(size + 4, 0); ctx.lineTo(-size * 0.5, -size * 0.55); ctx.lineTo(-size * 0.5, size * 0.55); ctx.closePath(); ctx.fill();
    ctx.shadowBlur = 0; ctx.restore();
    if (active && state.you) {
        const dx = turret.x - state.you.x, dy = turret.y - state.you.y;
        if (dx * dx + dy * dy < 600 * 600) {
            ctx.save(); ctx.font = `${Math.max(9, 11 / ns.currentZoom)}px Segoe UI`;
            ctx.textAlign = 'center'; ctx.fillStyle = 'rgba(255,80,0,0.7)';
            ctx.fillText('TURRET', sx, sy + size + 14); ctx.restore();
        }
    }
}

function drawBoss(boss) {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    if (!boss) return;
    const sx = boss.x - state.camera.x, sy = boss.y - state.camera.y, r = boss.radius;
    const vw = canvas.width / ns.currentZoom, vh = canvas.height / ns.currentZoom;
    if (sx + r < -50 || sx - r > vw + 50 || sy + r < -50 || sy - r > vh + 50) return;
    const now = Date.now(), pulse = 0.5 + 0.5 * Math.sin(now / 400), weakened = boss.weakened;
    ctx.save();
    ctx.shadowColor = weakened ? '#00ff88' : '#cc0000'; ctx.shadowBlur = 30 + pulse * 20;
    ctx.beginPath(); ctx.arc(sx, sy, r + 6 + pulse * 6, 0, Math.PI * 2);
    ctx.strokeStyle = weakened ? `rgba(0,255,136,${0.3 + pulse * 0.3})` : `rgba(200,0,0,${0.3 + pulse * 0.3})`; ctx.lineWidth = 2; ctx.stroke();
    const grad = ctx.createRadialGradient(sx - r * 0.3, sy - r * 0.3, r * 0.1, sx, sy, r);
    if (weakened) { grad.addColorStop(0, '#004422'); grad.addColorStop(0.5, '#001a0e'); grad.addColorStop(1, '#000a06'); }
    else { grad.addColorStop(0, '#440000'); grad.addColorStop(0.5, '#1a0000'); grad.addColorStop(1, '#0a0000'); }
    ctx.beginPath(); ctx.arc(sx, sy, r, 0, Math.PI * 2); ctx.fillStyle = grad; ctx.fill();
    ctx.strokeStyle = weakened ? `rgba(0,255,136,${0.6 + pulse * 0.4})` : `rgba(200,0,0,${0.6 + pulse * 0.4})`; ctx.lineWidth = 3; ctx.stroke();
    ctx.shadowBlur = 0; ctx.strokeStyle = weakened ? 'rgba(0,255,136,0.15)' : 'rgba(200,0,0,0.15)'; ctx.lineWidth = 1;
    for (let i = -1; i <= 1; i++) {
        ctx.beginPath(); ctx.moveTo(sx + i * r * 0.5, sy - r * 0.9); ctx.lineTo(sx + i * r * 0.5, sy + r * 0.9); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(sx - r * 0.9, sy + i * r * 0.5); ctx.lineTo(sx + r * 0.9, sy + i * r * 0.5); ctx.stroke();
    }
    if (boss.shielded) {
        const sPulse = 0.5 + 0.5 * Math.sin(now / 150);
        ctx.beginPath(); ctx.arc(sx, sy, r + 18 + sPulse * 8, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(255,220,80,${0.7 + sPulse * 0.3})`; ctx.lineWidth = 3 + sPulse * 2;
        ctx.shadowColor = '#ffdd44'; ctx.shadowBlur = 25 + sPulse * 15; ctx.stroke();
        ctx.beginPath(); ctx.arc(sx, sy, r + 8, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(255,200,50,${0.4 + sPulse * 0.3})`; ctx.lineWidth = 1.5; ctx.stroke();
    }
    ctx.shadowColor = weakened ? '#00ff88' : '#cc0000'; ctx.shadowBlur = 8;
    ctx.font = `bold ${Math.max(10, 14 / ns.currentZoom)}px Orbitron, monospace`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillStyle = weakened ? '#00ff88' : '#ff2200'; ctx.fillText(weakened ? 'SLOWED' : 'HUNTER', sx, sy);
    ctx.restore();
    if (state.you) {
        const dx = boss.x - state.you.x, dy = boss.y - state.you.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > 800) {
            const angle = Math.atan2(dy, dx);
            const edgeX = canvas.width / 2 / ns.currentZoom + Math.cos(angle) * (Math.min(canvas.width, canvas.height) / ns.currentZoom * 0.42);
            const edgeY = canvas.height / 2 / ns.currentZoom + Math.sin(angle) * (Math.min(canvas.width, canvas.height) / ns.currentZoom * 0.42);
            ctx.save(); ctx.shadowColor = '#cc0000'; ctx.shadowBlur = 12;
            ctx.beginPath(); ctx.translate(edgeX, edgeY); ctx.rotate(angle);
            ctx.moveTo(10, 0); ctx.lineTo(-8, -7); ctx.lineTo(-8, 7); ctx.closePath();
            ctx.fillStyle = weakened ? 'rgba(0,255,136,0.8)' : `rgba(200,0,0,${0.5 + pulse * 0.4})`; ctx.fill();
            ctx.restore();
        }
    }
}

function drawStrikeReticle(target, phase) {
    const state = OrbArena.state.state;
    const sx = target[0] - state.camera.x, sy = target[1] - state.camera.y;
    const now = Date.now(), pulse = 0.5 + 0.5 * Math.sin(now / 200), scatter = 50;
    const isBarrage = phase === 'barrage', isDanger = phase === 'danger_close';
    const retColor = (isDanger || isBarrage) ? '#ff1100' : '#ff8800';
    const fastPulse = 0.5 + 0.5 * Math.sin(now / ((isDanger || isBarrage) ? 80 : 200));
    ctx.save(); ctx.shadowColor = retColor; ctx.shadowBlur = isBarrage ? 22 : 12;
    if (isDanger || isBarrage) {
        const zoneFill = ctx.createRadialGradient(sx, sy, 0, sx, sy, scatter);
        zoneFill.addColorStop(0, `rgba(255,0,0,${0.08 + fastPulse * 0.08})`); zoneFill.addColorStop(1, 'transparent');
        ctx.fillStyle = zoneFill; ctx.beginPath(); ctx.arc(sx, sy, scatter, 0, Math.PI * 2); ctx.fill();
    }
    ctx.beginPath(); ctx.arc(sx, sy, scatter, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(255,${(isDanger || isBarrage) ? 30 : 120},0,${0.35 + fastPulse * 0.35})`;
    ctx.lineWidth = (isDanger || isBarrage) ? 2 : 1; ctx.setLineDash([6, 6]); ctx.stroke(); ctx.setLineDash([]);
    ctx.strokeStyle = `rgba(255,${(isDanger || isBarrage) ? 20 : 80},0,${0.7 + fastPulse * 0.3})`;
    ctx.lineWidth = (isDanger || isBarrage) ? 2 : 1.5;
    const cs = 28;
    ctx.beginPath(); ctx.moveTo(sx - cs, sy); ctx.lineTo(sx + cs, sy); ctx.moveTo(sx, sy - cs); ctx.lineTo(sx, sy + cs); ctx.stroke();
    ctx.beginPath(); ctx.arc(sx, sy, 5 + fastPulse * 4, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255,${(isDanger || isBarrage) ? 20 : 80},0,${0.8 + fastPulse * 0.2})`; ctx.fill();
    const bl = 16;
    for (const [dx, dy] of [[-1,-1],[1,-1],[1,1],[-1,1]]) {
        const bx = sx + dx * (scatter - 2), by = sy + dy * (scatter - 2);
        ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx - dx * bl, by); ctx.moveTo(bx, by); ctx.lineTo(bx, by - dy * bl);
        ctx.strokeStyle = `rgba(255,${(isDanger || isBarrage) ? 20 : 100},0,${0.6 + fastPulse * 0.4})`; ctx.lineWidth = 2; ctx.stroke();
    }
    ctx.restore();
}

function drawStrikeAlert() {
    const state = OrbArena.state.state;
    if (state.connectionMode !== 'challenge' || state.challengeName !== 'boss_hunt') return;
    const cd = state.challengeData;
    if (!cd || !cd.strike_phase || cd.strike_phase === 'barrage') return;
    const phase = cd.strike_phase, now = Date.now(), pulse = 0.5 + 0.5 * Math.sin(now / 120);
    const cx = canvas.width / 2, cy = canvas.height / 2;
    const lines = {
        targeting:    { top: 'TARGET',       bottom: 'ACQUIRED',      color: '#ff8800', size: 1.0 },
        cleared_hot:  { top: 'CLEARED HOT',  bottom: 'CORNER BUSTER', color: '#ff5500', size: 1.05 },
        danger_close: { top: 'DANGER',        bottom: 'CLOSE',         color: '#ff1100', size: 1.15 },
    };
    const cfg = lines[phase]; if (!cfg) return;
    ctx.save();
    if (phase === 'danger_close') {
        const vAlpha = 0.08 + pulse * 0.12;
        const vGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(canvas.width, canvas.height) * 0.7);
        vGrad.addColorStop(0, 'rgba(255,0,0,0)'); vGrad.addColorStop(1, `rgba(255,0,0,${vAlpha})`);
        ctx.fillStyle = vGrad; ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    const scale = cfg.size * (phase === 'danger_close' ? (0.95 + pulse * 0.1) : 1.0);
    const topSize = Math.min(Math.round(canvas.height * 0.028 * scale), 22);
    const botSize = Math.min(Math.round(canvas.height * 0.042 * scale), 34);
    const orbScreenR = (state.you ? state.you.radius : 20) * OrbArena.state.currentZoom;
    const rawAlertY = canvas.height / 2 - orbScreenR - 14 - (topSize + botSize * 1.2);
    const alertY = Math.max(topSize + 6, rawAlertY);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = `700 ${topSize}px Orbitron, monospace`; ctx.shadowColor = cfg.color; ctx.shadowBlur = 20 + pulse * 15;
    ctx.fillStyle = cfg.color; ctx.globalAlpha = 0.75 + pulse * 0.25; ctx.fillText(cfg.top, cx, alertY);
    ctx.font = `900 ${botSize}px Orbitron, monospace`; ctx.shadowBlur = 30 + pulse * 20;
    ctx.globalAlpha = 0.85 + pulse * 0.15; ctx.fillText(cfg.bottom, cx, alertY + botSize * 1.1);
    const dashW = canvas.width * 0.08, dashY = alertY + botSize * 0.55;
    ctx.globalAlpha = 0.4 + pulse * 0.3; ctx.strokeStyle = cfg.color; ctx.lineWidth = 2; ctx.shadowBlur = 8;
    const textHalfW = ctx.measureText(cfg.bottom).width / 2 + 20;
    ctx.beginPath();
    ctx.moveTo(cx - textHalfW - dashW, dashY); ctx.lineTo(cx - textHalfW, dashY);
    ctx.moveTo(cx + textHalfW, dashY); ctx.lineTo(cx + textHalfW + dashW, dashY);
    ctx.stroke(); ctx.restore();
}

function drawWall(wall) {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    const screenX = wall.x - state.camera.x, screenY = wall.y - state.camera.y;
    if (screenX + wall.width < 0 || screenX > canvas.width / ns.currentZoom ||
        screenY + wall.height < 0 || screenY > canvas.height / ns.currentZoom) return;
    ctx.fillStyle = 'rgb(40,20,6)'; ctx.fillRect(screenX, screenY, wall.width, wall.height);
    const hp = wall.hp || 0, maxHp = wall.max_hp || 0;
    if (maxHp > 1 && hp < maxHp) {
        ctx.strokeStyle = hp === 2 ? '#ffaa00' : '#ff3333'; ctx.lineWidth = 4;
        ctx.strokeRect(screenX - 1, screenY - 1, wall.width + 2, wall.height + 2);
    } else {
        ctx.strokeStyle = 'rgba(255,140,0,0.6)'; ctx.lineWidth = 1; ctx.strokeRect(screenX, screenY, wall.width, wall.height);
    }
    const mk = 4; ctx.strokeStyle = 'rgba(255,140,0,0.5)'; ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(screenX + mk, screenY); ctx.lineTo(screenX, screenY); ctx.lineTo(screenX, screenY + mk);
    ctx.moveTo(screenX + wall.width - mk, screenY); ctx.lineTo(screenX + wall.width, screenY); ctx.lineTo(screenX + wall.width, screenY + mk);
    ctx.moveTo(screenX, screenY + wall.height - mk); ctx.lineTo(screenX, screenY + wall.height); ctx.lineTo(screenX + mk, screenY + wall.height);
    ctx.moveTo(screenX + wall.width - mk, screenY + wall.height); ctx.lineTo(screenX + wall.width, screenY + wall.height); ctx.lineTo(screenX + wall.width, screenY + wall.height - mk);
    ctx.stroke();
}

function drawKillFeed() {
    const state = OrbArena.state.state;
    if (!state.killFeed || state.killFeed.length === 0) return;
    ctx.font = 'bold 13px Segoe UI'; ctx.textAlign = 'left';
    const isMob = window.innerWidth <= 768;
    const startY = 60 + (isMob ? 100 : 150) + 14;
    state.killFeed.forEach((kill, index) => {
        const y = startY + index * 22, alpha = 0.9 - (index * 0.12);
        const isExplosion = kill.victim.includes('(exploded)');
        if (isExplosion) {
            const text = `${kill.killer} EXPLODED!`;
            ctx.fillStyle = `rgba(80, 0, 0, ${alpha * 0.6})`; ctx.fillRect(15, y - 14, ctx.measureText(text).width + 10, 20);
            ctx.fillStyle = `rgba(255, 150, 50, ${alpha})`; ctx.fillText(text, 20, y);
        } else {
            const text = `${kill.killer} consumed ${kill.victim}`;
            ctx.fillStyle = `rgba(0, 0, 0, ${alpha * 0.5})`; ctx.fillRect(15, y - 14, ctx.measureText(text).width + 10, 20);
            ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`; ctx.fillText(kill.killer, 20, y);
            const kw = ctx.measureText(kill.killer).width;
            ctx.fillStyle = `rgba(255, 100, 100, ${alpha})`; ctx.fillText(' consumed ', 20 + kw, y);
            const cw = ctx.measureText(kill.killer + ' consumed ').width;
            ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`; ctx.fillText(kill.victim, 20 + cw, y);
        }
    });
}

function drawHudBar(x, y, width, ready, fillColor, glowColor, label) {
    const trackH = 6;
    ctx.font = '700 11px "Share Tech Mono", monospace'; ctx.textAlign = 'left';
    ctx.fillStyle = ready ? fillColor : 'rgba(122,61,0,0.7)'; ctx.fillText(label, x, y - 6);
    ctx.fillStyle = 'rgba(255,140,0,0.1)'; ctx.fillRect(x, y, width, trackH);
    ctx.strokeStyle = 'rgba(255,140,0,0.15)'; ctx.lineWidth = 1; ctx.strokeRect(x, y, width, trackH);
    if (ready) {
        ctx.save(); ctx.shadowBlur = 8; ctx.shadowColor = glowColor;
        ctx.fillStyle = fillColor; ctx.fillRect(x, y, width, trackH); ctx.restore();
    }
}

function drawBoostIndicator() {
    const state = OrbArena.state.state;
    if (!state.you || !state.you.alive || isMobile()) return;
    const x = 20, y = canvas.height - 60;
    const boostLabel = state.you.wormhole_held ? 'WORMHOLE' : state.you.trail_held ? 'BOOST+TRAIL' : 'BOOST';
    drawHudBar(x, y, 180, state.you.boost_ready, '#ff8c00', 'rgba(255,140,0,0.5)', boostLabel);
    if (state.you.is_boosting) {
        ctx.fillStyle = '#ffb347'; ctx.font = '700 11px "Share Tech Mono", monospace'; ctx.fillText('BOOSTING', x + 192, y + 6);
    }
    const canShoot = state.you.shoot_ready && state.you.radius >= OrbArena.config.PROJECTILE_MIN_RADIUS;
    const shootLabel = state.you.radius < OrbArena.config.PROJECTILE_MIN_RADIUS ? 'GROW' : 'FIRE';
    drawHudBar(x, y - 32, 180, canShoot, '#ff2200', 'rgba(255,34,0,0.5)', shootLabel);
}

function drawPowerUpPopup() {
    const state = OrbArena.state.state;
    if (!state.powerupPopup || !state.you || !state.you.alive) return;
    const elapsed = Date.now() - state.powerupPopup.time;
    if (elapsed > 2000) { state.powerupPopup = null; return; }
    const alpha = Math.max(0, 1 - elapsed / 2000), rise = elapsed * 0.03;
    const screenX = state.you.x - state.camera.x;
    const screenY = state.you.y - state.camera.y - state.you.radius - 40 - rise;
    const pu = OrbArena.config.POWERUP_COLORS[state.you.active_powerup];
    const color = pu ? pu.text : '#fff';
    ctx.font = 'bold 22px Segoe UI'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.globalAlpha = alpha; ctx.fillStyle = color;
    ctx.fillText(state.powerupPopup.text + '!', screenX, screenY);
    ctx.globalAlpha = 1;
}

function drawTouchIndicator() {
    const ns = OrbArena.state;
    if (!ns.touchOrigin || !ns.touchCurrent) return;
    const deltaX = ns.touchCurrent.x - ns.touchOrigin.x, deltaY = ns.touchCurrent.y - ns.touchOrigin.y;
    const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(ns.touchOrigin.x, ns.touchOrigin.y, 50, 0, Math.PI * 2); ctx.stroke();
    if (distance > 10) {
        ctx.strokeStyle = 'rgba(0, 255, 255, 0.5)'; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(ns.touchOrigin.x, ns.touchOrigin.y); ctx.lineTo(ns.touchCurrent.x, ns.touchCurrent.y); ctx.stroke();
        const angle = Math.atan2(deltaY, deltaX), arrowSize = 12;
        ctx.fillStyle = 'rgba(0, 255, 255, 0.7)';
        ctx.beginPath(); ctx.moveTo(ns.touchCurrent.x, ns.touchCurrent.y);
        ctx.lineTo(ns.touchCurrent.x - arrowSize * Math.cos(angle - 0.4), ns.touchCurrent.y - arrowSize * Math.sin(angle - 0.4));
        ctx.lineTo(ns.touchCurrent.x - arrowSize * Math.cos(angle + 0.4), ns.touchCurrent.y - arrowSize * Math.sin(angle + 0.4));
        ctx.closePath(); ctx.fill();
    }
    ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
    ctx.beginPath(); ctx.arc(ns.touchOrigin.x, ns.touchOrigin.y, 8, 0, Math.PI * 2); ctx.fill();
}

function drawInvincibilityEffect(screenX, screenY, player) {
    const pulse = Math.sin(Date.now() / 100) * 0.3 + 0.7;
    ctx.strokeStyle = `rgba(100, 200, 255, ${pulse})`; ctx.lineWidth = 4;
    ctx.beginPath(); ctx.arc(screenX, screenY, player.radius + 15, 0, Math.PI * 2); ctx.stroke();
    const shieldGlow = ctx.createRadialGradient(screenX, screenY, player.radius, screenX, screenY, player.radius + 20);
    shieldGlow.addColorStop(0, 'transparent');
    shieldGlow.addColorStop(0.5, `rgba(100, 200, 255, ${pulse * 0.3})`);
    shieldGlow.addColorStop(1, 'transparent');
    ctx.fillStyle = shieldGlow; ctx.beginPath(); ctx.arc(screenX, screenY, player.radius + 20, 0, Math.PI * 2); ctx.fill();
}

function drawCriticalMassEffect(screenX, screenY, player) {
    const remaining = player.critical_mass_remaining;
    const pulseSpeed = remaining < 5 ? 50 : remaining < 10 ? 80 : 150;
    const pulse = Math.sin(Date.now() / pulseSpeed) * 0.4 + 0.6;
    const urgency = Math.max(0, 1 - remaining / 30);
    let wR, wG, wB;
    if (remaining > 20) { wR = 0; wG = 255; wB = 100; }
    else if (remaining > 10) { wR = 255; wG = 200; wB = 0; }
    else { wR = 255; wG = 50; wB = 50; }
    const breathSpeed = 800 - urgency * 500;
    const breathT = (Math.sin(Date.now() / breathSpeed) + 1) / 2;
    const auraMin = player.radius + 15, auraMax = player.radius + 25 + urgency * 30;
    const auraRadius = auraMin + breathT * (auraMax - auraMin);
    const auraAlpha = (0.1 + urgency * 0.3) * pulse;
    const auraGrad = ctx.createRadialGradient(screenX, screenY, player.radius * 0.8, screenX, screenY, auraRadius);
    auraGrad.addColorStop(0, `rgba(${wR}, ${wG}, ${wB}, ${auraAlpha})`);
    auraGrad.addColorStop(0.5, `rgba(${wR}, ${wG}, ${wB}, ${auraAlpha * 0.5})`);
    auraGrad.addColorStop(1, 'transparent');
    ctx.fillStyle = auraGrad; ctx.beginPath(); ctx.arc(screenX, screenY, auraRadius, 0, Math.PI * 2); ctx.fill();
    const warningColor = `rgba(${wR}, ${wG}, ${wB}, ${pulse * (0.6 + urgency * 0.3)})`;
    ctx.strokeStyle = warningColor; ctx.lineWidth = remaining < 5 ? 5 : 3;
    ctx.beginPath(); ctx.arc(screenX, screenY, player.radius + 20, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = warningColor; ctx.font = 'bold 18px Segoe UI'; ctx.textAlign = 'center';
    ctx.fillText('CRITICAL MASS', screenX, screenY - player.radius - 28);
    ctx.font = `bold ${remaining < 10 ? 28 : 22}px Segoe UI`;
    ctx.fillText(`${Math.ceil(remaining)}s`, screenX, screenY + player.radius + 30);
}

function drawPowerupEffect(screenX, screenY, player) {
    if (player.active_powerup === 'shield') {
        const shieldPulse = Math.sin(Date.now() / 150) * 0.3 + 0.7;
        ctx.strokeStyle = `rgba(255, 215, 0, ${shieldPulse})`; ctx.lineWidth = 4;
        ctx.beginPath(); ctx.arc(screenX, screenY, player.radius + 12, 0, Math.PI * 2); ctx.stroke();
        const shieldGlow = ctx.createRadialGradient(screenX, screenY, player.radius, screenX, screenY, player.radius + 18);
        shieldGlow.addColorStop(0, 'transparent'); shieldGlow.addColorStop(0.5, `rgba(255, 215, 0, ${shieldPulse * 0.25})`); shieldGlow.addColorStop(1, 'transparent');
        ctx.fillStyle = shieldGlow; ctx.beginPath(); ctx.arc(screenX, screenY, player.radius + 18, 0, Math.PI * 2); ctx.fill();
    } else if (player.active_powerup === 'rapid_fire') {
        for (let i = 0; i < 6; i++) {
            const angle = (Date.now() / 100 + i * Math.PI / 3) % (Math.PI * 2);
            const dist = player.radius + 8 + Math.sin(Date.now() / 80 + i) * 6;
            ctx.fillStyle = i % 2 === 0 ? 'rgba(255, 100, 50, 0.8)' : 'rgba(255, 200, 50, 0.7)';
            ctx.beginPath(); ctx.arc(screenX + Math.cos(angle) * dist, screenY + Math.sin(angle) * dist, 3, 0, Math.PI * 2); ctx.fill();
        }
    } else if (player.active_powerup === 'magnet') {
        for (let i = 0; i < 8; i++) {
            const angle = (Date.now() / 200 + i * Math.PI / 4) % (Math.PI * 2);
            const alpha = (Math.sin(Date.now() / 100 + i) * 0.3 + 0.5);
            ctx.strokeStyle = `rgba(0, 255, 136, ${alpha})`; ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(screenX + Math.cos(angle) * (player.radius + 25), screenY + Math.sin(angle) * (player.radius + 25));
            ctx.lineTo(screenX + Math.cos(angle) * (player.radius + 5), screenY + Math.sin(angle) * (player.radius + 5));
            ctx.stroke();
        }
    } else if (player.active_powerup === 'phantom') {
        ctx.globalAlpha = 0.4;
    } else if (player.active_powerup === 'trail') {
        const t = Date.now(), trailPulse = Math.sin(t / 100) * 0.3 + 0.7;
        const trailGlow = ctx.createRadialGradient(screenX, screenY, player.radius, screenX, screenY, player.radius + 28);
        trailGlow.addColorStop(0, `rgba(0, 200, 255, ${trailPulse * 0.35})`);
        trailGlow.addColorStop(0.5, `rgba(0, 128, 255, ${trailPulse * 0.15})`);
        trailGlow.addColorStop(1, 'transparent');
        ctx.fillStyle = trailGlow; ctx.beginPath(); ctx.arc(screenX, screenY, player.radius + 28, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = `rgba(0, 220, 255, ${trailPulse})`; ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.arc(screenX, screenY, player.radius + 6, 0, Math.PI * 2); ctx.stroke();
        ctx.strokeStyle = `rgba(0, 128, 255, ${trailPulse * 0.7})`; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(screenX, screenY, player.radius + 13, 0, Math.PI * 2); ctx.stroke();
        const streakCount = 8, streakOffset = (t / 60) % (Math.PI * 2);
        for (let i = 0; i < streakCount; i++) {
            const angle = streakOffset + i * (Math.PI * 2 / streakCount);
            const innerR = player.radius + 15, outerR = player.radius + 22 + Math.sin(t / 80 + i * 1.3) * 5;
            const streakAlpha = (Math.sin(t / 90 + i * 2.1) * 0.4 + 0.6) * trailPulse;
            ctx.strokeStyle = `rgba(0, 210, 255, ${streakAlpha * 0.8})`; ctx.lineWidth = 1.5;
            ctx.beginPath(); ctx.moveTo(screenX + Math.cos(angle) * innerR, screenY + Math.sin(angle) * innerR);
            ctx.lineTo(screenX + Math.cos(angle) * outerR, screenY + Math.sin(angle) * outerR); ctx.stroke();
        }
    } else if (player.active_powerup === 'speed_force') {
        const t = Date.now() / 1000;
        for (let i = 0; i < 8; i++) {
            const angle = t * 3 + i * Math.PI / 4;
            const dist = player.radius + 6 + Math.sin(t * 12 + i * 5) * 10;
            ctx.strokeStyle = `rgba(255, 238, 0, ${0.6 + Math.sin(t * 15 + i) * 0.4})`; ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(screenX + Math.cos(angle) * player.radius, screenY + Math.sin(angle) * player.radius);
            const midDist = (player.radius + dist) / 2, jag = (Math.random() - 0.5) * 12;
            ctx.lineTo(screenX + Math.cos(angle) * midDist + jag, screenY + Math.sin(angle) * midDist + jag);
            ctx.lineTo(screenX + Math.cos(angle) * dist, screenY + Math.sin(angle) * dist); ctx.stroke();
        }
        const speedGlow = ctx.createRadialGradient(screenX, screenY, player.radius, screenX, screenY, player.radius + 20);
        speedGlow.addColorStop(0, `rgba(255, 238, 0, ${0.15 + Math.sin(Date.now() / 125) * 0.1})`);
        speedGlow.addColorStop(1, 'transparent');
        ctx.fillStyle = speedGlow; ctx.beginPath(); ctx.arc(screenX, screenY, player.radius + 20, 0, Math.PI * 2); ctx.fill();
    }
    const homingCount = player.homing_missiles_remaining || 0;
    if (homingCount > 0) {
        for (let i = 0; i < homingCount; i++) {
            const angle = Date.now() / 500 + i * Math.PI * 2 / 3;
            const rx = Math.cos(angle) * player.radius * 1.3, ry = Math.sin(angle) * player.radius * 1.3;
            ctx.strokeStyle = '#ffaa00'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(screenX + rx, screenY + ry, 8, 0, Math.PI * 2); ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(screenX + rx - 12, screenY + ry); ctx.lineTo(screenX + rx + 12, screenY + ry);
            ctx.moveTo(screenX + rx, screenY + ry - 12); ctx.lineTo(screenX + rx, screenY + ry + 12);
            ctx.stroke();
        }
    }
    if (player.trail_held) {
        const angle = Date.now() / 700;
        const tx = screenX + Math.cos(angle) * player.radius * 1.5, ty = screenY + Math.sin(angle) * player.radius * 1.5;
        ctx.strokeStyle = '#0080ff'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(tx, ty, 8, 0, Math.PI * 2); ctx.stroke();
        ctx.fillStyle = 'rgba(0, 128, 255, 0.4)'; ctx.beginPath(); ctx.arc(tx, ty, 4, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = '#0080ff'; ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (let s = 0; s < 4; s++) {
            const sa = s * Math.PI / 2 + Math.PI / 4;
            ctx.moveTo(tx + Math.cos(sa) * 8, ty + Math.sin(sa) * 8);
            ctx.lineTo(tx + Math.cos(sa) * 13, ty + Math.sin(sa) * 13);
        }
        ctx.stroke();
    }
    if (player.wormhole_held) {
        const angle = Date.now() / 800 + Math.PI * 0.5;
        const wx = screenX + Math.cos(angle) * player.radius * 1.5, wy = screenY + Math.sin(angle) * player.radius * 1.5;
        const t = Date.now() / 1000;
        ctx.fillStyle = '#000000'; ctx.beginPath(); ctx.arc(wx, wy, 6, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = `rgba(0, 210, 170, ${0.7 + Math.sin(t * 5) * 0.3})`; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(wx, wy, 9, 0, Math.PI * 2); ctx.stroke();
        const dotAngle = t * 4;
        ctx.fillStyle = 'rgba(0, 220, 180, 0.9)';
        ctx.beginPath(); ctx.arc(wx + Math.cos(dotAngle) * 9, wy + Math.sin(dotAngle) * 9, 2, 0, Math.PI * 2); ctx.fill();
    }
    const mineCount = player.mines_remaining || 0;
    if (mineCount > 0) {
        for (let i = 0; i < mineCount; i++) {
            const angle = Date.now() / 600 + i * Math.PI * 2 / 3 + Math.PI;
            const mx = screenX + Math.cos(angle) * player.radius * 1.3, my = screenY + Math.sin(angle) * player.radius * 1.3;
            ctx.strokeStyle = '#ff3300'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(mx, my, 7, 0, Math.PI * 2); ctx.stroke();
            ctx.fillStyle = 'rgba(255, 51, 0, 0.6)'; ctx.beginPath(); ctx.arc(mx, my, 3, 0, Math.PI * 2); ctx.fill();
            ctx.strokeStyle = '#ff3300'; ctx.lineWidth = 1.5;
            ctx.beginPath();
            for (let s = 0; s < 4; s++) {
                const sa = s * Math.PI / 2;
                ctx.moveTo(mx + Math.cos(sa) * 7, my + Math.sin(sa) * 7);
                ctx.lineTo(mx + Math.cos(sa) * 11, my + Math.sin(sa) * 11);
            }
            ctx.stroke();
        }
    }
}

function drawBoostTrail(screenX, screenY, player) {
    ctx.strokeStyle = 'rgba(0, 255, 255, 0.6)'; ctx.lineWidth = 2;
    for (let i = 0; i < 5; i++) {
        const angle = Math.random() * Math.PI * 2, dist = player.radius + 10 + Math.random() * 20;
        ctx.beginPath();
        ctx.moveTo(screenX + Math.cos(angle) * player.radius, screenY + Math.sin(angle) * player.radius);
        ctx.lineTo(screenX + Math.cos(angle) * dist, screenY + Math.sin(angle) * dist);
        ctx.stroke();
    }
}

function drawPlayer(player, isYou) {
    const state = OrbArena.state.state;
    const screenX = player.x - state.camera.x, screenY = player.y - state.camera.y;
    if (isOffScreen(screenX, screenY, player.radius * 2)) return;
    if (player.is_invincible) drawInvincibilityEffect(screenX, screenY, player);
    if (player.critical_mass_active) drawCriticalMassEffect(screenX, screenY, player);
    drawPowerupEffect(screenX, screenY, player);
    if (player.is_boosting) drawBoostTrail(screenX, screenY, player);
    const glowColor = player.is_boosting ? 'rgba(0, 255, 255, 0.4)' : player.color + '60';
    const glow = ctx.createRadialGradient(screenX, screenY, player.radius * 0.5, screenX, screenY, player.radius * 2);
    glow.addColorStop(0, glowColor); glow.addColorStop(1, 'transparent');
    ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(screenX, screenY, player.radius * 2, 0, Math.PI * 2); ctx.fill();
    const bodyGradient = ctx.createRadialGradient(screenX - player.radius * 0.3, screenY - player.radius * 0.3, 0, screenX, screenY, player.radius);
    bodyGradient.addColorStop(0, OrbArena.utils.lightenColor(player.color, 30));
    bodyGradient.addColorStop(0.7, player.color);
    bodyGradient.addColorStop(1, OrbArena.utils.darkenColor(player.color, 30));
    ctx.fillStyle = bodyGradient; ctx.beginPath(); ctx.arc(screenX, screenY, player.radius, 0, Math.PI * 2); ctx.fill();
    if (isYou) {
        ctx.strokeStyle = player.is_boosting ? '#00ffff' : '#fff'; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(screenX, screenY, player.radius + 5, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.fillStyle = player.is_invincible ? '#88ddff' : '#fff';
    ctx.font = 'bold 14px Segoe UI'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(player.name, screenX, screenY - player.radius - 15);
    ctx.font = '12px Segoe UI'; ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
    ctx.fillText(Math.floor(player.radius), screenX, screenY);
    if (player.active_powerup === 'phantom') ctx.globalAlpha = 1;
}

function drawMinimap() {
    const state = OrbArena.state.state;
    const mapSize = minimapCanvas.width, scale = mapSize / state.world.width;
    const isRallyMap = state.challengeMode && state.challengeName === 'rally_run' && state.welcomeTrackWaypoints.length > 1;
    minimapCtx.fillStyle = isRallyMap ? 'rgba(8, 12, 20, 0.92)' : 'rgba(0, 0, 0, 0.7)';
    minimapCtx.fillRect(0, 0, mapSize, mapSize);
    if (isRallyMap) {
        const wps = state.welcomeTrackWaypoints, corridorW = 175 * 2 * scale;
        minimapCtx.beginPath(); minimapCtx.moveTo(wps[0][0] * scale, wps[0][1] * scale);
        for (let i = 1; i < wps.length; i++) minimapCtx.lineTo(wps[i][0] * scale, wps[i][1] * scale);
        minimapCtx.strokeStyle = 'rgba(55, 62, 80, 1)'; minimapCtx.lineWidth = corridorW;
        minimapCtx.lineJoin = 'round'; minimapCtx.lineCap = 'round'; minimapCtx.stroke();
        minimapCtx.beginPath(); minimapCtx.moveTo(wps[0][0] * scale, wps[0][1] * scale);
        for (let i = 1; i < wps.length; i++) minimapCtx.lineTo(wps[i][0] * scale, wps[i][1] * scale);
        minimapCtx.strokeStyle = 'rgba(255, 255, 255, 0.12)'; minimapCtx.lineWidth = 0.75;
        minimapCtx.setLineDash([3, 5]); minimapCtx.stroke(); minimapCtx.setLineDash([]);
        const sf = wps[0]; minimapCtx.fillStyle = '#ffffff';
        minimapCtx.fillRect(sf[0] * scale - 1.5, sf[1] * scale - 5, 3, 10);
        if (state.challengeData) {
            const cpIdx = state.challengeData.checkpoint;
            const cpOrb = state.goldenOrbs && state.goldenOrbs.find(o => o.id === `checkpoint_${cpIdx}`);
            if (cpOrb) {
                minimapCtx.fillStyle = 'rgba(255, 215, 0, 0.85)';
                minimapCtx.beginPath(); minimapCtx.arc(cpOrb.x * scale, cpOrb.y * scale, 2.5, 0, Math.PI * 2); minimapCtx.fill();
            }
        }
    } else {
        const puHue = (Date.now() / 10) % 360;
        minimapCtx.fillStyle = `hsl(${puHue}, 100%, 80%)`;
        state.powerupOrbs.forEach(orb => {
            minimapCtx.beginPath(); minimapCtx.arc(orb.x * scale, orb.y * scale, 3, 0, Math.PI * 2); minimapCtx.fill();
        });
        state.players.forEach(player => {
            if (!player.alive || (state.you && player.id === state.you.id)) return;
            minimapCtx.fillStyle = player.color;
            minimapCtx.beginPath(); minimapCtx.arc(player.x * scale, player.y * scale, Math.max(2, player.radius * scale), 0, Math.PI * 2); minimapCtx.fill();
        });
    }
    if (state.you && state.you.alive) {
        minimapCtx.fillStyle = '#ffffff';
        minimapCtx.beginPath(); minimapCtx.arc(state.you.x * scale, state.you.y * scale, isRallyMap ? 3 : 4, 0, Math.PI * 2); minimapCtx.fill();
        if (!isRallyMap) {
            const ns = OrbArena.state;
            minimapCtx.strokeStyle = 'rgba(255, 255, 255, 0.5)'; minimapCtx.lineWidth = 1;
            minimapCtx.strokeRect(state.camera.x * scale, state.camera.y * scale,
                (canvas.width / ns.currentZoom) * scale, (canvas.height / ns.currentZoom) * scale);
        }
    }
}

// ── Main Render ──

function render() {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#040404'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!state.playing) return;

    const ch = canvas.height, glowH = ch * 0.35;
    const tg = ctx.createLinearGradient(0, 0, 0, glowH);
    tg.addColorStop(0, 'rgba(42,10,0,0.4)'); tg.addColorStop(1, 'transparent');
    ctx.fillStyle = tg; ctx.fillRect(0, 0, canvas.width, glowH);
    const bg = ctx.createLinearGradient(0, ch, 0, ch - glowH);
    bg.addColorStop(0, 'rgba(42,10,0,0.4)'); bg.addColorStop(1, 'transparent');
    ctx.fillStyle = bg; ctx.fillRect(0, ch - glowH, canvas.width, glowH);

    ctx.save(); ctx.scale(ns.currentZoom, ns.currentZoom);
    if (ns.vfxShakeIntensity > 0.1) ctx.translate(ns.vfxShakeX, ns.vfxShakeY);

    const hasEarthquake = state.disaster && state.disaster.active === 'earthquake';
    if (hasEarthquake) { ctx.save(); drawEarthquakeShake(state.disaster.earthquake_progress || 0); }

    drawGrid();
    drawBoundary();
    if (state.challengeMode && state.challengeName === 'rally_run') drawTrack();
    state.walls.forEach(wall => drawWall(wall));
    if (state.challengeMode && state.welcomeTurrets.length > 0) {
        const activeTurretIds = new Set(state.challengeData ? (state.challengeData.active_turrets || []) : []);
        state.welcomeTurrets.forEach(t => drawTurret(t, activeTurretIds.has(t.id)));
    }
    state.energyOrbs.forEach(orb => drawEnergyOrb(orb));
    state.goldenOrbs.forEach(orb => drawGoldenOrb(orb));
    state.powerupOrbs.forEach(orb => drawPowerUpOrb(orb));
    state.minePickups.forEach(pickup => drawMinePickup(pickup));
    state.mines.forEach(mine => drawMine(mine));
    if (state.challengeMode && state.challengeName === 'rally_run') drawCheckpointArrow();
    state.spikeOrbs.forEach(orb => drawSpikeOrb(orb));
    renderParticles();
    drawTrailSegments();
    (state.wormholePortals || []).forEach(p => drawWormholePortal(p));
    if (state.wormholeExitEffect) {
        const age = Date.now() - state.wormholeExitEffect.time;
        if (age < 800) drawWormholeExit(state.wormholeExitEffect.x, state.wormholeExitEffect.y, age / 800);
        else state.wormholeExitEffect = null;
    }
    state.projectiles.forEach(proj => drawProjectile(proj));
    renderDisasterEffects();
    const sortedPlayers = [...state.players].sort((a, b) => a.radius - b.radius);
    sortedPlayers.forEach(player => { if (player.alive) drawPlayer(player, state.you && player.id === state.you.id); });
    if (state.challengeName === 'boss_hunt' && state.boss) drawBoss(state.boss);
    if (state.challengeName === 'boss_hunt' && state.challengeData) {
        const sp = state.challengeData.strike_phase;
        if (sp && state.challengeData.strike_target) drawStrikeReticle(state.challengeData.strike_target, sp);
    }
    renderKillRings();
    renderKillPopups();
    if (state.disaster && state.disaster.active === 'fog_of_war') drawFogOfWar(state.disaster.fog_radius || 300);
    if (state.disaster && state.disaster.active === 'feeding_frenzy') drawFrenzyOverlay(state.disaster.progress || 0);
    if (hasEarthquake) ctx.restore();
    ctx.restore();

    if (state.wormholeFlashUntil && Date.now() < state.wormholeFlashUntil) {
        const flashProgress = (state.wormholeFlashUntil - Date.now()) / 200;
        ctx.fillStyle = `rgba(0, 230, 180, ${flashProgress * 0.5})`;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
    }

    drawKillFeed();
    drawBoostIndicator();
    drawTouchIndicator();
    drawPowerUpPopup();
    drawRallyCountdown();
    drawStrikeAlert();

    if (state.disaster && state.disaster.active === 'fog_of_war') {
        minimapCtx.fillStyle = 'rgba(0, 0, 0, 0.9)'; minimapCtx.fillRect(0, 0, minimapCanvas.width, minimapCanvas.height);
        minimapCtx.fillStyle = 'rgba(100, 100, 150, 0.5)'; minimapCtx.font = 'bold 12px Segoe UI';
        minimapCtx.textAlign = 'center'; minimapCtx.textBaseline = 'middle';
        minimapCtx.fillText('FOG', minimapCanvas.width / 2, minimapCanvas.height / 2);
    } else {
        drawMinimap();
    }
}

OrbArena.render = {
    update,
    render,
    triggerScreenShake,
    spawnOrbBurst,
    spawnKillEffects,
    detectOrbConsumption,
    spawnStrikeImpact,
    isNearPlayer,
    getZoomForRadius,
    get canvas() { return canvas; },
    get ctx() { return ctx; },
};
