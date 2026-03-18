window.OrbArena = window.OrbArena || {};

// ── DOM Elements (UI screens) ──
const startScreen = document.getElementById('start-screen');
const deathScreen = document.getElementById('death-screen');
const hud = document.getElementById('hud');
const leaderboard = document.getElementById('leaderboard');
const minimap = document.getElementById('minimap');
const nameInput = document.getElementById('name-input');
const playBtn = document.getElementById('play-btn');
const spectateBtn = document.getElementById('spectate-btn');
const challengeBtn = document.getElementById('challenge-btn');
const respawnBtn = document.getElementById('respawn-btn');
const challengeResult = document.getElementById('challenge-result');
const challengeHud = document.getElementById('challenge-hud');
const spectatingBanner = document.getElementById('spectating-banner');
const finalScore = document.getElementById('final-score');
const gameMuteBtn = document.getElementById('game-mute-btn');
const challengeScreen = document.getElementById('challenge-screen');

// Leaderboard collapse toggle
const leaderboardHeader = leaderboard.querySelector('h3');
leaderboardHeader.addEventListener('click', function(e) {
    e.stopPropagation();
    leaderboard.classList.toggle('collapsed');
});
if (window.innerWidth <= 768) {
    leaderboard.classList.add('collapsed');
}

function toggleMute() {
    const state = OrbArena.state.state;
    state.audioMuted = !state.audioMuted;
    const icon = state.audioMuted ? '\u{1F507}' : '\u{1F50A}';
    gameMuteBtn.textContent = icon;
    gameMuteBtn.classList.toggle('muted', state.audioMuted);
    if (OrbArena.audio.ambient.playing) OrbArena.audio.ambient.updateVolume();
}
gameMuteBtn.addEventListener('click', toggleMute);

function initAudio() {
    if (OrbArena.state.ambientStarted) return;
    OrbArena.state.ambientStarted = true;
    const ac = OrbArena.audio.audioCtx;
    if (ac && ac.state === 'suspended') {
        ac.resume().then(() => OrbArena.audio.ambient.start());
    } else {
        OrbArena.audio.ambient.start();
    }
}

// Try to start on load (works if browser allows autoplay)
try {
    const ac = OrbArena.audio.audioCtx;
    if (ac.state === 'running') {
        OrbArena.state.ambientStarted = true;
        OrbArena.audio.ambient.start();
    } else {
        ac.resume().then(() => {
            if (!OrbArena.state.ambientStarted) {
                OrbArena.state.ambientStarted = true;
                OrbArena.audio.ambient.start();
            }
        }).catch(() => {});
    }
} catch(e) {}

function onFirstInteraction() {
    initAudio();
    document.removeEventListener('click', onFirstInteraction);
    document.removeEventListener('keydown', onFirstInteraction);
    document.removeEventListener('touchstart', onFirstInteraction);
}
document.addEventListener('click', onFirstInteraction);
document.addEventListener('keydown', onFirstInteraction);
document.addEventListener('touchstart', onFirstInteraction);

// ── State Update Handler ──

