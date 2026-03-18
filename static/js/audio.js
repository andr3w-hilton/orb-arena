window.OrbArena = window.OrbArena || {};

let audioCtx = null;

function actx() {
    if (!audioCtx) audioCtx = new AudioContext();
    return audioCtx;
}

function vol() {
    return OrbArena.state.state.audioMuted ? 0 : OrbArena.state.state.audioVolume;
}

function gain(v) {
    const g = actx().createGain();
    g.gain.value = v * vol();
    g.connect(actx().destination);
    return g;
}

function tone(freq, type, attack, decay, volume, detune) {
    const ac = actx();
    const osc = ac.createOscillator();
    const g = ac.createGain();
    osc.type = type || 'sine';
    osc.frequency.value = freq;
    if (detune) osc.detune.value = detune;
    g.gain.setValueAtTime(0, ac.currentTime);
    g.gain.linearRampToValueAtTime(volume * vol(), ac.currentTime + attack);
    g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + attack + decay);
    osc.connect(g);
    g.connect(ac.destination);
    osc.start(ac.currentTime);
    osc.stop(ac.currentTime + attack + decay + 0.05);
    return { osc, gain: g };
}

function noise(duration, volume, filterFreq, filterType) {
    const ac = actx();
    const buf = ac.createBuffer(1, ac.sampleRate * duration, ac.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    const src = ac.createBufferSource();
    src.buffer = buf;
    const filter = ac.createBiquadFilter();
    filter.type = filterType || 'lowpass';
    filter.frequency.value = filterFreq || 2000;
    const g = ac.createGain();
    g.gain.setValueAtTime(volume * vol(), ac.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + duration);
    src.connect(filter);
    filter.connect(g);
    g.connect(ac.destination);
    src.start();
    return { src, gain: g, filter };
}

const sfx = {
    shoot() {
        const ac = actx();
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(900, ac.currentTime);
        osc.frequency.exponentialRampToValueAtTime(200, ac.currentTime + 0.12);
        g.gain.setValueAtTime(0.3 * vol(), ac.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.12);
        osc.connect(g); g.connect(ac.destination);
        osc.start(); osc.stop(ac.currentTime + 0.15);
    },
    rapidShoot() {
        // Bassier, punchier rapid fire shot - lower freq, shorter, less piercing
        const ac = actx();
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(400, ac.currentTime);
        osc.frequency.exponentialRampToValueAtTime(120, ac.currentTime + 0.08);
        g.gain.setValueAtTime(0.2 * vol(), ac.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.08);
        osc.connect(g); g.connect(ac.destination);
        osc.start(); osc.stop(ac.currentTime + 0.1);
        // Sub thump for weight
        const sub = ac.createOscillator();
        const sg = ac.createGain();
        sub.type = 'sine';
        sub.frequency.setValueAtTime(80, ac.currentTime);
        sub.frequency.exponentialRampToValueAtTime(40, ac.currentTime + 0.06);
        sg.gain.setValueAtTime(0.15 * vol(), ac.currentTime);
        sg.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.07);
        sub.connect(sg); sg.connect(ac.destination);
        sub.start(); sub.stop(ac.currentTime + 0.09);
    },
    homingShoot() {
        // Deep bass whoosh with rising sweep
        const ac = actx();
        const sub = ac.createOscillator();
        const gs = ac.createGain();
        sub.type = 'sine';
        sub.frequency.setValueAtTime(40, ac.currentTime);
        sub.frequency.exponentialRampToValueAtTime(80, ac.currentTime + 0.15);
        sub.frequency.exponentialRampToValueAtTime(30, ac.currentTime + 0.35);
        gs.gain.setValueAtTime(0.5 * vol(), ac.currentTime);
        gs.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.4);
        sub.connect(gs); gs.connect(ac.destination);
        sub.start(); sub.stop(ac.currentTime + 0.45);
        const buf = ac.createBuffer(1, ac.sampleRate * 0.4, ac.sampleRate);
        const data = buf.getChannelData(0);
        for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
        const src = ac.createBufferSource();
        src.buffer = buf;
        const filter = ac.createBiquadFilter();
        filter.type = 'bandpass';
        filter.frequency.setValueAtTime(200, ac.currentTime);
        filter.frequency.exponentialRampToValueAtTime(2500, ac.currentTime + 0.2);
        filter.frequency.exponentialRampToValueAtTime(600, ac.currentTime + 0.35);
        filter.Q.value = 1.5;
        const g = ac.createGain();
        g.gain.setValueAtTime(0.35 * vol(), ac.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.4);
        src.connect(filter); filter.connect(g); g.connect(ac.destination);
        src.start();
        const sweep = ac.createOscillator();
        const sg = ac.createGain();
        sweep.type = 'sine';
        sweep.frequency.setValueAtTime(120, ac.currentTime);
        sweep.frequency.exponentialRampToValueAtTime(500, ac.currentTime + 0.25);
        sg.gain.setValueAtTime(0.15 * vol(), ac.currentTime);
        sg.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.3);
        sweep.connect(sg); sg.connect(ac.destination);
        sweep.start(); sweep.stop(ac.currentTime + 0.35);
    },
    hit() {
        noise(0.08, 0.35, 1500, 'bandpass');
        tone(80, 'sine', 0.005, 0.1, 0.3);
    },
    kill() {
        const ac = actx();
        noise(0.1, 0.4, 1800, 'bandpass');
        const sub = ac.createOscillator();
        const gs = ac.createGain();
        sub.type = 'sine';
        sub.frequency.setValueAtTime(70, ac.currentTime);
        sub.frequency.exponentialRampToValueAtTime(35, ac.currentTime + 0.15);
        gs.gain.setValueAtTime(0.4 * vol(), ac.currentTime);
        gs.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.2);
        sub.connect(gs); gs.connect(ac.destination);
        sub.start(); sub.stop(ac.currentTime + 0.25);
        setTimeout(() => { tone(500, 'sine', 0.01, 0.25, 0.2); tone(500, 'triangle', 0.01, 0.25, 0.08); }, 60);
        setTimeout(() => { tone(630, 'sine', 0.01, 0.25, 0.18); }, 120);
        setTimeout(() => { tone(750, 'sine', 0.01, 0.3, 0.16); tone(1000, 'sine', 0.01, 0.2, 0.08); }, 180);
        setTimeout(() => tone(1500, 'sine', 0.005, 0.15, 0.06), 220);
    },
    death() {
        const ac = actx();
        const sub = ac.createOscillator();
        const gs = ac.createGain();
        sub.type = 'sine';
        sub.frequency.setValueAtTime(60, ac.currentTime);
        sub.frequency.exponentialRampToValueAtTime(18, ac.currentTime + 0.8);
        gs.gain.setValueAtTime(0.5 * vol(), ac.currentTime);
        gs.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.9);
        sub.connect(gs); gs.connect(ac.destination);
        sub.start(); sub.stop(ac.currentTime + 1.0);
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(300, ac.currentTime);
        osc.frequency.exponentialRampToValueAtTime(30, ac.currentTime + 0.9);
        g.gain.setValueAtTime(0.3 * vol(), ac.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 1.0);
        const shaper = ac.createWaveShaper();
        const curve = new Float32Array(256);
        for (let i = 0; i < 256; i++) { const x = (i / 128) - 1; curve[i] = Math.tanh(x * 3); }
        shaper.curve = curve;
        osc.connect(shaper); shaper.connect(g); g.connect(ac.destination);
        osc.start(); osc.stop(ac.currentTime + 1.1);
        noise(0.25, 0.35, 600, 'lowpass');
        setTimeout(() => noise(0.3, 0.12, 2500, 'bandpass'), 200);
    },
    boost() {
        const ac = actx();
        const buf = ac.createBuffer(1, ac.sampleRate * 0.3, ac.sampleRate);
        const data = buf.getChannelData(0);
        for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
        const src = ac.createBufferSource();
        src.buffer = buf;
        const filter = ac.createBiquadFilter();
        filter.type = 'bandpass';
        filter.frequency.setValueAtTime(500, ac.currentTime);
        filter.frequency.exponentialRampToValueAtTime(3000, ac.currentTime + 0.1);
        filter.frequency.exponentialRampToValueAtTime(800, ac.currentTime + 0.25);
        filter.Q.value = 2;
        const g = ac.createGain();
        g.gain.setValueAtTime(0.3 * vol(), ac.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.3);
        src.connect(filter); filter.connect(g); g.connect(ac.destination);
        src.start();
    },
    mineDrop() {
        tone(800, 'square', 0.005, 0.04, 0.15);
        tone(100, 'sine', 0.01, 0.15, 0.25);
        noise(0.05, 0.1, 3000, 'highpass');
    },
    mineExplode() {
        const ac = actx();
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(80, ac.currentTime);
        osc.frequency.exponentialRampToValueAtTime(20, ac.currentTime + 0.4);
        g.gain.setValueAtTime(0.5 * vol(), ac.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.5);
        osc.connect(g); g.connect(ac.destination);
        osc.start(); osc.stop(ac.currentTime + 0.55);
        noise(0.3, 0.4, 1200, 'lowpass');
        setTimeout(() => noise(0.15, 0.15, 4000, 'highpass'), 50);
    },
    orbPickup() {
        tone(680, 'sine', 0.003, 0.035, 0.06);
    },
    goldenPickup() {
        tone(800, 'sine', 0.005, 0.1, 0.1);
        setTimeout(() => tone(1000, 'sine', 0.005, 0.12, 0.08), 70);
    },
    spikeHit() {
        const ac = actx();
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.type = 'square';
        osc.frequency.setValueAtTime(200, ac.currentTime);
        osc.frequency.exponentialRampToValueAtTime(80, ac.currentTime + 0.15);
        g.gain.setValueAtTime(0.2 * vol(), ac.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.2);
        osc.connect(g); g.connect(ac.destination);
        osc.start(); osc.stop(ac.currentTime + 0.25);
        noise(0.08, 0.2, 1000, 'bandpass');
    },
    powerupPickup() {
        const ac = actx();
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(400, ac.currentTime);
        osc.frequency.exponentialRampToValueAtTime(1200, ac.currentTime + 0.2);
        g.gain.setValueAtTime(0.25 * vol(), ac.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.3);
        osc.connect(g); g.connect(ac.destination);
        osc.start(); osc.stop(ac.currentTime + 0.35);
        setTimeout(() => tone(1400, 'sine', 0.01, 0.15, 0.1), 100);
    },
    powerupExpire() {
        const ac = actx();
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(600, ac.currentTime);
        osc.frequency.exponentialRampToValueAtTime(200, ac.currentTime + 0.25);
        g.gain.setValueAtTime(0.15 * vol(), ac.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.3);
        osc.connect(g); g.connect(ac.destination);
        osc.start(); osc.stop(ac.currentTime + 0.35);
    },
    disasterWarning() {
        const ac = actx();
        const play = (offset) => {
            const buf = ac.createBuffer(1, ac.sampleRate * 0.7, ac.sampleRate);
            const data = buf.getChannelData(0);
            for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
            const src = ac.createBufferSource();
            src.buffer = buf;
            const filter = ac.createBiquadFilter();
            filter.type = 'lowpass'; filter.frequency.value = 140; filter.Q.value = 1.5;
            const g = ac.createGain();
            g.gain.setValueAtTime(0.001, ac.currentTime + offset);
            g.gain.linearRampToValueAtTime(0.1 * vol(), ac.currentTime + offset + 0.15);
            g.gain.linearRampToValueAtTime(0.1 * vol(), ac.currentTime + offset + 0.3);
            g.gain.linearRampToValueAtTime(0.001, ac.currentTime + offset + 0.5);
            src.connect(filter); filter.connect(g); g.connect(ac.destination);
            src.start(ac.currentTime + offset);
            const sub = ac.createOscillator();
            const gss = ac.createGain();
            sub.type = 'sine';
            sub.frequency.setValueAtTime(50, ac.currentTime + offset);
            sub.frequency.linearRampToValueAtTime(70, ac.currentTime + offset + 0.3);
            sub.frequency.linearRampToValueAtTime(45, ac.currentTime + offset + 0.55);
            gss.gain.setValueAtTime(0.001, ac.currentTime + offset);
            gss.gain.linearRampToValueAtTime(0.25 * vol(), ac.currentTime + offset + 0.12);
            gss.gain.linearRampToValueAtTime(0.25 * vol(), ac.currentTime + offset + 0.35);
            gss.gain.linearRampToValueAtTime(0.001, ac.currentTime + offset + 0.6);
            sub.connect(gss); gss.connect(ac.destination);
            sub.start(ac.currentTime + offset); sub.stop(ac.currentTime + offset + 0.65);
            const mid = ac.createOscillator();
            const gm = ac.createGain();
            mid.type = 'triangle'; mid.frequency.value = 220;
            gm.gain.setValueAtTime(0.001, ac.currentTime + offset + 0.05);
            gm.gain.linearRampToValueAtTime(0.05 * vol(), ac.currentTime + offset + 0.2);
            gm.gain.linearRampToValueAtTime(0.001, ac.currentTime + offset + 0.4);
            mid.connect(gm); gm.connect(ac.destination);
            mid.start(ac.currentTime + offset); mid.stop(ac.currentTime + offset + 0.45);
        };
        play(0); play(0.75); play(1.5);
    },
    meteorImpact() {
        const ac = actx();
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(150, ac.currentTime);
        osc.frequency.exponentialRampToValueAtTime(30, ac.currentTime + 0.2);
        g.gain.setValueAtTime(0.35 * vol(), ac.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.25);
        osc.connect(g); g.connect(ac.destination);
        osc.start(); osc.stop(ac.currentTime + 0.3);
        noise(0.15, 0.25, 600, 'lowpass');
    },
    supernovaPulse() {
        const ac = actx();
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(200, ac.currentTime);
        osc.frequency.exponentialRampToValueAtTime(40, ac.currentTime + 0.5);
        g.gain.setValueAtTime(0.35 * vol(), ac.currentTime);
        g.gain.linearRampToValueAtTime(0.4 * vol(), ac.currentTime + 0.05);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.6);
        osc.connect(g); g.connect(ac.destination);
        osc.start(); osc.stop(ac.currentTime + 0.65);
        tone(1000, 'sine', 0.05, 0.4, 0.08);
    },
    blackHoleHum() {
        const ac = actx();
        const osc1 = ac.createOscillator();
        const osc2 = ac.createOscillator();
        const g = ac.createGain();
        osc1.type = 'sine'; osc1.frequency.value = 50;
        osc2.type = 'sine'; osc2.frequency.value = 53;
        g.gain.setValueAtTime(0.001, ac.currentTime);
        g.gain.linearRampToValueAtTime(0.25 * vol(), ac.currentTime + 0.3);
        g.gain.setValueAtTime(0.25 * vol(), ac.currentTime + 1.5);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 2.0);
        osc1.connect(g); osc2.connect(g); g.connect(ac.destination);
        osc1.start(); osc2.start();
        osc1.stop(ac.currentTime + 2.1); osc2.stop(ac.currentTime + 2.1);
        noise(2.0, 0.08, 200, 'lowpass');
    },
    earthquakeRumble() {
        const ac = actx();
        const buf = ac.createBuffer(1, ac.sampleRate * 1.5, ac.sampleRate);
        const data = buf.getChannelData(0);
        for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
        const src = ac.createBufferSource();
        src.buffer = buf;
        const filter = ac.createBiquadFilter();
        filter.type = 'lowpass'; filter.frequency.value = 150; filter.Q.value = 3;
        const g = ac.createGain();
        g.gain.setValueAtTime(0.001, ac.currentTime);
        g.gain.linearRampToValueAtTime(0.35 * vol(), ac.currentTime + 0.2);
        g.gain.setValueAtTime(0.35 * vol(), ac.currentTime + 1.0);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 1.5);
        src.connect(filter); filter.connect(g); g.connect(ac.destination);
        src.start();
        tone(35, 'sine', 0.1, 1.3, 0.25);
    },
    feedingFrenzy() {
        const notes = [523, 659, 784, 1047];
        notes.forEach((freq, i) => { setTimeout(() => tone(freq, 'sine', 0.01, 0.2, 0.18), i * 70); });
    },
    respawn() {
        const ac = actx();
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(200, ac.currentTime);
        osc.frequency.exponentialRampToValueAtTime(800, ac.currentTime + 0.15);
        g.gain.setValueAtTime(0.001, ac.currentTime);
        g.gain.linearRampToValueAtTime(0.2 * vol(), ac.currentTime + 0.05);
        g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.3);
        osc.connect(g); g.connect(ac.destination);
        osc.start(); osc.stop(ac.currentTime + 0.35);
        setTimeout(() => tone(1000, 'sine', 0.01, 0.15, 0.12), 120);
    }
};

