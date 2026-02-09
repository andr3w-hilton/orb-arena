"""
Orb Arena - Multiplayer WebSocket Game Server
A competitive arena game where players control orbs, collect energy, and consume smaller players.
"""

import asyncio
import json
import random
import math
import time

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("Using uvloop (faster async)")
except ImportError:
    pass  # Falls back to default asyncio loop

import websockets
from websockets.exceptions import ConnectionClosed
from dataclasses import dataclass
from typing import Dict, Set, Optional
import colorsys
import socket
import http.server
import threading
import os
import re

# Game configuration
WORLD_WIDTH = 5000
WORLD_HEIGHT = 5000
INITIAL_RADIUS = 20
MAX_RADIUS = 150
MIN_RADIUS = 10
BASE_SPEED = 14
SPEED_SCALING = 0.2  # Higher = more speed difference between small and large
ENERGY_ORB_COUNT = 625
ENERGY_ORB_VALUE = 2
ENERGY_ORB_RADIUS = 8
SPIKE_ORB_COUNT = 90  # Evil spike orbs
SPIKE_ORB_RADIUS = 12
GOLDEN_ORB_COUNT = 30  # Rare golden orbs
GOLDEN_ORB_VALUE = 10  # 5x energy orb value
GOLDEN_ORB_RADIUS = 12
TICK_RATE = 1 / 30  # 30 FPS (reduced from 60 for memory efficiency)
SHRINK_RATE = 0.02  # Slowly shrink over time
CONSUME_RATIO = 1.2  # Must be 20% larger to consume another player

# Boost/Dash configuration
BOOST_SPEED_MULTIPLIER = 2.5
BOOST_DURATION = 0.25  # seconds
BOOST_COOLDOWN = 3.0  # seconds
BOOST_MASS_COST = 3  # radius cost to boost

# Projectile/Shooting configuration
PROJECTILE_SPEED = 25
PROJECTILE_RADIUS = 5
PROJECTILE_LIFETIME = 2.0  # seconds
PROJECTILE_RAPID_FIRE_LIFETIME = 3.2  # seconds (40% of map at speed 25)
PROJECTILE_DAMAGE = 10  # radius removed from target
PROJECTILE_COST = 5  # radius cost to shooter
PROJECTILE_COOLDOWN = 0.5  # seconds between shots
PROJECTILE_MIN_RADIUS = 25  # must be this big to shoot

# Critical mass configuration
CRITICAL_MASS_THRESHOLD = 100  # radius threshold to start timer
CRITICAL_MASS_TIMER = 30.0  # seconds before explosion

# Power-up configuration
POWERUP_COUNT = 5  # max on map at once
POWERUP_RADIUS = 14
POWERUP_RESPAWN_DELAY = 30.0  # seconds before replacement spawns
POWERUP_TYPES = ["shield", "rapid_fire", "magnet", "phantom"]
POWERUP_DURATIONS = {"shield": 5.0, "rapid_fire": 5.0, "magnet": 8.0, "phantom": 5.0}
MAGNET_RANGE = 300  # radius for magnet pull
MAGNET_STRENGTH = 10  # speed orbs move toward player

# Respawn invincibility
RESPAWN_INVINCIBILITY = 3.0  # seconds

# Kill feed
KILL_FEED_MAX = 5  # max messages to show
KILL_FEED_DURATION = 5.0  # seconds before message expires

# Walls/Obstacles
WALL_COUNT = 20

# ── Natural Disaster Configuration ──
DISASTER_MIN_INTERVAL = 290.0  # ~5 minutes between disasters (minus jitter)
DISASTER_MAX_INTERVAL = 330.0  # ~5 minutes + 10-30s jitter
DISASTER_WARNING_TIME = 5.0    # seconds of warning before disaster hits
DISASTER_MIN_PLAYERS = 2       # need at least 2 players to trigger
DISASTER_SETTLE_TIME = 120.0   # 2 min grace period after lobby first fills

# Black Hole
BLACK_HOLE_DURATION = 30.0
BLACK_HOLE_MAX_RADIUS = 80     # visual/kill radius at full size
BLACK_HOLE_PULL_RANGE = 750    # gravitational pull range
BLACK_HOLE_PULL_STRENGTH = 18  # base pull speed (scaled by distance)
BLACK_HOLE_MASS_FACTOR = 0.7   # smaller players pulled harder (inverse mass)

# Meteor Shower
METEOR_SHOWER_DURATION = 10.0
METEOR_INTERVAL = 0.15         # seconds between meteor strikes
METEOR_DAMAGE = 8              # radius removed on hit
METEOR_BLAST_RADIUS = 40       # area of effect per meteor
METEOR_COUNT_PER_WAVE = 3      # meteors per interval tick

# Fog of War
FOG_DURATION = 15.0
FOG_VISIBILITY_RADIUS = 300    # pixels around player

# Feeding Frenzy
FRENZY_DURATION = 10.0
FRENZY_ORB_COUNT = 1500        # orbs spawned at start

# Supernova
SUPERNOVA_RADIUS = 900         # blast radius from center
SUPERNOVA_PULSE_COUNT = 5      # number of ripple pulses
SUPERNOVA_PULSE_INTERVAL = 1.5 # seconds between each pulse
SUPERNOVA_PULSE_EXPAND_TIME = 1.2  # seconds for each ring to expand
SUPERNOVA_MASS_LOSS_MIN = 0.08 # 8% mass loss per pulse (5 pulses ≈ 34% total)
SUPERNOVA_MASS_LOSS_MAX = 0.12 # 12% mass loss per pulse (5 pulses ≈ 47% total)

# Earthquake
EARTHQUAKE_DURATION = 3.0      # wall transition time

# Derived / internal constants
WALL_COLLISION_ITERATIONS = 3          # stability passes for wall push-out
MOVE_THRESHOLD_SQ = 25                 # 5^2 - minimum distance before moving
KILL_BASE_SCORE = 100                  # base score for consuming a player
KILL_SCORE_RATIO = 0.1                 # fraction of victim's score awarded as bonus
BLACK_HOLE_INITIAL_RADIUS = 5.0        # starting radius before growth
BLACK_HOLE_KILL_RADIUS_FACTOR = 0.5    # fraction of current_radius that kills
BLACK_HOLE_ORB_PULL_STRENGTH = 8       # orb-specific pull strength
BLACK_HOLE_EXIT_ORB_COUNT = 30         # orbs scattered on collapse
METEOR_MARKER_DURATION = 0.5           # seconds to keep impact marker visible


@dataclass
class BaseOrb:
    """Base class for all orb types with shared serialization."""
    id: str
    x: float
    y: float
    radius: float = 0
    color: str = ""

    def to_dict(self):
        return {"id": self.id, "x": round(self.x, 1), "y": round(self.y, 1), "radius": self.radius, "color": self.color}


@dataclass
class EnergyOrb(BaseOrb):
    radius: float = ENERGY_ORB_RADIUS
    color: str = "#00ff88"


@dataclass
class SpikeOrb(BaseOrb):
    radius: float = SPIKE_ORB_RADIUS
    color: str = "#ff2266"


@dataclass
class GoldenOrb(BaseOrb):
    radius: float = GOLDEN_ORB_RADIUS
    color: str = "#ffd700"


@dataclass
class PowerUpOrb(BaseOrb):
    radius: float = POWERUP_RADIUS
    color: str = "#dd44ff"


@dataclass
class Projectile:
    id: str
    owner_id: str
    x: float
    y: float
    dx: float  # normalized direction
    dy: float
    radius: float = PROJECTILE_RADIUS
    color: str = "#ffffff"
    created_at: float = 0.0
    lifetime: float = PROJECTILE_LIFETIME

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "radius": self.radius,
            "color": self.color
        }