function handleStateUpdate(data) {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;

    // VFX: detect events from state diffs (BEFORE state overwrite)
    if (state.you && state.you.alive && data.you && data.you.alive) {
        const scoreDelta = data.you.score - state.you.score;
        if (scoreDelta > 30) {
            OrbArena.render.triggerScreenShake(Math.min(12, 4 + scoreDelta / 20));
            OrbArena.audio.sfx.kill();

            let victimColor = '#ffffff';
            if (state.players && data.players) {
                const newAlive = new Set(data.players.filter(p => p.alive).map(p => p.id));
                const victim = state.players.find(p => p.alive && p.id !== state.you.id && !newAlive.has(p.id));
                if (victim) victimColor = victim.color;
            }
            OrbArena.render.spawnKillEffects(data.you.x, data.you.y, scoreDelta, victimColor, data.you.radius);
        }
        const radiusDelta = state.you.radius - data.you.radius;
        if (radiusDelta > 2) {
            OrbArena.render.triggerScreenShake(Math.min(8, 2 + radiusDelta / 5));
            OrbArena.audio.sfx.hit();
        }
    }
    OrbArena.render.detectOrbConsumption(data);

    // Detect power-up pickup
    if (data.you && data.you.active_powerup && (!state.you || !state.you.active_powerup || state.you.active_powerup !== data.you.active_powerup)) {
        const names = { shield: 'SHIELD', rapid_fire: 'RAPID FIRE', magnet: 'MAGNET', phantom: 'PHANTOM', speed_force: 'SPEED FORCE' };
        state.powerupPopup = { text: names[data.you.active_powerup] || data.you.active_powerup.toUpperCase(), time: Date.now() };
        OrbArena.audio.sfx.powerupPickup();
    }

    // Detect Tron Trail pickup
    if (data.you && data.you.trail_held && state.you && !state.you.trail_held) {
        const swapped = state.you.wormhole_held;
        state.powerupPopup = { text: swapped ? 'TRON TRAIL (swapped)' : 'TRON TRAIL', time: Date.now() };
        OrbArena.audio.sfx.powerupPickup();
    }

    // Detect Wormhole pickup
    if (data.you && data.you.wormhole_held && state.you && !state.you.wormhole_held) {
        const swapped = state.you.trail_held;
        state.powerupPopup = { text: swapped ? 'WORMHOLE (swapped)' : 'WORMHOLE', time: Date.now() };
        OrbArena.audio.sfx.powerupPickup();
    }

    // Detect wormhole teleport (large position jump while alive)
    if (data.you && state.you && data.you.alive && state.you.alive) {
        const dx = data.you.x - state.you.x;
        const dy = data.you.y - state.you.y;
        if (dx * dx + dy * dy > 200 * 200) {
            state.wormholeExitEffect = { x: data.you.x, y: data.you.y, time: Date.now() };
            state.wormholeFlashUntil = Date.now() + 200;
            OrbArena.render.triggerScreenShake(4);
        }
    }

    // Detect mine pickup
    if (data.you && state.you && data.you.mines_remaining > (state.you.mines_remaining || 0)) {
        state.powerupPopup = { text: 'MINE', time: Date.now() };
        OrbArena.audio.sfx.powerupPickup();
    }

    // Detect homing missile pickup
    if (data.you && state.you && data.you.homing_missiles_remaining > (state.you.homing_missiles_remaining || 0)) {
        state.powerupPopup = { text: 'MISSILE', time: Date.now() };
        OrbArena.audio.sfx.powerupPickup();
    }

    // Detect power-up expiry
    if (state.you && state.you.active_powerup && data.you && !data.you.active_powerup) {
        OrbArena.audio.sfx.powerupExpire();
    }

    // Detect disaster warning
    const newDisaster = data.disaster || { active: null, warning: null };
    if (newDisaster.warning && !ns.prevDisasterWarning) {
        OrbArena.audio.sfx.disasterWarning();
    }
    // Detect disaster activation
    if (newDisaster.active && newDisaster.active !== ns.prevDisasterActive) {
        OrbArena.audio.stopDisasterLoop();
        ns.supernovaPulsesPlayed = 0;
        if (newDisaster.active === 'black_hole') {
            OrbArena.audio.startDisasterLoop('black_hole');
        } else if (newDisaster.active === 'earthquake') {
            OrbArena.audio.startDisasterLoop('earthquake');
        } else if (newDisaster.active === 'supernova') {
            OrbArena.audio.sfx.supernovaPulse();
            ns.supernovaPulsesPlayed = 1;
        } else if (newDisaster.active === 'meteor_shower') {
            OrbArena.audio.sfx.meteorImpact();
        } else if (newDisaster.active === 'feeding_frenzy') {
            OrbArena.audio.sfx.feedingFrenzy();
        }
    }
    // Supernova: play sound for each new pulse wave
    if (newDisaster.active === 'supernova' && newDisaster.supernova) {
        const nova = newDisaster.supernova;
        const elapsed = nova.time || 0;
        const interval = nova.pulse_interval || 1.5;
        const totalPulses = nova.pulse_count || 5;
        const currentPulse = Math.floor(elapsed / interval) + 1;
        if (currentPulse > ns.supernovaPulsesPlayed && currentPulse <= totalPulses) {
            OrbArena.audio.sfx.supernovaPulse();
            ns.supernovaPulsesPlayed = currentPulse;
        }
    }
    // Meteor shower: play impact for each new meteor
    if (newDisaster.active === 'meteor_shower' && newDisaster.meteors) {
        for (const m of newDisaster.meteors) {
            const key = m.x + ',' + m.y;
            if (!ns.seenMeteorKeys.has(key)) {
                ns.seenMeteorKeys.add(key);
                if (OrbArena.render.isNearPlayer(m.x, m.y, 500)) OrbArena.audio.sfx.meteorImpact();
            }
        }
    } else {
        ns.seenMeteorKeys.clear();
    }
    // Stop looping sounds when disaster ends
    if (!newDisaster.active && ns.prevDisasterActive) {
        OrbArena.audio.stopDisasterLoop();
        ns.supernovaPulsesPlayed = 0;
    }
    ns.prevDisasterWarning = newDisaster.warning;
    ns.prevDisasterActive = newDisaster.active;

    if (data.you) state.you = data.you;
    state.players = data.players;
    state.energyOrbs = data.energy_orbs;
    state.spikeOrbs = data.spike_orbs || [];
    state.goldenOrbs = data.golden_orbs || [];

    // Track strike barrage shots for impact VFX
    const incomingProjs = data.projectiles || [];
    const newStrikeIds = new Set();
    incomingProjs.forEach(p => { if (p.owner_id === 'strike') newStrikeIds.add(p.id); });
    ns.prevStrikeMap.forEach((pos, id) => {
        if (!newStrikeIds.has(id)) OrbArena.render.spawnStrikeImpact(pos.x, pos.y);
    });
    ns.prevStrikeMap.clear();
    incomingProjs.forEach(p => { if (p.owner_id === 'strike') ns.prevStrikeMap.set(p.id, {x: p.x, y: p.y}); });
    state.projectiles = incomingProjs;
    state.powerupOrbs = data.powerup_orbs || [];
    state.minePickups = data.mine_pickups || [];
    state.mines = data.mines || [];
    state.wormholePortals = data.wormhole_portals || [];
    state.trailSegments = data.trail_segments || [];
    state.killFeed = data.kill_feed || [];
    state.leaderboard = data.leaderboard;
    state.disaster = data.disaster || { active: null, warning: null };
    if (data.walls) state.walls = data.walls;
    if (data.boss !== undefined) state.boss = data.boss;

    // Update challenge HUD if in challenge mode
    if (data.challenge) {
        if (data.challenge.type === 'rally_run') {
            const prevCd = state.challengeData ? (state.challengeData.countdown || 0) : 0;
            const currCd = data.challenge.countdown || 0;
            if (currCd > 0) {
                const digit = Math.ceil(currCd);
                if (digit !== state.rallyCountdownDigit) {
                    state.rallyCountdownDigit = digit;
                    state.rallyCountdownDigitTime = Date.now();
                }
            } else if (prevCd > 0) {
                state.rallyGoUntil = Date.now() + 900;
            }
        }
        state.challengeData = data.challenge;
        if (data.challenge.type === 'rally_run') {
            const lt = data.challenge.lap_time !== null ? data.challenge.lap_time + 's' : '--';
            const tt = data.challenge.total_time !== null ? data.challenge.total_time + 's' : '--';
            document.getElementById('ch-lap-time').textContent = lt;
            document.getElementById('ch-lap').textContent = `LAP ${data.challenge.lap} / ${data.challenge.max_laps}`;
            document.getElementById('ch-total').textContent = 'Total: ' + tt;
            document.getElementById('ch-cp').textContent = `Gate ${data.challenge.checkpoint} / ${data.challenge.total_checkpoints}`;
        } else if (data.challenge.type === 'hunter_seeker') {
            document.getElementById('ch-boss-time').textContent = data.challenge.time_survived + 's';
            const weakened = data.challenge.boss_weakened;
            document.getElementById('ch-boss-status').textContent = weakened ? 'HUNTER SLOWED' : 'HUNTER ACTIVE';
            document.getElementById('ch-boss-status').style.color = weakened ? '#00ff88' : '#aa2200';
            const shooting = data.challenge.shooting_phase;
            const nextIn = data.challenge.next_phase_in;
            if (shooting) {
                document.getElementById('ch-boss-phase').textContent = `ATTACK PHASE: ${nextIn}s`;
                document.getElementById('ch-boss-phase').style.color = '#ff2200';
            } else {
                document.getElementById('ch-boss-phase').textContent = nextIn > 0 ? `ATTACK IN: ${nextIn}s` : '';
                document.getElementById('ch-boss-phase').style.color = '#7a6858';
            }
        } else {
            document.getElementById('ch-time').textContent = data.challenge.time_survived + 's';
            document.getElementById('ch-wave').textContent = 'Wave ' + data.challenge.wave;
        }
    }

    // Suppress normal death screen in challenge mode
    if (!state.challengeMode) {
        if (state.you && !state.you.alive && state.playing && deathScreen.style.display !== 'flex') {
            showDeathScreen();
        } else if (state.you && state.you.alive && deathScreen.style.display === 'flex') {
            hideDeathScreen();
        }
    }
}

