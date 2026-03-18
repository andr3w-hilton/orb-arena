window.OrbArena = window.OrbArena || {};

let ws = null;

function connect(onConnected) {
    // Use secure WebSocket (wss://) for HTTPS, regular (ws://) for HTTP
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Connect through nginx proxy at /ws path
    const wsUrl = `${wsProtocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        OrbArena.state.state.connected = true;
        if (onConnected) onConnected();
    };

    ws.onclose = () => {
        OrbArena.state.state.connected = false;
        if (OrbArena.state.state.playing) {
            goToMainMenu();
            return;
        }
        OrbArena.state.state.playing = false;

        playBtn.disabled = false;
        playBtn.textContent = 'DEPLOY';
        spectateBtn.disabled = false;
        spectateBtn.textContent = 'WATCH';
    };

    ws.onerror = () => {
        OrbArena.state.state.connected = false;

        playBtn.disabled = false;
        playBtn.textContent = 'DEPLOY';
        spectateBtn.disabled = false;
        spectateBtn.textContent = 'WATCH';
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleMessage(data);
    };
}

function handleMessage(data) {
    switch (data.type) {
        case 'welcome':
            if (data.mode === 'spectate') {
                // Spectator mode - no player data
                OrbArena.state.state.you = null;
                OrbArena.state.state.connectionMode = 'spectate';
                OrbArena.state.state.challengeMode = false;
            } else if (data.mode === 'challenge') {
                // Challenge mode - solo isolated game
                OrbArena.state.state.you = data.player;
                OrbArena.state.state.connectionMode = 'challenge';
                OrbArena.state.state.challengeMode = true;
                OrbArena.state.state.challengeName = data.challenge || 'missile_magnet';
                if (data.challenge === 'rally_run') {
                    OrbArena.state.state.welcomeTrackWaypoints = data.track_waypoints || [];
                    OrbArena.state.state.welcomeTurrets = data.turrets || [];
                    document.getElementById('ch-mm').style.display = 'none';
                    document.getElementById('ch-rally').style.display = '';
                    document.getElementById('ch-boss').style.display = 'none';
                } else if (data.challenge === 'boss_hunt') {
                    OrbArena.state.state.boss = data.boss || null;
                    document.getElementById('ch-mm').style.display = 'none';
                    document.getElementById('ch-rally').style.display = 'none';
                    document.getElementById('ch-boss').style.display = '';
                } else {
                    OrbArena.state.state.welcomeTurrets = data.turrets || [];
                    document.getElementById('ch-boss').style.display = 'none';
                }
            } else {
                // Multiplayer mode
                OrbArena.state.state.you = data.player;
                OrbArena.state.state.connectionMode = 'player';
                OrbArena.state.state.challengeMode = false;
            }
            OrbArena.state.state.walls = data.walls || [];
            OrbArena.state.state.world = data.world || OrbArena.state.state.world;
            OrbArena.state.state.playing = true;
            OrbArena.ui.showGame();
            break;

        case 'state':
            OrbArena.ui.handleStateUpdate(data);
            break;

        case 'challenge_result':
            showChallengeResult(data);
            break;
    }
}

function joinGame(mode = 'player', challenge = null) {
    OrbArena.state.state.connectionMode = mode;

    if (!OrbArena.state.state.connected) {
        // Connect first, then join when connected
        playBtn.disabled = true;
        spectateBtn.disabled = true;
        challengeBtn.disabled = true;
        playBtn.textContent = 'CONNECTING...';
        connect(() => {
            const name = nameInput.value.trim() || 'Anonymous';
            const msg = { type: 'join', name, mode };
            if (challenge) msg.challenge = challenge;
            ws.send(JSON.stringify(msg));
        });
    } else {
        const name = nameInput.value.trim() || 'Anonymous';
        const msg = { type: 'join', name, mode };
        if (challenge) msg.challenge = challenge;
        ws.send(JSON.stringify(msg));
    }
}

function sendMovement() {
    const state = OrbArena.state.state;
    if (!state.playing || state.connectionMode === 'spectate' || !state.you || !state.you.alive) return;

    const TOUCH_SENSITIVITY = 3;
    let worldX, worldY;

    // Check if using touch controls
    if (OrbArena.state.isTouchDevice && OrbArena.state.touchOrigin && OrbArena.state.touchCurrent) {
        // Relative touch: calculate direction from origin to current touch
        const deltaX = OrbArena.state.touchCurrent.x - OrbArena.state.touchOrigin.x;
        const deltaY = OrbArena.state.touchCurrent.y - OrbArena.state.touchOrigin.y;

        // Project from player position in that direction
        worldX = state.you.x + (deltaX * TOUCH_SENSITIVITY);
        worldY = state.you.y + (deltaY * TOUCH_SENSITIVITY);
    } else if (OrbArena.state.isTouchDevice && !OrbArena.state.touchOrigin) {
        // Touch released - target current position (stop moving)
        worldX = state.you.x;
        worldY = state.you.y;
    } else {
        // Mouse/desktop: convert screen coords to world coords (zoom-adjusted)
        worldX = OrbArena.state.mouseX / OrbArena.state.currentZoom + state.camera.x;
        worldY = OrbArena.state.mouseY / OrbArena.state.currentZoom + state.camera.y;
    }

    ws.send(JSON.stringify({
        type: 'move',
        x: worldX,
        y: worldY
    }));
}

function sendShoot(targetX, targetY) {
    const state = OrbArena.state.state;
    if (!state.connected || state.connectionMode === 'spectate' || !state.you) return;
    if (state.you.wormhole_held) return; // never consume wormhole via regular shoot
    if (!state.you.shoot_ready && state.you.active_powerup !== 'rapid_fire') return;
    ws.send(JSON.stringify({ type: 'shoot', x: targetX, y: targetY }));
    if (state.you.homing_missiles_remaining > 0) OrbArena.audio.sfx.homingShoot();
    else if (state.you.active_powerup === 'rapid_fire') OrbArena.audio.sfx.rapidShoot();
    else OrbArena.audio.sfx.shoot();
}

function sendWormhole() {
    const state = OrbArena.state.state;
    if (!state.connected || state.connectionMode === 'spectate' || !state.you || !state.you.wormhole_held) return;
    const worldX = OrbArena.state.mouseX / OrbArena.state.currentZoom + state.camera.x;
    const worldY = OrbArena.state.mouseY / OrbArena.state.currentZoom + state.camera.y;
    ws.send(JSON.stringify({ type: 'shoot', x: worldX, y: worldY, wormhole: true }));
    OrbArena.audio.sfx.powerupPickup(); // temporary until we have a dedicated sfx
}

function sendBoost() {
    const state = OrbArena.state.state;
    if (!state.connected || state.connectionMode === 'spectate' || !state.you || !state.you.boost_ready) return;
    ws.send(JSON.stringify({ type: 'boost' }));
    OrbArena.audio.sfx.boost();
}

function sendPlaceMine() {
    const state = OrbArena.state.state;
    if (!state.connected || state.connectionMode === 'spectate' || !state.you) return;
    if (!state.you.mines_remaining || state.you.mines_remaining <= 0) return;
    ws.send(JSON.stringify({ type: 'place_mine' }));
    OrbArena.audio.sfx.mineDrop();
}

OrbArena.network = {
    connect,
    joinGame,
    sendMovement,
    sendShoot,
    sendWormhole,
    sendBoost,
    sendPlaceMine,
    get ws() { return ws; },
    set ws(v) { ws = v; },
};