@dataclass
class Wall:
    id: str
    x: float
    y: float
    width: float
    height: float
    color: str = "#334455"

    def to_dict(self):
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "color": self.color
        }


@dataclass
class Meteor:
    x: float
    y: float
    radius: float = METEOR_BLAST_RADIUS
    impact_time: float = 0.0  # when it lands

    def to_dict(self):
        return {"x": round(self.x, 1), "y": round(self.y, 1), "radius": self.radius}


@dataclass
class BlackHole:
    x: float
    y: float
    current_radius: float = 5.0
    max_radius: float = BLACK_HOLE_MAX_RADIUS

    def to_dict(self):
        return {"x": round(self.x, 1), "y": round(self.y, 1), "radius": round(self.current_radius, 1)}


@dataclass
class Player:
    id: str
    name: str
    x: float
    y: float
    radius: float
    color: str
    target_x: float
    target_y: float
    score: int = 0
    alive: bool = True
    # Boost tracking
    boost_cooldown_until: float = 0
    boost_active_until: float = 0
    # Invincibility tracking
    invincible_until: float = 0
    # Shooting tracking
    shoot_cooldown_until: float = 0
    # Critical mass tracking
    critical_mass_start: float = 0  # timestamp when threshold crossed, 0 = inactive
    # Power-up tracking
    active_powerup: str = ""
    powerup_until: float = 0

    def to_dict(self, current_time: float):
        critical_mass_active = self.critical_mass_start > 0
        critical_mass_remaining = 0
        if critical_mass_active:
            elapsed = current_time - self.critical_mass_start
            critical_mass_remaining = max(0, CRITICAL_MASS_TIMER - elapsed)
        return {
            "id": self.id,
            "name": self.name,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "radius": round(self.radius, 1),
            "color": self.color,
            "score": self.score,
            "alive": self.alive,
            "is_boosting": current_time < self.boost_active_until,
            "boost_ready": current_time >= self.boost_cooldown_until,
            "is_invincible": current_time < self.invincible_until,
            "shoot_ready": current_time >= self.shoot_cooldown_until,
            "critical_mass_active": critical_mass_active,
            "critical_mass_remaining": round(critical_mass_remaining, 1),
            "active_powerup": self.active_powerup if current_time < self.powerup_until else "",
            "powerup_remaining": round(max(0, self.powerup_until - current_time), 1) if self.active_powerup else 0
        }

    def get_speed(self, current_time: float):
        # Larger players move slower, smaller players are much faster
        base = BASE_SPEED * (INITIAL_RADIUS / self.radius) ** SPEED_SCALING
        # Apply boost multiplier if active
        if current_time < self.boost_active_until:
            return base * BOOST_SPEED_MULTIPLIER
        return base

    def check_invincible(self, current_time: float):
        return current_time < self.invincible_until

    def has_protection(self, current_time: float) -> bool:
        """Check if player is protected by invincibility, shield, or phantom."""
        if current_time < self.invincible_until:
            return True
        return self.active_powerup in ("shield", "phantom") and current_time < self.powerup_until

    def has_shield(self, current_time: float) -> bool:
        """Check if player has an active shield power-up."""
        return self.active_powerup == "shield" and current_time < self.powerup_until