// ── Screen Management ──

function showGame() {
    const state = OrbArena.state.state;
    document.body.classList.add('in-game');
    startScreen.style.display = 'none';
    OrbArena.render.canvas.style.display = 'block';
    hud.style.display = 'block';
    minimap.style.display = 'block';
    gameMuteBtn.style.display = 'flex';

    if (OrbArena.audio.ambient.playing) OrbArena.audio.ambient.fadeOut(2);

    if (state.challengeMode) {
        challengeHud.style.display = 'flex';
        leaderboard.style.display = 'none';
        spectatingBanner.style.display = 'none';
    } else if (state.connectionMode === 'spectate') {
        leaderboard.style.display = 'block';
        challengeHud.style.display = 'none';
        spectatingBanner.style.display = 'block';
    } else {
        leaderboard.style.display = 'block';
        challengeHud.style.display = 'none';
        spectatingBanner.style.display = 'none';
    }
}

function showDeathScreen() {
    const state = OrbArena.state.state;
    OrbArena.audio.sfx.death();
    finalScore.textContent = state.lastScore;
    deathScreen.style.display = 'flex';
    document.getElementById('boost-btn').style.display = 'none';
    document.getElementById('shoot-btn').style.display = 'none';
    document.getElementById('mine-btn').style.display = 'none';
    document.getElementById('powerup-hud').style.display = 'none';
    gameMuteBtn.style.display = 'none';
    if (OrbArena.state.ambientStarted && !OrbArena.audio.ambient.playing) OrbArena.audio.ambient.fadeIn();
}

