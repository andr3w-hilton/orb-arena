window.OrbArena = window.OrbArena || {};

const state = {
    connected: false,
    playing: false,
    connectionMode: 'player',  // 'player', 'spectate', or 'challenge'
    you: null,
    players: [],
    energyOrbs: [],
    spikeOrbs: [],
    goldenOrbs: [],
    projectiles: [],
    powerupOrbs: [],
    minePickups: [],
    mines: [],
    trailSegments: [],
    powerupPopup: null,
    walls: [],
    killFeed: [],
    world: { width: 2000, height: 2000 },
    leaderboard: [],
    camera: { x: 0, y: 0 },
    lastScore: 0,
    disaster: { active: null, warning: null },
    audioVolume: 0.5,
    audioMuted: false,
    // Challenge mode
    challengeMode: false,
    challengeName: '',
    challengeData: null,
    welcomeTurrets: [],
    welcomeTrackWaypoints: [],
    boss: null,
    // Rally countdown animation state
    rallyCountdownDigit: 0,
    rallyCountdownDigitTime: 0,
    rallyGoUntil: 0,
};

OrbArena.state = {
    state,

    // VFX arrays
    particles: [],
    killPopups: [],
    killRings: [],
    prevStrikeMap: new Map(), // id -> {x, y} for impact VFX tracking

    // Camera shake
    vfxShakeIntensity: 0,
    vfxShakeX: 0,
    vfxShakeY: 0,

    // Diff-tracking vars for sound triggers
    prevEnergyOrbs: new Map(),
    prevGoldenOrbs: new Map(),
    prevSpikeOrbs: new Map(),
    prevMines: new Map(),
    prevDisasterWarning: null,
    prevDisasterActive: null,
    prevActivePowerup: null,
    prevHomingMissiles: 0,
    ambientStarted: false,
    supernovaPulsesPlayed: 0,
    seenMeteorKeys: new Set(),

    // Zoom
    currentZoom: 1.0,
    targetZoom: 1.0,

    // Input state
    mouseX: 0,
    mouseY: 0,
    isTouchDevice: false,
    isMouseDown: false,
    isShootBtnHeld: false,

    // Touch
    touchOrigin: null,
    touchCurrent: null,

    // Held keys
    keysHeld: new Set(),
};