DISASTER_TYPES = ["black_hole", "meteor_shower", "fog_of_war", "feeding_frenzy", "supernova", "earthquake"]


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to a finite float, clamped to world bounds."""
    try:
        f = float(value)
        if not math.isfinite(f):
            return default
        # Clamp to reasonable world bounds to prevent absurd values
        return max(-1000, min(max(WORLD_WIDTH, WORLD_HEIGHT) + 1000, f))
    except (TypeError, ValueError):
        return default


def sanitize_name(raw: str) -> str:
    """Sanitize a player name: strip HTML/control chars, collapse whitespace, limit length."""
    # Strip HTML tags
    name = re.sub(r'<[^>]*>', '', raw)
    # Strip control characters and zero-width chars
    name = re.sub(r'[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff]', '', name)
    # Collapse whitespace
    name = ' '.join(name.split())
    # Limit length
    name = name[:15].strip()
    return name if name else "Anonymous"


class DisasterManager:
    """Manages natural disaster scheduling and execution."""

    def __init__(self, game):
        self.game = game
        self.active_disaster: Optional[str] = None
        self.disaster_start: float = 0
        self.disaster_end: float = 0
        self.warning_active: bool = False
        self.warning_type: str = ""
        self.warning_start: float = 0
        # Scheduling — timer is paused until enough players join
        self.next_disaster_time: float = 0  # 0 = not scheduled yet
        self.lobby_ready_since: float = 0   # when player count first hit minimum
        self.timer_paused: bool = True       # paused until lobby is ready
        # Black hole state
        self.black_hole: Optional[BlackHole] = None
        # Meteor shower state
        self.meteors: list = []  # active meteor impact markers
        self.last_meteor_time: float = 0
        # Fog of war state
        self.fog_active: bool = False
        # Feeding frenzy state
        self.frenzy_orb_ids: list = []  # track frenzy orbs for cleanup
        # Supernova state
        self.supernova_x: float = 0
        self.supernova_y: float = 0
        self.supernova_triggered: bool = False
        self.supernova_time: float = 0  # when the first pulse started
        self.supernova_pulses_fired: int = 0  # how many pulses have triggered
        # Earthquake state
        self.earthquake_progress: float = 0  # 0..1
        self.earthquake_old_walls: list = []
        self.earthquake_new_walls: list = []

    def _player_count(self) -> int:
        return len(self.game.players)

    def tick(self, current_time: float):
        """Called every game tick."""
        player_count = self._player_count()

        # ── Lobby readiness / timer management ──
        if player_count < DISASTER_MIN_PLAYERS:
            # Not enough players — pause timer and reset lobby readiness
            if not self.timer_paused:
                self.timer_paused = True
                self.next_disaster_time = 0
                self.lobby_ready_since = 0
            # If a warning was queued but players left, cancel it
            if self.warning_active and not self.active_disaster:
                self.warning_active = False
                self.warning_type = ""
            return

        # Enough players are present
        if self.timer_paused:
            # Lobby just became ready — start settle period
            self.lobby_ready_since = current_time
            self.timer_paused = False
            # Schedule first disaster after settle time + random interval
            self.next_disaster_time = (
                current_time + DISASTER_SETTLE_TIME
                + random.uniform(DISASTER_MIN_INTERVAL, DISASTER_MAX_INTERVAL)
            )
            return

        # Still in settle period — don't trigger yet
        if current_time - self.lobby_ready_since < DISASTER_SETTLE_TIME:
            return

        # ── Warning phase ──
        if not self.active_disaster and not self.warning_active:
            if self.next_disaster_time > 0 and current_time >= self.next_disaster_time:
                self.warning_type = random.choice(DISASTER_TYPES)
                self.warning_active = True
                self.warning_start = current_time
            return

        if self.warning_active and not self.active_disaster:
            if current_time - self.warning_start >= DISASTER_WARNING_TIME:
                self._start_disaster(self.warning_type, current_time)
                self.warning_active = False
            return

        # ── Active disaster tick ──
        if self.active_disaster:
            if current_time >= self.disaster_end:
                self._end_disaster(current_time)
            else:
                self._tick_disaster(current_time)

    def _start_disaster(self, dtype: str, current_time: float):
        self.active_disaster = dtype
        self.disaster_start = current_time
        starters = {
            "black_hole": self._start_black_hole,
            "meteor_shower": self._start_meteor_shower,
            "fog_of_war": self._start_fog_of_war,
            "feeding_frenzy": self._start_feeding_frenzy,
            "supernova": self._start_supernova,
            "earthquake": self._start_earthquake,
        }
        starters[dtype](current_time)

    def _start_black_hole(self, current_time: float):
        self.disaster_end = current_time + BLACK_HOLE_DURATION
        x, y = self.game.find_safe_orb_position(BLACK_HOLE_MAX_RADIUS)
        self.black_hole = BlackHole(x=x, y=y)

    def _start_meteor_shower(self, current_time: float):
        self.disaster_end = current_time + METEOR_SHOWER_DURATION
        self.meteors = []
        self.last_meteor_time = current_time

    def _start_fog_of_war(self, current_time: float):
        self.disaster_end = current_time + FOG_DURATION
        self.fog_active = True

    def _start_feeding_frenzy(self, current_time: float):
        self.disaster_end = current_time + FRENZY_DURATION
        self._spawn_frenzy_orbs()

    def _start_supernova(self, current_time: float):
        self.supernova_x = random.uniform(200, WORLD_WIDTH - 200)
        self.supernova_y = random.uniform(200, WORLD_HEIGHT - 200)
        self.supernova_triggered = True
        self.supernova_time = current_time
        self.supernova_pulses_fired = 1
        self._apply_supernova()
        total_duration = (SUPERNOVA_PULSE_COUNT - 1) * SUPERNOVA_PULSE_INTERVAL + SUPERNOVA_PULSE_EXPAND_TIME + 0.5
        self.disaster_end = current_time + total_duration

    def _start_earthquake(self, current_time: float):
        self.disaster_end = current_time + EARTHQUAKE_DURATION
        self.earthquake_progress = 0
        self.earthquake_old_walls = [
            {"id": w.id, "x": w.x, "y": w.y, "width": w.width, "height": w.height}
            for w in self.game.walls.values()
        ]
        self.earthquake_new_walls = self._generate_new_wall_positions()

    def _tick_disaster(self, current_time: float):
        tickers = {
            "black_hole": self._tick_black_hole,
            "meteor_shower": self._tick_meteor_shower,
            "earthquake": self._tick_earthquake,
            "supernova": self._tick_supernova,
        }
        ticker = tickers.get(self.active_disaster)
        if ticker:
            ticker(current_time)

    def _end_disaster(self, current_time: float):
        enders = {
            "black_hole": self._end_black_hole,
            "meteor_shower": self._end_meteor_shower,
            "fog_of_war": self._end_fog_of_war,
            "feeding_frenzy": self._end_feeding_frenzy,
            "supernova": self._end_supernova,
            "earthquake": self._end_earthquake,
        }
        ender = enders.get(self.active_disaster)
        if ender:
            ender()
        self.active_disaster = None
        self.next_disaster_time = current_time + random.uniform(DISASTER_MIN_INTERVAL, DISASTER_MAX_INTERVAL)

    def _end_black_hole(self):
        if self.black_hole:
            for _ in range(BLACK_HOLE_EXIT_ORB_COUNT):
                angle = random.uniform(0, math.pi * 2)
                dist = random.uniform(50, 300)
                ox = max(50, min(WORLD_WIDTH - 50, self.black_hole.x + math.cos(angle) * dist))
                oy = max(50, min(WORLD_HEIGHT - 50, self.black_hole.y + math.sin(angle) * dist))
                self.game.orb_counter += 1
                orb_id = f"orb_{self.game.orb_counter}"
                self.game.energy_orbs[orb_id] = EnergyOrb(id=orb_id, x=ox, y=oy)
            self.game._energy_orbs_cache = None
        self.black_hole = None

    def _end_meteor_shower(self):
        self.meteors = []

    def _end_fog_of_war(self):
        self.fog_active = False

    def _end_feeding_frenzy(self):
        for orb_id in self.frenzy_orb_ids:
            if orb_id in self.game.energy_orbs:
                del self.game.energy_orbs[orb_id]
        self.frenzy_orb_ids = []
        self.game._energy_orbs_cache = None

    def _end_supernova(self):
        self.supernova_triggered = False
        self.supernova_pulses_fired = 0

    def _end_earthquake(self):
        self._finalize_earthquake()
        self.earthquake_progress = 0

    # ── Black Hole ──

    def _tick_black_hole(self, current_time: float):
        bh = self.black_hole
        if not bh:
            return
        elapsed = current_time - self.disaster_start
        progress = min(1.0, elapsed / BLACK_HOLE_DURATION)
        bh.current_radius = BLACK_HOLE_INITIAL_RADIUS + (bh.max_radius - BLACK_HOLE_INITIAL_RADIUS) * progress

        self._apply_black_hole_pull(bh, progress, current_time)
        self._apply_black_hole_orb_pull(bh, progress)

    def _apply_black_hole_pull(self, bh, progress: float, current_time: float):
        """Pull players toward the black hole and kill those that reach the center."""
        for player in self.game.players.values():
            if not player.alive:
                continue
            dx = bh.x - player.x
            dy = bh.y - player.y
            dist_sq = max(1, dx * dx + dy * dy)
            dist = math.sqrt(dist_sq)

            if dist >= BLACK_HOLE_PULL_RANGE:
                continue

            mass_factor = (INITIAL_RADIUS / player.radius) ** BLACK_HOLE_MASS_FACTOR
            proximity_factor = 1.0 - (dist / BLACK_HOLE_PULL_RANGE)
            pull = BLACK_HOLE_PULL_STRENGTH * proximity_factor * mass_factor * progress
            player.x += (dx / dist) * pull
            player.y += (dy / dist) * pull

            if dist < bh.current_radius * BLACK_HOLE_KILL_RADIUS_FACTOR:
                if not player.check_invincible(current_time) and not player.has_shield(current_time):
                    player.alive = False
                    player.score = 0
                    self.game.add_kill("Black Hole", player.name)

    def _apply_black_hole_orb_pull(self, bh, progress: float):
        """Pull energy orbs toward the black hole and consume those that reach the center."""
        orb_moved = False
        for orb in self.game.energy_orbs.values():
            dx = bh.x - orb.x
            dy = bh.y - orb.y
            dist = math.sqrt(dx * dx + dy * dy)
            if 0 < dist < BLACK_HOLE_PULL_RANGE:
                pull = BLACK_HOLE_ORB_PULL_STRENGTH * (1.0 - dist / BLACK_HOLE_PULL_RANGE) * progress
                orb.x += (dx / dist) * pull
                orb.y += (dy / dist) * pull
                orb_moved = True

        kill_radius_sq = (bh.current_radius * BLACK_HOLE_KILL_RADIUS_FACTOR) ** 2
        orbs_consumed = [oid for oid, orb in self.game.energy_orbs.items()
                         if (orb.x - bh.x)**2 + (orb.y - bh.y)**2 < kill_radius_sq]
        for oid in orbs_consumed:
            del self.game.energy_orbs[oid]

        if orb_moved or orbs_consumed:
            self.game._energy_orbs_cache = None

    # ── Meteor Shower ──

    def _is_sheltered(self, player) -> bool:
        """Check if a player is sheltered by a wall (inside or very close)."""
        for wall in self.game.walls.values():
            if (wall.x <= player.x <= wall.x + wall.width and
                    wall.y <= player.y <= wall.y + wall.height):
                return True
            closest_x = max(wall.x, min(player.x, wall.x + wall.width))
            closest_y = max(wall.y, min(player.y, wall.y + wall.height))
            wall_dist = math.sqrt((player.x - closest_x)**2 + (player.y - closest_y)**2)
            if wall_dist < player.radius * 0.5:
                return True
        return False

    def _tick_meteor_shower(self, current_time: float):
        if current_time - self.last_meteor_time >= METEOR_INTERVAL:
            self.last_meteor_time = current_time
            for _ in range(METEOR_COUNT_PER_WAVE):
                mx = random.uniform(50, WORLD_WIDTH - 50)
                my = random.uniform(50, WORLD_HEIGHT - 50)
                self.meteors.append(Meteor(x=mx, y=my, impact_time=current_time))
                self._apply_meteor_damage(mx, my, current_time)

        self.meteors = [m for m in self.meteors if current_time - m.impact_time < METEOR_MARKER_DURATION]

    def _apply_meteor_damage(self, mx: float, my: float, current_time: float):
        """Damage players in blast radius of a meteor impact."""
        for player in self.game.players.values():
            if not player.alive or player.check_invincible(current_time):
                continue
            if player.has_shield(current_time):
                continue
            if self._is_sheltered(player):
                continue
            dx = player.x - mx
            dy = player.y - my
            if dx * dx + dy * dy < (METEOR_BLAST_RADIUS + player.radius) ** 2:
                player.radius = max(MIN_RADIUS, player.radius - METEOR_DAMAGE)
                if player.radius <= MIN_RADIUS:
                    player.alive = False
                    player.score = 0
                    self.game.add_kill("Meteor", player.name)

    # ── Feeding Frenzy ──

    def _spawn_frenzy_orbs(self):
        self.frenzy_orb_ids = []
        for _ in range(FRENZY_ORB_COUNT):
            self.game.orb_counter += 1
            orb_id = f"frenzy_{self.game.orb_counter}"
            x, y = self.game.find_safe_orb_position(ENERGY_ORB_RADIUS)
            hue = 0.25 + random.random() * 0.15
            r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
            color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
            self.game.energy_orbs[orb_id] = EnergyOrb(id=orb_id, x=x, y=y, color=color)
            self.frenzy_orb_ids.append(orb_id)
        self.game._energy_orbs_cache = None

    # ── Supernova ──

    def _tick_supernova(self, current_time: float):
        """Fire subsequent pulses at intervals."""
        if self.supernova_pulses_fired >= SUPERNOVA_PULSE_COUNT:
            return
        elapsed = current_time - self.supernova_time
        next_pulse_time = self.supernova_pulses_fired * SUPERNOVA_PULSE_INTERVAL
        if elapsed >= next_pulse_time:
            self.supernova_pulses_fired += 1
            self._apply_supernova()

    def _apply_supernova(self):
        loss_pct = random.uniform(SUPERNOVA_MASS_LOSS_MIN, SUPERNOVA_MASS_LOSS_MAX)
        for player in self.game.players.values():
            if not player.alive:
                continue
            dx = player.x - self.supernova_x
            dy = player.y - self.supernova_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < SUPERNOVA_RADIUS:
                player.radius = max(MIN_RADIUS, player.radius * (1 - loss_pct))
                player.score = max(0, int(player.score * (1 - loss_pct * 0.5)))

    # ── Earthquake ──

    def _generate_new_wall_positions(self) -> list:
        new_walls = []
        for old in self.earthquake_old_walls:
            # Randomize position but keep same dimensions
            new_x = random.uniform(100, WORLD_WIDTH - 100 - old["width"])
            new_y = random.uniform(100, WORLD_HEIGHT - 100 - old["height"])
            new_walls.append({
                "id": old["id"], "x": new_x, "y": new_y,
                "width": old["width"], "height": old["height"]
            })
        return new_walls

    def _tick_earthquake(self, current_time: float):
        elapsed = current_time - self.disaster_start
        self.earthquake_progress = min(1.0, elapsed / EARTHQUAKE_DURATION)
        t = self.earthquake_progress
        # Smooth easing
        t = t * t * (3 - 2 * t)

        for old, new in zip(self.earthquake_old_walls, self.earthquake_new_walls):
            wall = self.game.walls.get(old["id"])
            if wall:
                wall.x = old["x"] + (new["x"] - old["x"]) * t
                wall.y = old["y"] + (new["y"] - old["y"]) * t
        self.game._walls_cache = None

    def _finalize_earthquake(self):
        for new in self.earthquake_new_walls:
            wall = self.game.walls.get(new["id"])
            if wall:
                wall.x = new["x"]
                wall.y = new["y"]
        self.game._walls_cache = None

    def get_state(self, current_time: float) -> dict:
        """Return disaster state for broadcast to clients."""
        state = {
            "active": self.active_disaster,
            "warning": self.warning_type if self.warning_active else None,
            "warning_remaining": round(max(0, DISASTER_WARNING_TIME - (current_time - self.warning_start)), 1) if self.warning_active else 0,
        }
        if self.active_disaster:
            elapsed = current_time - self.disaster_start
            duration = self.disaster_end - self.disaster_start
            state["remaining"] = round(max(0, duration - elapsed), 1)
            state["progress"] = round(min(1.0, elapsed / duration), 2)

        if self.active_disaster == "black_hole" and self.black_hole:
            state["black_hole"] = self.black_hole.to_dict()
        elif self.active_disaster == "meteor_shower":
            state["meteors"] = [m.to_dict() for m in self.meteors]
        elif self.active_disaster == "fog_of_war":
            state["fog_radius"] = FOG_VISIBILITY_RADIUS
        elif self.active_disaster == "supernova":
            state["supernova"] = {
                "x": round(self.supernova_x, 1),
                "y": round(self.supernova_y, 1),
                "radius": SUPERNOVA_RADIUS,
                "time": round(current_time - self.supernova_time, 2),
                "pulse_count": SUPERNOVA_PULSE_COUNT,
                "pulse_interval": SUPERNOVA_PULSE_INTERVAL,
                "pulse_expand": SUPERNOVA_PULSE_EXPAND_TIME
            }
        elif self.active_disaster == "earthquake":
            state["earthquake_progress"] = round(self.earthquake_progress, 2)

        return state


class GameState:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.energy_orbs: Dict[str, EnergyOrb] = {}
        self.spike_orbs: Dict[str, SpikeOrb] = {}
        self.golden_orbs: Dict[str, GoldenOrb] = {}
        self.walls: Dict[str, Wall] = {}
        self.projectiles: Dict[str, Projectile] = {}
        self.powerup_orbs: Dict[str, PowerUpOrb] = {}
        self.connections: Dict[str, any] = {}
        self.orb_counter = 0
        self.spike_counter = 0
        self.golden_counter = 0
        self.wall_counter = 0
        self.projectile_counter = 0
        self.powerup_counter = 0
        self.powerup_respawn_timers: list = []  # [(respawn_time), ...]
        # Kill feed
        self.kill_feed: list = []  # [(timestamp, killer_name, victim_name), ...]
        # Leaderboard cache (updated every 1 second instead of every tick)
        self._cached_leaderboard: list = []
        self._leaderboard_update_time: float = 0
        self._leaderboard_cache_duration: float = 1.0  # seconds
        # Orb serialization caches (invalidated on collect/respawn)
        self._energy_orbs_cache: list = None
        self._spike_orbs_cache: list = None
        self._golden_orbs_cache: list = None
        self._powerup_orbs_cache: list = None
        self._walls_cache: list = None
        self.spawn_walls()
        self.spawn_energy_orbs(ENERGY_ORB_COUNT)
        self.spawn_spike_orbs(SPIKE_ORB_COUNT)
        self.spawn_golden_orbs(GOLDEN_ORB_COUNT)
        self.spawn_powerup_orbs(POWERUP_COUNT)
        self.disaster_manager = DisasterManager(self)

    def generate_color(self) -> str:
        """Generate a vibrant random color."""
        hue = random.random()
        saturation = 0.7 + random.random() * 0.3
        value = 0.8 + random.random() * 0.2
        r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    def find_safe_orb_position(self, radius: float = 10) -> tuple:
        """Find a random position not inside any wall."""
        for _ in range(50):
            x = random.uniform(50, WORLD_WIDTH - 50)
            y = random.uniform(50, WORLD_HEIGHT - 50)
            inside_wall = False
            for wall in self.walls.values():
                if (wall.x - radius < x < wall.x + wall.width + radius and
                    wall.y - radius < y < wall.y + wall.height + radius):
                    inside_wall = True
                    break
            if not inside_wall:
                return x, y
        return x, y  # fallback to last attempt

    def spawn_energy_orbs(self, count: int):
        """Spawn energy orbs at random positions."""
        for _ in range(count):
            self.orb_counter += 1
            orb_id = f"orb_{self.orb_counter}"
            # Random green-ish color
            hue = 0.25 + random.random() * 0.15  # Green range
            r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
            color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

            x, y = self.find_safe_orb_position(ENERGY_ORB_RADIUS)
            self.energy_orbs[orb_id] = EnergyOrb(
                id=orb_id,
                x=x,
                y=y,
                color=color
            )

    def spawn_spike_orbs(self, count: int):
        """Spawn evil spike orbs at random positions."""
        for _ in range(count):
            self.spike_counter += 1
            orb_id = f"spike_{self.spike_counter}"
            # Random red/pink color
            hue = random.uniform(0.95, 1.0) if random.random() > 0.5 else random.uniform(0.0, 0.05)
            r, g, b = colorsys.hsv_to_rgb(hue, 0.9, 0.9)
            color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

            x, y = self.find_safe_orb_position(SPIKE_ORB_RADIUS)
            self.spike_orbs[orb_id] = SpikeOrb(
                id=orb_id,
                x=x,
                y=y,
                color=color
            )

    def spawn_golden_orbs(self, count: int):
        """Spawn rare golden orbs worth extra points."""
        for _ in range(count):
            self.golden_counter += 1
            orb_id = f"golden_{self.golden_counter}"
            x, y = self.find_safe_orb_position(GOLDEN_ORB_RADIUS)
            self.golden_orbs[orb_id] = GoldenOrb(
                id=orb_id,
                x=x,
                y=y
            )

    def spawn_powerup_orbs(self, count: int):
        """Spawn mystery power-up orbs."""
        for _ in range(count):
            self.powerup_counter += 1
            orb_id = f"powerup_{self.powerup_counter}"
            x, y = self.find_safe_orb_position(POWERUP_RADIUS)
            self.powerup_orbs[orb_id] = PowerUpOrb(
                id=orb_id,
                x=x,
                y=y
            )
        self._powerup_orbs_cache = None

    def spawn_walls(self):
        """Spawn obstacle walls around the map."""
        wall_configs = [
            # Central cross
            {"x": WORLD_WIDTH // 2 - 150, "y": WORLD_HEIGHT // 2 - 25, "width": 300, "height": 50},
            {"x": WORLD_WIDTH // 2 - 25, "y": WORLD_HEIGHT // 2 - 150, "width": 50, "height": 300},
            # Corner L-shapes (4 corners, 2 walls each = 8 walls)
            {"x": 200, "y": 200, "width": 150, "height": 30},
            {"x": 200, "y": 200, "width": 30, "height": 150},
            {"x": WORLD_WIDTH - 350, "y": 200, "width": 150, "height": 30},
            {"x": WORLD_WIDTH - 230, "y": 200, "width": 30, "height": 150},
            {"x": 200, "y": WORLD_HEIGHT - 230, "width": 150, "height": 30},
            {"x": 200, "y": WORLD_HEIGHT - 350, "width": 30, "height": 150},
            {"x": WORLD_WIDTH - 350, "y": WORLD_HEIGHT - 230, "width": 150, "height": 30},
            {"x": WORLD_WIDTH - 230, "y": WORLD_HEIGHT - 350, "width": 30, "height": 150},
        ]
        # Fill remaining wall slots with random walls spread across the map
        remaining = WALL_COUNT - len(wall_configs)
        for _ in range(remaining):
            if random.random() < 0.5:
                w = random.randint(120, 300)
                h = random.randint(25, 50)
            else:
                w = random.randint(25, 50)
                h = random.randint(120, 300)
            x = random.uniform(300, WORLD_WIDTH - 300 - w)
            y = random.uniform(300, WORLD_HEIGHT - 300 - h)
            wall_configs.append({"x": x, "y": y, "width": w, "height": h})

        for i, cfg in enumerate(wall_configs):
            wall_id = f"wall_{i}"
            self.walls[wall_id] = Wall(
                id=wall_id,
                x=cfg["x"],
                y=cfg["y"],
                width=cfg["width"],
                height=cfg["height"]
            )

    def add_kill(self, killer_name: str, victim_name: str):
        """Add a kill to the feed."""
        self.kill_feed.append({
            "time": time.time(),
            "killer": killer_name,
            "victim": victim_name
        })
        # Keep only recent kills
        if len(self.kill_feed) > KILL_FEED_MAX * 2:
            self.kill_feed = self.kill_feed[-KILL_FEED_MAX:]

    def get_kill_feed(self) -> list:
        """Get recent kills for display."""
        current_time = time.time()
        # Filter to recent kills only
        recent = [k for k in self.kill_feed if current_time - k["time"] < KILL_FEED_DURATION]
        return recent[-KILL_FEED_MAX:]

    def activate_boost(self, player_id: str):
        """Activate boost for a player."""
        if player_id not in self.players:
            return
        player = self.players[player_id]
        current_time = time.time()

        # Check cooldown and minimum size
        if current_time < player.boost_cooldown_until:
            return
        if player.radius <= MIN_RADIUS + BOOST_MASS_COST:
            return

        # Activate boost
        player.boost_active_until = current_time + BOOST_DURATION
        player.boost_cooldown_until = current_time + BOOST_COOLDOWN
        player.radius -= BOOST_MASS_COST

    def shoot(self, player_id: str, target_x: float, target_y: float):
        """Fire a projectile from a player toward a target position."""
        if player_id not in self.players:
            return
        player = self.players[player_id]
        current_time = time.time()

        if not player.alive:
            return
        if player.radius < PROJECTILE_MIN_RADIUS:
            return

        has_rapid_fire = player.active_powerup == "rapid_fire" and current_time < player.powerup_until

        if not has_rapid_fire and current_time < player.shoot_cooldown_until:
            return

        # Calculate direction
        dx = target_x - player.x
        dy = target_y - player.y
        distance = math.sqrt(dx * dx + dy * dy)
        if distance < 1:
            return

        # Normalize direction
        ndx = dx / distance
        ndy = dy / distance

        # Cost mass (free with rapid fire)
        if not has_rapid_fire:
            player.radius -= PROJECTILE_COST
            player.shoot_cooldown_until = current_time + PROJECTILE_COOLDOWN

        # Spawn projectile at player's edge
        self.projectile_counter += 1
        proj_id = f"proj_{self.projectile_counter}"
        self.projectiles[proj_id] = Projectile(
            id=proj_id,
            owner_id=player_id,
            x=player.x + ndx * (player.radius + PROJECTILE_RADIUS + 2),
            y=player.y + ndy * (player.radius + PROJECTILE_RADIUS + 2),
            dx=ndx,
            dy=ndy,
            color=player.color,
            created_at=current_time,
            lifetime=PROJECTILE_RAPID_FIRE_LIFETIME if has_rapid_fire else PROJECTILE_LIFETIME
        )

    def add_player(self, player_id: str, name: str, websocket) -> Player:
        """Add a new player to the game."""
        # Spawn at random position away from walls and other players
        x, y = self.find_safe_spawn()

        player = Player(
            id=player_id,
            name=sanitize_name(name),
            x=x,
            y=y,
            radius=INITIAL_RADIUS,
            color=self.generate_color(),
            target_x=x,
            target_y=y,
            invincible_until=time.time() + RESPAWN_INVINCIBILITY
        )
        self.players[player_id] = player
        self.connections[player_id] = websocket
        return player

    def find_safe_spawn(self) -> tuple:
        """Find a spawn point not inside a wall."""
        for _ in range(50):  # Max attempts
            x = random.uniform(100, WORLD_WIDTH - 100)
            y = random.uniform(100, WORLD_HEIGHT - 100)
            # Check if inside any wall
            safe = True
            for wall in self.walls.values():
                if (wall.x - 50 < x < wall.x + wall.width + 50 and
                    wall.y - 50 < y < wall.y + wall.height + 50):
                    safe = False
                    break
            if safe:
                return x, y
        # Fallback
        return WORLD_WIDTH // 2, WORLD_HEIGHT // 2

    def remove_player(self, player_id: str):
        """Remove a player from the game."""
        if player_id in self.players:
            del self.players[player_id]
        if player_id in self.connections:
            del self.connections[player_id]

    def update_player_target(self, player_id: str, target_x: float, target_y: float):
        """Update where a player is moving towards."""
        if player_id in self.players:
            self.players[player_id].target_x = target_x
            self.players[player_id].target_y = target_y

    def respawn_player(self, player_id: str):
        """Respawn a dead player."""
        if player_id in self.players:
            player = self.players[player_id]
            x, y = self.find_safe_spawn()
            player.x = x
            player.y = y
            player.radius = INITIAL_RADIUS
            player.target_x = player.x
            player.target_y = player.y
            player.alive = True
            player.invincible_until = time.time() + RESPAWN_INVINCIBILITY
            player.boost_cooldown_until = 0
            player.boost_active_until = 0
            player.shoot_cooldown_until = 0
            player.critical_mass_start = 0
            player.active_powerup = ""
            player.powerup_until = 0

    def _move_players(self, current_time: float):
        """Move players towards targets, handle bounds and wall collisions, apply shrink."""
        for player in self.players.values():
            if not player.alive:
                continue

            prev_x, prev_y = player.x, player.y

            dx = player.target_x - player.x
            dy = player.target_y - player.y
            dist_sq = dx * dx + dy * dy

            if dist_sq > MOVE_THRESHOLD_SQ:
                distance = math.sqrt(dist_sq)
                speed = player.get_speed(current_time)
                player.x += (dx / distance) * speed
                player.y += (dy / distance) * speed

            # Keep player in bounds
            player.x = max(player.radius, min(WORLD_WIDTH - player.radius, player.x))
            player.y = max(player.radius, min(WORLD_HEIGHT - player.radius, player.y))

            # Wall collisions - push player out of walls (phantom passes through)
            self._resolve_wall_collisions(player, prev_x, prev_y, current_time)

            # Slowly shrink (but not below minimum)
            if player.radius > MIN_RADIUS + 5:
                player.radius = max(MIN_RADIUS, player.radius - SHRINK_RATE)

    def _resolve_wall_collisions(self, player, prev_x: float, prev_y: float, current_time: float):
        """Push a player out of any overlapping walls."""
        is_phantom = player.active_powerup == "phantom" and current_time < player.powerup_until
        wall_iters = 0 if is_phantom else WALL_COLLISION_ITERATIONS
        for _iteration in range(wall_iters):
            for wall in self.walls.values():
                closest_x = max(wall.x, min(player.x, wall.x + wall.width))
                closest_y = max(wall.y, min(player.y, wall.y + wall.height))
                dist_x = player.x - closest_x
                dist_y = player.y - closest_y
                dist = math.sqrt(dist_x * dist_x + dist_y * dist_y)

                if dist < player.radius:
                    if dist > 0:
                        overlap = player.radius - dist + 1
                        player.x += (dist_x / dist) * overlap
                        player.y += (dist_y / dist) * overlap
                    else:
                        self._push_player_from_wall(player, wall, prev_x, prev_y)

    def _push_player_from_wall(self, player, wall, prev_x: float, prev_y: float):
        """Push a player whose center is inside a wall back to safety."""
        push_dx = prev_x - player.x
        push_dy = prev_y - player.y
        push_dist = math.sqrt(push_dx * push_dx + push_dy * push_dy)
        if push_dist > 0:
            player.x = prev_x
            player.y = prev_y
        else:
            # Fallback: push to nearest edge
            push_left = player.x - wall.x
            push_right = (wall.x + wall.width) - player.x
            push_up = player.y - wall.y
            push_down = (wall.y + wall.height) - player.y
            min_push = min(push_left, push_right, push_up, push_down)
            if min_push == push_left:
                player.x = wall.x - player.radius - 1
            elif min_push == push_right:
                player.x = wall.x + wall.width + player.radius + 1
            elif min_push == push_up:
                player.y = wall.y - player.radius - 1
            else:
                player.y = wall.y + wall.height + player.radius + 1

    def _check_orb_collisions(self, current_time: float):
        """Handle all orb pickup collisions (energy, spike, golden, power-up) and respawns."""
        self._collect_energy_orbs()
        self._collect_spike_orbs(current_time)
        self._collect_golden_orbs()
        self._collect_powerup_orbs(current_time)
        self._process_powerup_respawns(current_time)

    def _collect_energy_orbs(self):
        orbs_to_remove = []
        for orb_id, orb in self.energy_orbs.items():
            for player in self.players.values():
                if not player.alive:
                    continue
                dx = player.x - orb.x
                dy = player.y - orb.y
                combined = player.radius + orb.radius
                if dx * dx + dy * dy < combined * combined:
                    player.radius = min(MAX_RADIUS, player.radius + ENERGY_ORB_VALUE)
                    player.score += 10
                    orbs_to_remove.append(orb_id)
                    break
        if orbs_to_remove:
            for orb_id in orbs_to_remove:
                del self.energy_orbs[orb_id]
            self.spawn_energy_orbs(len(orbs_to_remove))
            self._energy_orbs_cache = None

    def _collect_spike_orbs(self, current_time: float):
        spikes_to_remove = []
        for orb_id, orb in self.spike_orbs.items():
            for player in self.players.values():
                if not player.alive:
                    continue
                if player.has_protection(current_time):
                    continue
                dx = player.x - orb.x
                dy = player.y - orb.y
                combined = player.radius + orb.radius
                if dx * dx + dy * dy < combined * combined:
                    player.radius = max(MIN_RADIUS, player.radius * 0.75)
                    spikes_to_remove.append(orb_id)
                    break
        if spikes_to_remove:
            for orb_id in spikes_to_remove:
                del self.spike_orbs[orb_id]
            self.spawn_spike_orbs(len(spikes_to_remove))
            self._spike_orbs_cache = None

    def _collect_golden_orbs(self):
        golden_to_remove = []
        for orb_id, orb in self.golden_orbs.items():
            for player in self.players.values():
                if not player.alive:
                    continue
                dx = player.x - orb.x
                dy = player.y - orb.y
                combined = player.radius + orb.radius
                if dx * dx + dy * dy < combined * combined:
                    player.radius = min(MAX_RADIUS, player.radius + GOLDEN_ORB_VALUE)
                    player.score += 50
                    golden_to_remove.append(orb_id)
                    break
        if golden_to_remove:
            for orb_id in golden_to_remove:
                del self.golden_orbs[orb_id]
            self.spawn_golden_orbs(len(golden_to_remove))
            self._golden_orbs_cache = None

    def _collect_powerup_orbs(self, current_time: float):
        powerups_to_remove = []
        for orb_id, orb in self.powerup_orbs.items():
            for player in self.players.values():
                if not player.alive:
                    continue
                dx = player.x - orb.x
                dy = player.y - orb.y
                combined = player.radius + orb.radius
                if dx * dx + dy * dy < combined * combined:
                    powerup_type = random.choice(POWERUP_TYPES)
                    player.active_powerup = powerup_type
                    player.powerup_until = current_time + POWERUP_DURATIONS[powerup_type]
                    powerups_to_remove.append(orb_id)
                    break
        if powerups_to_remove:
            for orb_id in powerups_to_remove:
                del self.powerup_orbs[orb_id]
            self._powerup_orbs_cache = None
            for _ in powerups_to_remove:
                self.powerup_respawn_timers.append(current_time + POWERUP_RESPAWN_DELAY)

    def _process_powerup_respawns(self, current_time: float):
        if self.powerup_respawn_timers:
            respawns = [t for t in self.powerup_respawn_timers if current_time >= t]
            if respawns:
                self.powerup_respawn_timers = [t for t in self.powerup_respawn_timers if current_time < t]
                self.spawn_powerup_orbs(len(respawns))

    def _consume_player(self, consumer, victim):
        """One player consumes another."""
        consumer.radius = min(MAX_RADIUS, consumer.radius + victim.radius * 0.5)
        consumer.score += KILL_BASE_SCORE + int(victim.score * KILL_SCORE_RATIO)
        victim.alive = False
        victim.score = 0
        self.add_kill(consumer.name, victim.name)

    def _check_player_collisions(self, current_time: float):
        """Handle player vs player consume and bounce collisions."""
        players_list = list(self.players.values())
        for i, player1 in enumerate(players_list):
            if not player1.alive:
                continue
            for player2 in players_list[i+1:]:
                if not player2.alive:
                    continue

                if player1.has_protection(current_time) or player2.has_protection(current_time):
                    continue

                dx = player1.x - player2.x
                dy = player1.y - player2.y
                combined = player1.radius + player2.radius
                dist_sq = dx * dx + dy * dy

                if dist_sq < combined * combined:
                    distance = math.sqrt(dist_sq)
                    if player1.radius > player2.radius * CONSUME_RATIO:
                        self._consume_player(player1, player2)
                    elif player2.radius > player1.radius * CONSUME_RATIO:
                        self._consume_player(player2, player1)
                    elif distance > 0:
                        overlap = (player1.radius + player2.radius - distance) / 2
                        player1.x += (dx / distance) * overlap
                        player1.y += (dy / distance) * overlap
                        player2.x -= (dx / distance) * overlap
                        player2.y -= (dy / distance) * overlap

    def _update_projectiles(self, current_time: float):
        """Move projectiles and handle wall/player hit detection."""
        projectiles_to_remove = []
        for proj_id, proj in self.projectiles.items():
            proj.x += proj.dx * PROJECTILE_SPEED
            proj.y += proj.dy * PROJECTILE_SPEED

            if current_time - proj.created_at > proj.lifetime:
                projectiles_to_remove.append(proj_id)
                continue
            if proj.x < 0 or proj.x > WORLD_WIDTH or proj.y < 0 or proj.y > WORLD_HEIGHT:
                projectiles_to_remove.append(proj_id)
                continue

            if self._projectile_hit_wall(proj):
                projectiles_to_remove.append(proj_id)
                continue

            if self._projectile_hit_player(proj, current_time):
                projectiles_to_remove.append(proj_id)

        for proj_id in projectiles_to_remove:
            if proj_id in self.projectiles:
                del self.projectiles[proj_id]

    def _projectile_hit_wall(self, proj) -> bool:
        for wall in self.walls.values():
            closest_x = max(wall.x, min(proj.x, wall.x + wall.width))
            closest_y = max(wall.y, min(proj.y, wall.y + wall.height))
            dist_x = proj.x - closest_x
            dist_y = proj.y - closest_y
            dist = math.sqrt(dist_x * dist_x + dist_y * dist_y)
            if dist < proj.radius:
                return True
        return False

    def _projectile_hit_player(self, proj, current_time: float) -> bool:
        for player in self.players.values():
            if not player.alive or player.id == proj.owner_id or player.has_protection(current_time):
                continue
            dx = player.x - proj.x
            dy = player.y - proj.y
            combined = player.radius + proj.radius
            if dx * dx + dy * dy < combined * combined:
                player.radius = max(MIN_RADIUS, player.radius - PROJECTILE_DAMAGE)
                if player.radius <= MIN_RADIUS:
                    shooter = self.players.get(proj.owner_id)
                    if shooter and shooter.alive and shooter.radius > player.radius * CONSUME_RATIO:
                        player.alive = False
                        shooter.score += KILL_BASE_SCORE + int(player.score * KILL_SCORE_RATIO)
                        player.score = 0
                        self.add_kill(shooter.name, player.name)
                return True
        return False

    def _update_critical_mass(self, current_time: float):
        """Handle critical mass timer and explosion."""
        for player in self.players.values():
            if not player.alive:
                continue
            if player.radius >= CRITICAL_MASS_THRESHOLD:
                if player.critical_mass_start == 0:
                    player.critical_mass_start = current_time
                elif current_time - player.critical_mass_start >= CRITICAL_MASS_TIMER:
                    player.radius = INITIAL_RADIUS
                    player.score = max(0, player.score // 2)
                    player.critical_mass_start = 0
                    self.add_kill(player.name, f"{player.name} (exploded)")
            else:
                player.critical_mass_start = 0

    def _update_powerups(self, current_time: float):
        """Handle power-up expiry and magnet pull effect."""
        for player in self.players.values():
            if player.active_powerup and current_time >= player.powerup_until:
                player.active_powerup = ""
                player.powerup_until = 0

        magnet_moved = False
        for player in self.players.values():
            if not player.alive or player.active_powerup != "magnet" or current_time >= player.powerup_until:
                continue
            for orb in self.energy_orbs.values():
                dx = player.x - orb.x
                dy = player.y - orb.y
                dist_sq = dx * dx + dy * dy
                if dist_sq < MAGNET_RANGE * MAGNET_RANGE and dist_sq > 1:
                    dist = math.sqrt(dist_sq)
                    orb.x += (dx / dist) * MAGNET_STRENGTH
                    orb.y += (dy / dist) * MAGNET_STRENGTH
                    magnet_moved = True
        if magnet_moved:
            self._energy_orbs_cache = None

    def tick(self):
        """Update game state for one tick."""
        current_time = time.time()
        self._move_players(current_time)
        self._check_orb_collisions(current_time)
        self._check_player_collisions(current_time)
        self._update_projectiles(current_time)
        self._update_critical_mass(current_time)
        self._update_powerups(current_time)
        self.disaster_manager.tick(current_time)

    def get_static_data(self) -> dict:
        """Get static data that only needs to be sent once (on welcome)."""
        if self._walls_cache is None:
            self._walls_cache = [w.to_dict() for w in self.walls.values()]
        return {
            "walls": self._walls_cache,
            "world": {"width": WORLD_WIDTH, "height": WORLD_HEIGHT}
        }

    def build_shared_state(self, current_time: float) -> dict:
        """Build the shared portion of game state (called once per tick)."""
        # Use cached orb lists when available
        if self._energy_orbs_cache is None:
            self._energy_orbs_cache = [o.to_dict() for o in self.energy_orbs.values()]
        if self._spike_orbs_cache is None:
            self._spike_orbs_cache = [o.to_dict() for o in self.spike_orbs.values()]
        if self._golden_orbs_cache is None:
            self._golden_orbs_cache = [o.to_dict() for o in self.golden_orbs.values()]
        if self._powerup_orbs_cache is None:
            self._powerup_orbs_cache = [o.to_dict() for o in self.powerup_orbs.values()]

        return {
            "type": "state",
            "players": [p.to_dict(current_time) for p in self.players.values()],
            "energy_orbs": self._energy_orbs_cache,
            "spike_orbs": self._spike_orbs_cache,
            "golden_orbs": self._golden_orbs_cache,
            "powerup_orbs": self._powerup_orbs_cache,
            "projectiles": [p.to_dict() for p in self.projectiles.values()],
            "kill_feed": self.get_kill_feed(),
            "leaderboard": self.get_leaderboard(),
            "disaster": self.disaster_manager.get_state(current_time)
        }

    def get_leaderboard(self) -> list:
        """Get top 10 players by score (cached for performance)."""
        current_time = time.time()
        if current_time - self._leaderboard_update_time >= self._leaderboard_cache_duration:
            sorted_players = sorted(
                [p for p in self.players.values() if p.alive],
                key=lambda p: p.score,
                reverse=True
            )[:10]
            self._cached_leaderboard = [{"name": p.name, "score": p.score} for p in sorted_players]
            self._leaderboard_update_time = current_time
        return self._cached_leaderboard


# Global game state
game = GameState()


SEND_TIMEOUT = 0.5  # seconds - drop slow clients to prevent buffer buildup

# Rate limiting / connection cap
MAX_CONNECTIONS = 50
RATE_LIMIT_WINDOW = 1.0   # seconds
RATE_LIMIT_MAX_MSGS = 120  # max messages per window (30fps move + up to 60 shoots during rapid_fire)
active_connections = 0


async def broadcast_state():
    """Broadcast game state to all connected players."""
    while True:
        game.tick()
        current_time = time.time()

        # Build shared state once and serialize to JSON once
        shared_state = game.build_shared_state(current_time)
        # Serialize without 'you' - we'll splice it in per player
        shared_json = json.dumps(shared_state)
        # Remove trailing '}' so we can append ',"you":...}'
        shared_json_prefix = shared_json[:-1] + ',"you":'

        # Send state to each player (only serialize their 'you' portion)
        disconnected = []
        for player_id, websocket in list(game.connections.items()):
            player = game.players.get(player_id)
            if not player:
                continue
            try:
                you_json = json.dumps(player.to_dict(current_time))
                message = shared_json_prefix + you_json + '}'
                await asyncio.wait_for(
                    websocket.send(message),
                    timeout=SEND_TIMEOUT
                )
            except asyncio.TimeoutError:
                print(f"Player {player_id} send timeout - dropping connection")
                disconnected.append(player_id)
            except ConnectionClosed:
                disconnected.append(player_id)
            except Exception as e:
                print(f"Error sending to {player_id}: {e}")
                disconnected.append(player_id)

        # Clean up disconnected players
        for player_id in disconnected:
            game.remove_player(player_id)
            print(f"Player {player_id} disconnected")

        await asyncio.sleep(TICK_RATE)


async def handle_client(websocket):
    """Handle a single client connection."""
    global active_connections
    player_id = None

    # Enforce connection cap
    if active_connections >= MAX_CONNECTIONS:
        await websocket.close(1013, "Server full")
        return

    active_connections += 1
    # Rate limiting state for this client
    msg_count = 0
    window_start = time.time()

    try:
        # Wait for join message
        message = await websocket.recv()
        data = json.loads(message)

        if data.get("type") == "join":
            player_id = f"player_{id(websocket)}"
            name = sanitize_name(str(data.get("name", "Anonymous")))
            player = game.add_player(player_id, name, websocket)

            # Send welcome message with static data
            welcome_data = {
                "type": "welcome",
                "player_id": player_id,
                "player": player.to_dict(time.time())
            }
            welcome_data.update(game.get_static_data())
            await websocket.send(json.dumps(welcome_data))

            print(f"Player {name} ({player_id}) joined!")

            # Handle messages from this client
            async for message in websocket:
                # Rate limiting
                now = time.time()
                if now - window_start >= RATE_LIMIT_WINDOW:
                    msg_count = 0
                    window_start = now
                msg_count += 1
                if msg_count > RATE_LIMIT_MAX_MSGS:
                    continue  # Silently drop excess messages

                try:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == "move":
                        game.update_player_target(
                            player_id,
                            safe_float(data.get("x", 0)),
                            safe_float(data.get("y", 0))
                        )

                    elif msg_type == "boost":
                        game.activate_boost(player_id)

                    elif msg_type == "shoot":
                        game.shoot(
                            player_id,
                            safe_float(data.get("x", 0)),
                            safe_float(data.get("y", 0))
                        )

                    elif msg_type == "respawn":
                        game.respawn_player(player_id)

                except (json.JSONDecodeError, TypeError, ValueError, KeyError):
                    pass  # Silently drop malformed messages

    except ConnectionClosed:
        pass
    finally:
        active_connections -= 1
        if player_id:
            game.remove_player(player_id)
            print(f"Player {player_id} left")


def get_local_ip():
    """Get the local IP address for LAN play."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