function hideDeathScreen() {
    OrbArena.audio.sfx.respawn();
    deathScreen.style.display = 'none';
    gameMuteBtn.style.display = 'flex';
    if (OrbArena.audio.ambient.playing) OrbArena.audio.ambient.fadeOut(2);
}

function showChallengeResult(data) {
    const state = OrbArena.state.state;
    OrbArena.audio.sfx.death();
    const ch = data.challenge || {};
    const isRally = ch.type === 'rally_run';
    const isBossHunt = ch.type === 'hunter_seeker';

    if (isBossHunt) {
        document.getElementById('cr-title').textContent = 'Hunter Seeker';
    } else {
        document.getElementById('cr-title').textContent = isRally ? 'Nitro Orb' : 'Missile Magnet';
    }

    if (isRally) {
        const completed = ch.is_complete;
        const laps = ch.laps_completed || 0;
        document.getElementById('cr-time-display').textContent = completed && ch.final_time ? ch.final_time + 's' : 'DNF';
        const rankEl = document.getElementById('cr-rank-display');
        if (completed && ch.rank) {
            rankEl.textContent = `Rank #${ch.rank} of ${ch.total} - all 3 laps complete`;
        } else if (completed) {
            rankEl.textContent = 'All 3 laps complete';
        } else {
            rankEl.textContent = `DNF - crashed on lap ${laps + 1}`;
        }
    } else {
        document.getElementById('cr-time-display').textContent = ch.time_survived + 's';
        const rankEl = document.getElementById('cr-rank-display');
        if (ch.rank && ch.total) {
            rankEl.textContent = `Rank #${ch.rank} of ${ch.total} attempts`;
        } else if (ch.rank) {
            rankEl.textContent = `Rank #${ch.rank}`;
        } else {
            rankEl.textContent = '';
        }
    }

    const list = document.getElementById('cr-scores-list');
    list.innerHTML = '';
    (ch.top_scores || []).forEach(s => {
        const li = document.createElement('li');
        const isYou = state.you && s.name === state.you.name;
        if (isYou) li.className = 'you';
        li.innerHTML = `<span>${s.name}</span><span class="cr-score-val">${s.time}s</span>`;
        list.appendChild(li);
    });

    challengeResult.style.display = 'flex';
    challengeHud.style.display = 'none';
    document.getElementById('boost-btn').style.display = 'none';
    document.getElementById('shoot-btn').style.display = 'none';
    document.getElementById('mine-btn').style.display = 'none';
    document.getElementById('powerup-hud').style.display = 'none';
    gameMuteBtn.style.display = 'none';
    if (OrbArena.state.ambientStarted && !OrbArena.audio.ambient.playing) OrbArena.audio.ambient.fadeIn();
}