// Looping disaster sound management
let disasterLoopTimer = null;

function startDisasterLoop(type) {
    stopDisasterLoop();
    if (type === 'black_hole') {
        sfx.blackHoleHum();
        disasterLoopTimer = setInterval(() => sfx.blackHoleHum(), 2000);
    } else if (type === 'earthquake') {
        sfx.earthquakeRumble();
        disasterLoopTimer = setInterval(() => sfx.earthquakeRumble(), 1500);
    }
}

function stopDisasterLoop() {
    if (disasterLoopTimer) {
        clearInterval(disasterLoopTimer);
        disasterLoopTimer = null;
    }
}

// Ambient music engine - Cosmic Hum with generative melody
const ambient = {
    playing: false,
    nodes: [],
    masterGain: null,
    _melodyRunning: false,
    _melodyTimer: null,
    _fadeOutTimer: null,

    start() {
        if (this.playing || OrbArena.state.state.playing) return;
        const ac = actx();
        this.playing = true;
        this.masterGain = ac.createGain();
        this.masterGain.gain.value = vol() * 0.3;
        this.masterGain.connect(ac.destination);
        this._cosmicHum(ac);
    },

    stop() {
        this.playing = false;
        this._melodyRunning = false;
        if (this._melodyTimer) { clearTimeout(this._melodyTimer); this._melodyTimer = null; }
        if (this._fadeOutTimer) { clearTimeout(this._fadeOutTimer); this._fadeOutTimer = null; }
        this.nodes.forEach(n => { try { n.stop(); } catch(e) {} try { n.disconnect(); } catch(e) {} });
        this.nodes = [];
        if (this.masterGain) { try { this.masterGain.disconnect(); } catch(e) {} this.masterGain = null; }
    },

    fadeOut(duration) {
        if (!this.playing || !this.masterGain) return;
        const ac = actx();
        const now = ac.currentTime;
        this.masterGain.gain.setValueAtTime(this.masterGain.gain.value, now);
        this.masterGain.gain.linearRampToValueAtTime(0.001, now + (duration || 2));
        this._melodyRunning = false;
        if (this._melodyTimer) { clearTimeout(this._melodyTimer); this._melodyTimer = null; }
        this._fadeOutTimer = setTimeout(() => { this._fadeOutTimer = null; this.stop(); }, (duration || 2) * 1000 + 100);
    },

    fadeIn() {
        this.stop();
        const ac = actx();
        this.playing = true;
        this.masterGain = ac.createGain();
        this.masterGain.gain.setValueAtTime(0.001, ac.currentTime);
        this.masterGain.gain.linearRampToValueAtTime(vol() * 0.3, ac.currentTime + 3);
        this.masterGain.connect(ac.destination);
        this._cosmicHum(ac);
    },

    updateVolume() {
        if (this.masterGain) {
            this.masterGain.gain.setTargetAtTime(vol() * 0.3, actx().currentTime, 0.1);
        }
    },

    _cosmicHum(ac) {
        const t = ac.currentTime;
        const baseFreq = 55;
        for (let h = 1; h <= 6; h++) {
            const osc = ac.createOscillator();
            osc.type = h <= 2 ? 'sine' : 'triangle';
            osc.frequency.value = baseFreq * h;
            const lfo = ac.createOscillator();
            const lfoG = ac.createGain();
            lfo.type = 'sine';
            lfo.frequency.value = 0.02 + h * 0.015;
            lfoG.gain.value = baseFreq * h * 0.006;
            lfo.connect(lfoG); lfoG.connect(osc.frequency);
            const g = ac.createGain();
            const level = 0.12 / (h * 0.7);
            g.gain.setValueAtTime(0.001, t);
            g.gain.linearRampToValueAtTime(level, t + 2 + h * 0.3);
            osc.connect(g); g.connect(this.masterGain);
            osc.start(t); lfo.start(t);
            this.nodes.push(osc, lfo);
        }
        // Shimmer noise
        const noiseBuf = ac.createBuffer(1, ac.sampleRate * 4, ac.sampleRate);
        const nd = noiseBuf.getChannelData(0);
        for (let i = 0; i < nd.length; i++) nd[i] = Math.random() * 2 - 1;
        const ns = ac.createBufferSource();
        ns.buffer = noiseBuf; ns.loop = true;
        const nf = ac.createBiquadFilter();
        nf.type = 'bandpass'; nf.frequency.value = 3000; nf.Q.value = 2;
        const nLfo = ac.createOscillator();
        const nLfoG = ac.createGain();
        nLfo.type = 'sine'; nLfo.frequency.value = 0.025; nLfoG.gain.value = 2000;
        nLfo.connect(nLfoG); nLfoG.connect(nf.frequency);
        const aLfo = ac.createOscillator();
        const aLfoG = ac.createGain();
        aLfo.type = 'sine'; aLfo.frequency.value = 0.06; aLfoG.gain.value = 0.015;
        const nG = ac.createGain();
        nG.gain.value = 0.02;
        aLfo.connect(aLfoG); aLfoG.connect(nG.gain);
        ns.connect(nf); nf.connect(nG); nG.connect(this.masterGain);
        ns.start(t); nLfo.start(t); aLfo.start(t);
        this.nodes.push(ns, nLfo, aLfo);
        // Generative melody
        const melodyNotes = [220, 261.6, 293.7, 330, 392, 440, 523.3, 587.3, 659.3, 784];
        this._melodyRunning = true;
        const playNote = () => {
            if (!this._melodyRunning || !this.playing) return;
            const ac2 = actx();
            const now = ac2.currentTime;
            const noteCount = Math.random() < 0.35 ? 2 : 1;
            for (let n = 0; n < noteCount; n++) {
                const freq = melodyNotes[Math.floor(Math.random() * melodyNotes.length)];
                const delay = n * (0.3 + Math.random() * 0.4);
                const duration = 2.5 + Math.random() * 3;
                const peak = 0.04 + Math.random() * 0.03;
                const fadeIn = 0.4 + Math.random() * 0.6;
                const osc = ac2.createOscillator();
                osc.type = 'sine'; osc.frequency.value = freq;
                const vib = ac2.createOscillator();
                const vibG = ac2.createGain();
                vib.type = 'sine'; vib.frequency.value = 3 + Math.random() * 2;
                vibG.gain.value = freq * 0.003;
                vib.connect(vibG); vibG.connect(osc.frequency);
                const g = ac2.createGain();
                g.gain.setValueAtTime(0.001, now + delay);
                g.gain.linearRampToValueAtTime(peak, now + delay + fadeIn);
                g.gain.setValueAtTime(peak, now + delay + fadeIn + 0.1);
                g.gain.linearRampToValueAtTime(0.001, now + delay + duration);
                osc.connect(g); g.connect(this.masterGain);
                osc.start(now + delay); osc.stop(now + delay + duration + 0.05);
                vib.start(now + delay); vib.stop(now + delay + duration + 0.05);
            }
            this._melodyTimer = setTimeout(playNote, 2000 + Math.random() * 3000);
        };
        this._melodyTimer = setTimeout(playNote, 4000);
    }
};

OrbArena.audio = {
    sfx,
    ambient,
    startDisasterLoop,
    stopDisasterLoop,
    get disasterLoopTimer() { return disasterLoopTimer; },
    set disasterLoopTimer(v) { disasterLoopTimer = v; },
    get audioCtx() { return actx(); },
};
