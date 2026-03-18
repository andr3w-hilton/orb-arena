window.OrbArena = window.OrbArena || {};

function gameLoop() {
    try {
        OrbArena.render.update();
        OrbArena.render.render();
    } catch (e) {
        console.error('Game loop error:', e);
    }
    requestAnimationFrame(gameLoop);
}

gameLoop();