ALLOWED_HTTP_FILES = {"/", "/index.html"}


class SafeHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that only serves the game client file."""

    def do_GET(self):
        # Normalize path and only allow index.html
        path = self.path.split("?")[0].split("#")[0]  # strip query/fragment
        if path not in ALLOWED_HTTP_FILES:
            self.send_error(404, "Not Found")
            return
        # Always serve index.html
        self.path = "/index.html"
        super().do_GET()

    def do_HEAD(self):
        path = self.path.split("?")[0].split("#")[0]
        if path not in ALLOWED_HTTP_FILES:
            self.send_error(404, "Not Found")
            return
        self.path = "/index.html"
        super().do_HEAD()

    def log_message(self, format, *args):
        pass  # Suppress routine request logs

    def log_error(self, format, *args):
        # Keep error logging for visibility into abuse attempts
        print(f"[HTTP] {self.client_address[0]} - {format % args}")


def start_http_server(port=8080):
    """Start a threaded HTTP server to serve the game files."""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Use ThreadingHTTPServer to handle multiple connections
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", port), SafeHTTPHandler)
    httpd.serve_forever()


async def main():
    """Start the game server."""
    local_ip = get_local_ip()

    # Start HTTP server in a background thread
    http_thread = threading.Thread(target=start_http_server, args=(8080,), daemon=True)
    http_thread.start()

    print("=" * 50)
    print("  ORB ARENA - Multiplayer Game Server")
    print("=" * 50)
    print(f"  World Size: {WORLD_WIDTH}x{WORLD_HEIGHT}")
    print(f"  Tick Rate: {int(1/TICK_RATE)} FPS")
    print("=" * 50)
    print(f"\n  PLAY THE GAME:")
    print(f"    Local:  http://localhost:8080")
    print(f"    LAN:    http://{local_ip}:8080")
    print("=" * 50)
    print(f"\n  Share this URL with friends: http://{local_ip}:8080")
    print("\n  Press Ctrl+C to stop the server\n")

    # Start the game loop
    asyncio.create_task(broadcast_state())

    # Allowed origins for WebSocket connections (prevents cross-site hijacking)
    # None = allow all origins (for LAN play without domain setup)
    # Set ALLOWED_ORIGINS env var to restrict in production, e.g. "https://game.yourdomain.com"
    allowed_origins_env = os.environ.get("ALLOWED_ORIGINS")
    if allowed_origins_env:
        ws_origins = [o.strip() for o in allowed_origins_env.split(",")]
        print(f"  WebSocket origins restricted to: {ws_origins}")
    else:
        ws_origins = None  # Allow all for LAN play
        print("  WebSocket origins: unrestricted (set ALLOWED_ORIGINS to restrict)")

    # Start WebSocket server (0.0.0.0 allows LAN connections)
    # Enable permessage-deflate compression to reduce bandwidth
    async with websockets.serve(
        handle_client, "0.0.0.0", 8765,
        compression="deflate",
        origins=ws_origins,
        max_size=1024,  # Max message size: 1KB (game messages are tiny)
    ):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