function respawn() {
    OrbArena.network.ws.send(JSON.stringify({ type: 'respawn' }));
    hideDeathScreen();
}

function openChallengeScreen() {
    startScreen.style.display = 'none';
    challengeScreen.style.display = 'flex';
    fetch('/api/challenge/scores')
        .then(r => r.json())
        .then(scores => {
            const el = document.getElementById('cs-missile-magnet-score');
            if (scores && scores.length > 0) {
                el.textContent = `${scores[0].name} — ${scores[0].time}s`;
            } else {
                el.textContent = '--';
            }
        })
        .catch(() => {});
    fetch('/api/rally/scores')
        .then(r => r.json())
        .then(scores => {
            const el = document.getElementById('cs-rally-score');
            if (scores && scores.length > 0) {
                el.textContent = `${scores[0].name} — ${scores[0].time}s`;
            } else {
                el.textContent = '--';
            }
        })
        .catch(() => {});
    fetch('/api/boss/scores')
        .then(r => r.json())
        .then(scores => {
            const el = document.getElementById('cs-boss-hunt-score');
            if (scores && scores.length > 0) {
                el.textContent = `${scores[0].name} — ${scores[0].time}s`;
            } else {
                el.textContent = '--';
            }
        })
        .catch(() => {});
}

function closeChallengeScreen() {
    challengeScreen.style.display = 'none';
    startScreen.style.display = 'flex';
}

function goToMainMenu() {
    const state = OrbArena.state.state;
    const name = (state.you && state.you.name) || nameInput.value.trim();
    document.body.classList.remove('in-game');
    deathScreen.style.display = 'none';
    challengeResult.style.display = 'none';
    hud.style.display = 'none';
    leaderboard.style.display = 'none';
    gameMuteBtn.style.display = 'none';
    OrbArena.render.canvas.style.display = 'none';
    minimap.style.display = 'none';
    document.getElementById('boost-btn').style.display = 'none';
    document.getElementById('shoot-btn').style.display = 'none';
    document.getElementById('mine-btn').style.display = 'none';
    document.getElementById('disaster-hud').style.display = 'none';
    startScreen.style.display = 'flex';
    if (name && name !== 'Anonymous') nameInput.value = name;
    if (OrbArena.network.ws) { OrbArena.network.ws.close(); OrbArena.network.ws = null; }
    state.connected = false;
    state.playing = false;
    state.boss = null;
    OrbArena.state.currentZoom = OrbArena.render.getZoomForRadius(20);
    OrbArena.state.targetZoom = OrbArena.state.currentZoom;
    state.challengeData = null;
    playBtn.disabled = false;
    spectateBtn.disabled = false;
    challengeBtn.disabled = false;
    playBtn.textContent = 'DEPLOY';
}

