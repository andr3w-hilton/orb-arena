window.OrbArena = window.OrbArena || {};

OrbArena.config = {
    POWERUP_COLORS: {
        shield: { bg: 'rgba(200, 180, 0, 0.3)', border: '#ffd700', text: '#ffd700', name: 'SHIELD' },
        rapid_fire: { bg: 'rgba(200, 80, 0, 0.3)', border: '#ff6632', text: '#ff6632', name: 'RAPID FIRE' },
        magnet: { bg: 'rgba(0, 150, 50, 0.3)', border: '#00ff88', text: '#00ff88', name: 'MAGNET' },
        phantom: { bg: 'rgba(0, 150, 200, 0.3)', border: '#00d4ff', text: '#00d4ff', name: 'PHANTOM' },
        speed_force: { bg: 'rgba(255, 220, 0, 0.3)', border: '#ffee00', text: '#ffee00', name: 'SPEED FORCE' },
        trail: { bg: 'rgba(0, 80, 255, 0.3)', border: '#0080ff', text: '#0080ff', name: 'TRON TRAIL' },
        // homing_missiles removed - now ammo-based, not a timed power-up
    },
    DISASTER_NAMES: {
        black_hole: 'BLACK HOLE',
        meteor_shower: 'METEOR SHOWER',
        fog_of_war: 'FOG OF WAR',
        feeding_frenzy: 'FEEDING FRENZY',
        supernova: 'SUPERNOVA',
        earthquake: 'EARTHQUAKE'
    },
    PROJECTILE_MIN_RADIUS: 25,
};
