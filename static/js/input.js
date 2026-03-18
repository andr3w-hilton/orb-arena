window.OrbArena = window.OrbArena || {};

const TOUCH_SENSITIVITY = 3;

// ── Mouse Events ──

OrbArena.render.canvas.addEventListener('mousemove', (e) => {
    OrbArena.state.mouseX = e.clientX;
    OrbArena.state.mouseY = e.clientY;
});

OrbArena.render.canvas.addEventListener('mousedown', (e) => {
    if (e.button === 0) OrbArena.state.isMouseDown = true;
});
OrbArena.render.canvas.addEventListener('mouseup', (e) => {
    if (e.button === 0) OrbArena.state.isMouseDown = false;
});

// ── Touch Events ──

let lastTapTime = 0;
const DOUBLE_TAP_DELAY = 300;

OrbArena.render.canvas.addEventListener('touchstart', (e) => {
    e.preventDefault();
    OrbArena.state.isTouchDevice = true;
    const touch = e.touches[0];
    OrbArena.state.touchOrigin = { x: touch.clientX, y: touch.clientY };
    OrbArena.state.touchCurrent = { x: touch.clientX, y: touch.clientY };

    const currentTime = Date.now();
    if (currentTime - lastTapTime < DOUBLE_TAP_DELAY) {
        const state = OrbArena.state.state;
        if (state.you && state.you.wormhole_held) OrbArena.network.sendWormhole();
        else OrbArena.network.sendBoost();
        lastTapTime = 0;
    } else {
        lastTapTime = currentTime;
    }
}, { passive: false });

OrbArena.render.canvas.addEventListener('touchmove', (e) => {
    e.preventDefault();
    const touch = e.touches[0];
    OrbArena.state.touchCurrent = { x: touch.clientX, y: touch.clientY };
}, { passive: false });

OrbArena.render.canvas.addEventListener('touchend', (e) => {
    e.preventDefault();
    OrbArena.state.touchOrigin = null;
    OrbArena.state.touchCurrent = null;
}, { passive: false });

// ── Keyboard Events ──

document.addEventListener('keyup', (e) => OrbArena.state.keysHeld.delete(e.code));

document.addEventListener('keydown', (e) => {
    const state = OrbArena.state.state;
    const ns = OrbArena.state;

    if (e.code === 'Space' && state.playing && state.connectionMode !== 'spectate' && state.you && state.you.alive) {
        e.preventDefault();
        if (state.you.wormhole_held) {
            OrbArena.network.sendWormhole();
        } else {
            OrbArena.network.sendBoost();
        }
    }
    if (e.code === 'KeyC' && state.playing && state.connectionMode === 'player' && state.you && state.you.alive && !ns.isTouchDevice) {
        const worldX = ns.mouseX / ns.currentZoom + state.camera.x;
        const worldY = ns.mouseY / ns.currentZoom + state.camera.y;
        OrbArena.network.sendShoot(worldX, worldY);
    }
    if (e.code === 'KeyM' && state.playing && state.connectionMode === 'player' && state.you && state.you.alive) {
        OrbArena.network.sendPlaceMine();
    }
    if (e.code === 'KeyT' && state.playing && OrbArena.network.ws && OrbArena.network.ws.readyState === WebSocket.OPEN) {
        ns.keysHeld.add('KeyT');
        if (ns.keysHeld.has('Digit4')) {
            OrbArena.network.ws.send(JSON.stringify({ type: 'test_disasters' }));
        }
    }
    if (e.code === 'Digit4' && state.playing && OrbArena.network.ws && OrbArena.network.ws.readyState === WebSocket.OPEN) {
        ns.keysHeld.add('Digit4');
        if (ns.keysHeld.has('KeyT')) {
            OrbArena.network.ws.send(JSON.stringify({ type: 'test_disasters' }));
        }
    }
});

// ── Mobile Button Events ──

const boostBtn = document.getElementById('boost-btn');
const shootBtn = document.getElementById('shoot-btn');
const mineBtn = document.getElementById('mine-btn');

boostBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
    e.stopPropagation();
    boostBtn.classList.add('pressed');
    const state = OrbArena.state.state;
    if (state.you && state.you.wormhole_held) OrbArena.network.sendWormhole();
    else OrbArena.network.sendBoost();
}, { passive: false });

boostBtn.addEventListener('touchend', (e) => {
    e.preventDefault();
    e.stopPropagation();
    boostBtn.classList.remove('pressed');
}, { passive: false });

boostBtn.addEventListener('click', (e) => {
    e.preventDefault();
    if (OrbArena.state.isTouchDevice) return;
    const state = OrbArena.state.state;
    if (state.you && state.you.wormhole_held) OrbArena.network.sendWormhole();
    else OrbArena.network.sendBoost();
});

// Click to shoot (desktop)
OrbArena.render.canvas.addEventListener('click', (e) => {
    const state = OrbArena.state.state;
    if (!state.playing || !state.you || !state.you.alive) return;
    if (OrbArena.state.isTouchDevice) return;
    const worldX = e.clientX / OrbArena.state.currentZoom + state.camera.x;
    const worldY = e.clientY / OrbArena.state.currentZoom + state.camera.y;
    OrbArena.network.sendShoot(worldX, worldY);
});

shootBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
    e.stopPropagation();
    shootBtn.classList.add('pressed');
    OrbArena.state.isShootBtnHeld = true;
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    if (state.you && state.you.alive) {
        OrbArena.network.sendShoot(
            state.you.x + (ns.touchCurrent ? (ns.touchCurrent.x - (ns.touchOrigin ? ns.touchOrigin.x : 0)) * TOUCH_SENSITIVITY : 0),
            state.you.y + (ns.touchCurrent ? (ns.touchCurrent.y - (ns.touchOrigin ? ns.touchOrigin.y : 0)) * TOUCH_SENSITIVITY : 0)
        );
    }
}, { passive: false });

shootBtn.addEventListener('touchend', (e) => {
    e.preventDefault();
    e.stopPropagation();
    shootBtn.classList.remove('pressed');
    OrbArena.state.isShootBtnHeld = false;
}, { passive: false });

shootBtn.addEventListener('click', (e) => {
    e.preventDefault();
    if (OrbArena.state.isTouchDevice) return;
    const state = OrbArena.state.state;
    const ns = OrbArena.state;
    if (state.you && state.you.alive) {
        const worldX = ns.mouseX / ns.currentZoom + state.camera.x;
        const worldY = ns.mouseY / ns.currentZoom + state.camera.y;
        OrbArena.network.sendShoot(worldX, worldY);
    }
});

mineBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
    e.stopPropagation();
    mineBtn.classList.add('pressed');
    OrbArena.network.sendPlaceMine();
}, { passive: false });

mineBtn.addEventListener('touchend', (e) => {
    e.preventDefault();
    e.stopPropagation();
    mineBtn.classList.remove('pressed');
}, { passive: false });

mineBtn.addEventListener('click', (e) => {
    e.preventDefault();
    OrbArena.network.sendPlaceMine();
});

OrbArena.input = {};