function replayChallengeGame() {
    const state = OrbArena.state.state;
    const name = (state.you && state.you.name) || nameInput.value.trim() || 'Anonymous';
    const challenge = state.challengeName || 'missile_magnet';
    nameInput.value = name;
    challengeResult.style.display = 'none';
    if (OrbArena.network.ws && OrbArena.network.ws.readyState !== WebSocket.CLOSED) {
        const origOnClose = OrbArena.network.ws.onclose;
        OrbArena.network.ws.onclose = (e) => {
            if (origOnClose) origOnClose(e);
            OrbArena.network.joinGame('challenge', challenge);
        };
        OrbArena.network.ws.close();
    } else {
        state.connected = false;
        OrbArena.network.joinGame('challenge', challenge);
    }
}

// ── Event Listeners ──

// Load Hall of Fame on start screen
(function loadHoF() {
    fetch('/api/alltime/scores')
        .then(r => r.json())
        .then(scores => {
            const list = document.getElementById('start-hof-list');
            if (!scores || scores.length === 0) {
                list.innerHTML = '<li class="hof-empty">No scores yet - be the first!</li>';
                return;
            }
            list.innerHTML = scores.map((s, i) =>
                `<li>
                    <span class="hof-rank">#${i + 1}</span>
                    <span class="hof-name">${s.name}</span>
                    <span class="hof-score">${s.score}</span>
                </li>`
            ).join('');
        })
        .catch(() => {
            document.getElementById('start-hof-list').innerHTML =
                '<li class="hof-empty">-</li>';
        });
})();

// Poll player count on start screen
(function pollStatus() {
    const statusEl = document.getElementById('player-status');
    const textEl = document.getElementById('player-status-text');
    function updateStatus() {
        fetch('/api/status')
            .then(r => r.json())
            .then(data => {
                const n = data.players || 0;
                if (n === 0) {
                    statusEl.classList.remove('has-players');
                    textEl.textContent = 'No players online';
                } else if (n === 1) {
                    statusEl.classList.add('has-players');
                    textEl.textContent = '1 player online';
                } else {
                    statusEl.classList.add('has-players');
                    textEl.textContent = `${n} players online`;
                }
            })
            .catch(() => {
                statusEl.classList.remove('has-players');
                textEl.textContent = 'Server offline';
            });
    }
    updateStatus();
    setInterval(updateStatus, 5000);
})();

document.querySelectorAll('.guide-card h3').forEach(h3 => {
    h3.addEventListener('click', () => {
        h3.closest('.guide-card').classList.toggle('collapsed');
    });
});

playBtn.addEventListener('click', () => OrbArena.network.joinGame('player'));
spectateBtn.addEventListener('click', () => OrbArena.network.joinGame('spectate'));
challengeBtn.addEventListener('click', openChallengeScreen);
document.getElementById('cs-back-btn').addEventListener('click', closeChallengeScreen);
document.getElementById('cs-missile-magnet').addEventListener('click', () => {
    challengeScreen.style.display = 'none';
    OrbArena.network.joinGame('challenge', 'missile_magnet');
});
document.getElementById('cs-rally-run').addEventListener('click', () => {
    challengeScreen.style.display = 'none';
    OrbArena.network.joinGame('challenge', 'rally_run');
});
document.getElementById('cs-boss-hunt').addEventListener('click', () => {
    challengeScreen.style.display = 'none';
    OrbArena.network.joinGame('challenge', 'boss_hunt');
});
nameInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') OrbArena.network.joinGame('player');
});
respawnBtn.addEventListener('click', respawn);
document.getElementById('challenge-play-again').addEventListener('click', replayChallengeGame);
document.getElementById('death-menu-btn').addEventListener('click', goToMainMenu);
document.getElementById('challenge-menu-btn').addEventListener('click', goToMainMenu);

document.addEventListener('visibilitychange', () => {
    const state = OrbArena.state.state;
    if (document.visibilityState === 'visible' && state.playing) {
        if (!OrbArena.network.ws || OrbArena.network.ws.readyState === WebSocket.CLOSED || OrbArena.network.ws.readyState === WebSocket.CLOSING) {
            goToMainMenu();
        }
    }
});

OrbArena.ui = {
    showGame,
    showDeathScreen,
    hideDeathScreen,
    handleStateUpdate,
    showChallengeResult,
    goToMainMenu,
    openChallengeScreen,
    closeChallengeScreen,
};
