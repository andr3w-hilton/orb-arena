"""
Orb Arena - Disaster Manager
Handles scheduling, ticking, and cleanup of all natural disaster events.
"""

from __future__ import annotations

import colorsys
import math
import random
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game import GameState

from constants import (
    DISASTER_TYPES, DISASTER_WARNING_TIME, DISASTER_MIN_PLAYERS,
    DISASTER_SETTLE_TIME, DISASTER_FIRST_MIN, DISASTER_FIRST_MAX,
    DISASTER_MIN_INTERVAL, DISASTER_MAX_INTERVAL,
    BLACK_HOLE_DURATION, BLACK_HOLE_MAX_RADIUS, BLACK_HOLE_PULL_RANGE,
    BLACK_HOLE_PULL_STRENGTH, BLACK_HOLE_MASS_FACTOR, BLACK_HOLE_INITIAL_RADIUS,
    BLACK_HOLE_KILL_RADIUS_FACTOR, BLACK_HOLE_ORB_PULL_STRENGTH, BLACK_HOLE_EXIT_ORB_COUNT,
    METEOR_SHOWER_DURATION, METEOR_INTERVAL, METEOR_DAMAGE, METEOR_BLAST_RADIUS,
    METEOR_COUNT_PER_WAVE, METEOR_MARKER_DURATION,
    FOG_DURATION, FOG_VISIBILITY_RADIUS,
    FRENZY_DURATION, FRENZY_ORB_COUNT,
    SUPERNOVA_RADIUS, SUPERNOVA_PULSE_COUNT, SUPERNOVA_PULSE_INTERVAL,
    SUPERNOVA_PULSE_EXPAND_TIME, SUPERNOVA_MASS_LOSS_MIN, SUPERNOVA_MASS_LOSS_MAX,
    EARTHQUAKE_DURATION,
    INITIAL_RADIUS, MIN_RADIUS, WORLD_WIDTH, WORLD_HEIGHT,
    ENERGY_ORB_RADIUS,
)
from entities import BlackHole, EnergyOrb, Meteor


class DisasterManager:
    """Manages natural disaster scheduling and execution."""

    def __init__(self, game: "GameState"):
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
        # Test cycle state
        self._test_queue: list = []  # remaining disaster types to test
        self._test_running: bool = False  # True while last disaster is still active
        self._test_gap: float = 3.0  # seconds between test disasters
        self._test_next_time: float = 0

    def _player_count(self) -> int:
        return len(self.game.players)

    def start_test_cycle(self, current_time: float):
        """Start a test cycle that runs through all disasters in sequence."""
        # End any active disaster first
        if self.active_disaster:
            self._end_disaster(current_time)
        self.warning_active = False
        self.warning_type = ""
        self._test_queue = list(DISASTER_TYPES)
        self._test_running = True
        self._test_next_time = current_time + 1.0  # 1s before first disaster
        print(f"[TEST] Disaster test cycle started: {self._test_queue}")

    def tick(self, current_time: float):
        """Called every game tick."""
        # Test cycle override
        if self._test_queue or self._test_running:
            if self.active_disaster:
                if current_time >= self.disaster_end:
                    self._end_disaster(current_time)
                    self._test_next_time = current_time + self._test_gap
                    if not self._test_queue:
                        self._test_running = False
                        print("[TEST] Disaster test cycle complete")
                else:
                    self._tick_disaster(current_time)
                return
            if self.warning_active:
                if current_time - self.warning_start >= DISASTER_WARNING_TIME:
                    self._start_disaster(self.warning_type, current_time)
                    self.warning_active = False
                return
            if self._test_queue and current_time >= self._test_next_time:
                dtype = self._test_queue.pop(0)
                self._test_running = True
                self.warning_type = dtype
                self.warning_active = True
                self.warning_start = current_time
                print(f"[TEST] Next disaster: {dtype} ({len(self._test_queue)} remaining)")
            return

        player_count = self._player_count()

        # Lobby readiness / timer management
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
            # Schedule first disaster after settle time + shorter first interval
            self.next_disaster_time = (
                current_time + DISASTER_SETTLE_TIME
                + random.uniform(DISASTER_FIRST_MIN, DISASTER_FIRST_MAX)
            )
            return

        # Still in settle period — don't trigger yet
        if current_time - self.lobby_ready_since < DISASTER_SETTLE_TIME:
            return

        # Warning phase
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

        # Active disaster tick
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

    # Black Hole

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
            proximity_factor = (1.0 - (dist / BLACK_HOLE_PULL_RANGE)) ** 0.5  # sqrt curve — strong pull much further out
            ramp = 0.3 + 0.7 * progress  # starts at 30% strength, not zero
            pull = BLACK_HOLE_PULL_STRENGTH * proximity_factor * mass_factor * ramp

            # Boosting reduces pull to 30% — costs mass but lets you claw out
            if current_time < player.boost_active_until:
                pull *= 0.3

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

    # Meteor Shower

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

    # Feeding Frenzy

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

    # Supernova

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
        base_loss = random.uniform(SUPERNOVA_MASS_LOSS_MIN, SUPERNOVA_MASS_LOSS_MAX)
        for player in self.game.players.values():
            if not player.alive:
                continue
            dx = player.x - self.supernova_x
            dy = player.y - self.supernova_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < SUPERNOVA_RADIUS:
                # Closer to epicentre = up to 2x damage
                proximity = 1.0 + (1.0 - dist / SUPERNOVA_RADIUS)
                loss_pct = base_loss * proximity
                player.radius = player.radius * (1 - loss_pct)
                player.score = max(0, int(player.score * (1 - loss_pct * 0.5)))
                # Kill if radius drops to minimum
                if player.radius <= MIN_RADIUS:
                    player.radius = MIN_RADIUS
                    player.alive = False
                    player.score = 0
                    self.game.add_kill("Supernova", player.name)

    # Earthquake

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
        self.game._walls_dirty = True

    def _finalize_earthquake(self):
        for new in self.earthquake_new_walls:
            wall = self.game.walls.get(new["id"])
            if wall:
                wall.x = new["x"]
                wall.y = new["y"]
        self.game._walls_cache = None
        self.game._walls_dirty = True
        self.game.relocate_trapped_orbs()

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
