"""
Orb Arena - GameState
Core multiplayer game state, tick pipeline, and all game logic.
"""

import colorsys
import math
import random
import time
from typing import Dict

from constants import (
    WORLD_WIDTH, WORLD_HEIGHT, INITIAL_RADIUS, MAX_RADIUS, MIN_RADIUS,
    ENERGY_ORB_COUNT, ENERGY_ORB_RADIUS, ENERGY_ORB_VALUE,
    SPIKE_ORB_COUNT, SPIKE_ORB_RADIUS,
    GOLDEN_ORB_COUNT, GOLDEN_ORB_RADIUS, GOLDEN_ORB_VALUE,
    POWERUP_COUNT, POWERUP_RADIUS, POWERUP_TYPES, POWERUP_DURATIONS, POWERUP_RESPAWN_DELAY,
    HOMING_MISSILES_AMMO, HOMING_MISSILE_LIFETIME, HOMING_MISSILE_SPEED,
    HOMING_MISSILE_INITIAL_SPEED_RATIO, HOMING_MISSILE_RAMP_TIME,
    HOMING_TRACKING_STRENGTH, HOMING_REACQUIRE_RANGE,
    HOMING_MISSILE_DAMAGE, PROJECTILE_DAMAGE,
    PROJECTILE_SPEED, PROJECTILE_RADIUS, PROJECTILE_LIFETIME, PROJECTILE_RAPID_FIRE_LIFETIME,
    PROJECTILE_COST, PROJECTILE_COOLDOWN, PROJECTILE_MIN_RADIUS,
    BOOST_DURATION, BOOST_COOLDOWN, BOOST_MASS_COST,
    WORMHOLE_SPEED_BONUS, WORMHOLE_TRAVEL_DIST, WORMHOLE_LIFETIME,
    WORMHOLE_DAMAGE, WORMHOLE_RADIUS, WORMHOLE_MIN_EXIT_DIST,
    MAGNET_RANGE, MAGNET_STRENGTH,
    TRAIL_SEGMENT_LIFETIME, TRAIL_SEGMENT_RADIUS, TRAIL_SEGMENT_INTERVAL, TRAIL_DAMAGE,
    MINE_PICKUP_COUNT, MINE_PICKUP_RESPAWN_DELAY, MINE_MAX_COUNT, MINE_ARM_DELAY,
    MINE_BLAST_RADIUS, MINE_DAMAGE, MINE_PROXIMITY_TRIGGER,
    WALL_COUNT, WALL_COLLISION_ITERATIONS, MOVE_THRESHOLD_SQ,
    CRITICAL_MASS_THRESHOLD, CRITICAL_MASS_TIMER,
    KILL_FEED_MAX, KILL_FEED_DURATION,
    KILL_BASE_SCORE, KILL_SCORE_RATIO,
    CONSUME_RATIO, SHRINK_RATE, RESPAWN_INVINCIBILITY,
)
from entities import (
    Player, Spectator, EnergyOrb, SpikeOrb, GoldenOrb, PowerUpOrb,
    Projectile, HomingMissile, WormholePortal, Mine, MinePickup, Wall,
)
from utils import sanitize_name
from scores import record_alltime_score
from disasters import DisasterManager


class GameState:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.spectators: Dict[str, Spectator] = {}
        self.energy_orbs: Dict[str, EnergyOrb] = {}
        self.spike_orbs: Dict[str, SpikeOrb] = {}
        self.golden_orbs: Dict[str, GoldenOrb] = {}
        self.walls: Dict[str, Wall] = {}
        self.projectiles: Dict[str, Projectile] = {}
        self.powerup_orbs: Dict[str, PowerUpOrb] = {}
        self.mine_pickups: Dict[str, MinePickup] = {}
        self.mines: Dict[str, Mine] = {}
        self.wormhole_portals: Dict[str, WormholePortal] = {}
        self.wormhole_counter = 0
        self.trail_segments: list = []
        self.connections: Dict[str, any] = {}
        self.orb_counter = 0
        self.spike_counter = 0
        self.golden_counter = 0
        self.wall_counter = 0
        self.projectile_counter = 0
        self.powerup_counter = 0
        self.powerup_respawn_timers: list = []
        self.mine_pickup_counter = 0
        self.mine_pickup_respawn_timers: list = []
        self.mine_counter = 0
        # Kill feed
        self.kill_feed: list = []
        # Leaderboard cache (updated every 1 second instead of every tick)
        self._cached_leaderboard: list = []
        self._leaderboard_update_time: float = 0
        self._leaderboard_cache_duration: float = 1.0
        # Orb serialization caches (invalidated on collect/respawn)
        self._energy_orbs_cache: list = None
        self._spike_orbs_cache: list = None
        self._golden_orbs_cache: list = None
        self._powerup_orbs_cache: list = None
        self._mine_pickups_cache: list = None
        self._walls_cache: list = None
        self._walls_dirty: bool = False
        self.spawn_walls()
        self.spawn_energy_orbs(ENERGY_ORB_COUNT)
        self.spawn_spike_orbs(SPIKE_ORB_COUNT)
        self.spawn_golden_orbs(GOLDEN_ORB_COUNT)
        self.spawn_powerup_orbs(POWERUP_COUNT)
        self.spawn_mine_pickups()
        self.disaster_manager = DisasterManager(self)

    def generate_color(self) -> str:
        """Generate a vibrant random color, avoiding the green band reserved for energy orbs."""
        GREEN_START, GREEN_END = 0.20, 0.45
        hue = random.random() * (1.0 - (GREEN_END - GREEN_START))
        if hue >= GREEN_START:
            hue += GREEN_END - GREEN_START
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

    def _is_inside_wall(self, x: float, y: float, radius: float) -> bool:
        """Check if a point with given radius overlaps any wall."""
        for wall in self.walls.values():
            if (wall.x - radius < x < wall.x + wall.width + radius and
                wall.y - radius < y < wall.y + wall.height + radius):
                return True
        return False

    def relocate_trapped_orbs(self):
        """Move any orbs trapped inside walls to safe positions after earthquake."""
        moved = False
        for orb in self.energy_orbs.values():
            if self._is_inside_wall(orb.x, orb.y, orb.radius):
                orb.x, orb.y = self.find_safe_orb_position(orb.radius)
                moved = True
        for orb in self.spike_orbs.values():
            if self._is_inside_wall(orb.x, orb.y, orb.radius):
                orb.x, orb.y = self.find_safe_orb_position(orb.radius)
                moved = True
        for orb in self.golden_orbs.values():
            if self._is_inside_wall(orb.x, orb.y, orb.radius):
                orb.x, orb.y = self.find_safe_orb_position(orb.radius)
                moved = True
        for orb in self.powerup_orbs.values():
            if self._is_inside_wall(orb.x, orb.y, orb.radius):
                orb.x, orb.y = self.find_safe_orb_position(orb.radius)
                moved = True
        if moved:
            self._energy_orbs_cache = None
            self._spike_orbs_cache = None
            self._golden_orbs_cache = None
            self._powerup_orbs_cache = None

    def spawn_energy_orbs(self, count: int):
        """Spawn energy orbs at random positions."""
        for _ in range(count):
            self.orb_counter += 1
            orb_id = f"orb_{self.orb_counter}"
            hue = 0.25 + random.random() * 0.15
            r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
            color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
            x, y = self.find_safe_orb_position(ENERGY_ORB_RADIUS)
            self.energy_orbs[orb_id] = EnergyOrb(id=orb_id, x=x, y=y, color=color)

    def spawn_spike_orbs(self, count: int):
        """Spawn evil spike orbs at random positions."""
        for _ in range(count):
            self.spike_counter += 1
            orb_id = f"spike_{self.spike_counter}"
            hue = random.uniform(0.95, 1.0) if random.random() > 0.5 else random.uniform(0.0, 0.05)
            r, g, b = colorsys.hsv_to_rgb(hue, 0.9, 0.9)
            color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
            x, y = self.find_safe_orb_position(SPIKE_ORB_RADIUS)
            self.spike_orbs[orb_id] = SpikeOrb(id=orb_id, x=x, y=y, color=color)

    def spawn_golden_orbs(self, count: int):
        """Spawn rare golden orbs worth extra points."""
        for _ in range(count):
            self.golden_counter += 1
            orb_id = f"golden_{self.golden_counter}"
            x, y = self.find_safe_orb_position(GOLDEN_ORB_RADIUS)
            self.golden_orbs[orb_id] = GoldenOrb(id=orb_id, x=x, y=y)

    def spawn_powerup_orbs(self, count: int):
        """Spawn mystery power-up orbs."""
        for _ in range(count):
            self.powerup_counter += 1
            orb_id = f"powerup_{self.powerup_counter}"
            x, y = self.find_safe_orb_position(POWERUP_RADIUS)
            self.powerup_orbs[orb_id] = PowerUpOrb(id=orb_id, x=x, y=y)
        self._powerup_orbs_cache = None

    def spawn_mine_pickups(self):
        """Spawn super rare mine pickup orbs."""
        for _ in range(MINE_PICKUP_COUNT):
            self.mine_pickup_counter += 1
            pickup_id = f"mine_pickup_{self.mine_pickup_counter}"
            x, y = self.find_safe_spawn()
            self.mine_pickups[pickup_id] = MinePickup(id=pickup_id, x=x, y=y)
        self._mine_pickups_cache = None

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
                id=wall_id, x=cfg["x"], y=cfg["y"],
                width=cfg["width"], height=cfg["height"]
            )

    def add_kill(self, killer_name: str, victim_name: str):
        """Add a kill to the feed."""
        self.kill_feed.append({
            "time": time.time(),
            "killer": killer_name,
            "victim": victim_name
        })
        if len(self.kill_feed) > KILL_FEED_MAX * 2:
            self.kill_feed = self.kill_feed[-KILL_FEED_MAX:]

    def get_kill_feed(self) -> list:
        """Get recent kills for display."""
        current_time = time.time()
        recent = [k for k in self.kill_feed if current_time - k["time"] < KILL_FEED_DURATION]
        return recent[-KILL_FEED_MAX:]

    def activate_boost(self, player_id: str):
        """Activate boost for a player."""
        if player_id not in self.players:
            return
        player = self.players[player_id]
        current_time = time.time()

        # Speed Force: unlimited boost - no cooldown, no mass cost
        if player.active_powerup == "speed_force" and current_time < player.powerup_until:
            player.boost_active_until = current_time + BOOST_DURATION
            return

        if current_time < player.boost_cooldown_until:
            return
        if player.radius <= MIN_RADIUS + BOOST_MASS_COST:
            return

        player.boost_active_until = current_time + BOOST_DURATION
        player.boost_cooldown_until = current_time + BOOST_COOLDOWN
        player.radius -= BOOST_MASS_COST

        # Deploy trail if held
        if player.trail_held:
            player.trail_held = False
            player.active_powerup = "trail"
            player.powerup_until = current_time + POWERUP_DURATIONS["trail"]

    def shoot(self, player_id: str, target_x: float, target_y: float, wormhole: bool = False):
        """Fire a projectile from a player toward a target position."""
        if player_id not in self.players:
            return
        player = self.players[player_id]
        current_time = time.time()

        if not player.alive:
            return

        has_rapid_fire = player.active_powerup == "rapid_fire" and current_time < player.powerup_until
        has_homing = player.homing_missiles_remaining > 0
        has_wormhole = player.wormhole_held

        # Wormhole bypasses the size check (no mass cost, no projectile)
        if not has_wormhole and player.radius < PROJECTILE_MIN_RADIUS:
            return

        if not has_rapid_fire and not has_wormhole and current_time < player.shoot_cooldown_until:
            return

        dx = target_x - player.x
        dy = target_y - player.y
        distance = math.sqrt(dx * dx + dy * dy)
        if distance < 1:
            return

        ndx = dx / distance
        ndy = dy / distance

        # Wormhole: fire portal, no mass cost, no cooldown consumed
        if wormhole:
            if not has_wormhole:
                return  # stale client state - ignore, do not fire a projectile
            player.wormhole_held = False
            self.wormhole_counter += 1
            portal_id = f"wormhole_{self.wormhole_counter}"
            portal_speed = player.get_speed(current_time) + WORMHOLE_SPEED_BONUS
            self.wormhole_portals[portal_id] = WormholePortal(
                id=portal_id,
                owner_id=player_id,
                x=player.x + ndx * (player.radius + WORMHOLE_RADIUS + 2),
                y=player.y + ndy * (player.radius + WORMHOLE_RADIUS + 2),
                dx=ndx,
                dy=ndy,
                speed=portal_speed,
                travel_remaining=WORMHOLE_TRAVEL_DIST,
                traveling=True,
                created_at=current_time
            )
            return

        if has_homing:
            player.shoot_cooldown_until = current_time + PROJECTILE_COOLDOWN
            player.homing_missiles_remaining -= 1
        elif not has_rapid_fire:
            player.radius -= PROJECTILE_COST
            player.shoot_cooldown_until = current_time + PROJECTILE_COOLDOWN

        self.projectile_counter += 1
        proj_id = f"proj_{self.projectile_counter}"

        if has_homing:
            self.projectiles[proj_id] = HomingMissile(
                id=proj_id,
                owner_id=player_id,
                x=player.x + ndx * (player.radius + 10),
                y=player.y + ndy * (player.radius + 10),
                dx=ndx,
                dy=ndy,
                color="#ffaa00",
                created_at=current_time,
                lifetime=HOMING_MISSILE_LIFETIME,
                radius=8,
                target_id="",
                speed=HOMING_MISSILE_SPEED,
                tracking_strength=HOMING_TRACKING_STRENGTH
            )
        else:
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

    def place_mine(self, player_id: str):
        """Place a mine at the player's current position."""
        if player_id not in self.players:
            return
        player = self.players[player_id]

        if not player.alive or player.mines_remaining <= 0:
            return
        if player.mines_placed >= MINE_MAX_COUNT:
            return

        self.mine_counter += 1
        mine_id = f"mine_{self.mine_counter}"
        self.mines[mine_id] = Mine(
            id=mine_id,
            owner_id=player_id,
            x=player.x,
            y=player.y,
            armed_at=time.time() + MINE_ARM_DELAY,
            color=player.color
        )
        player.mines_remaining -= 1
        player.mines_placed += 1

    def add_player(self, player_id: str, name: str, websocket) -> Player:
        """Add a new player to the game."""
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
        if len(self.players) >= 2:
            for p in self.players.values():
                p.played_with_others = True
        return player

    def find_safe_spawn(self) -> tuple:
        """Find a spawn point not inside a wall."""
        for _ in range(50):
            x = random.uniform(100, WORLD_WIDTH - 100)
            y = random.uniform(100, WORLD_HEIGHT - 100)
            safe = True
            for wall in self.walls.values():
                if (wall.x - 50 < x < wall.x + wall.width + 50 and
                    wall.y - 50 < y < wall.y + wall.height + 50):
                    safe = False
                    break
            if safe:
                return x, y
        return WORLD_WIDTH // 2, WORLD_HEIGHT // 2

    def remove_player(self, player_id: str):
        """Remove a player from the game."""
        if player_id in self.players:
            player = self.players[player_id]
            if player.peak_score_with_others > 0:
                record_alltime_score(player.name, player.peak_score_with_others)
            del self.players[player_id]
        if player_id in self.connections:
            del self.connections[player_id]

    def add_spectator(self, spectator_id: str, name: str, websocket) -> Spectator:
        """Add a new spectator to the game."""
        spectator = Spectator(
            id=spectator_id,
            name=sanitize_name(name),
            websocket=websocket
        )
        self.spectators[spectator_id] = spectator
        self.connections[spectator_id] = websocket
        return spectator

    def remove_spectator(self, spectator_id: str):
        """Remove a spectator from the game."""
        if spectator_id in self.spectators:
            del self.spectators[spectator_id]
        if spectator_id in self.connections:
            del self.connections[spectator_id]

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
            player.trail_held = False
            player.wormhole_held = False

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

            player.x = max(player.radius, min(WORLD_WIDTH - player.radius, player.x))
            player.y = max(player.radius, min(WORLD_HEIGHT - player.radius, player.y))

            self._resolve_wall_collisions(player, prev_x, prev_y, current_time)

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
        """Handle all orb pickup collisions and respawns."""
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
                    if powerup_type == "homing_missiles":
                        player.homing_missiles_remaining = HOMING_MISSILES_AMMO
                    elif powerup_type == "trail":
                        player.wormhole_held = False
                        player.trail_held = True
                    elif powerup_type == "wormhole":
                        player.trail_held = False
                        player.wormhole_held = True
                    else:
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

    def _collect_mine_pickups(self, current_time: float):
        """Collect mine pickup orbs (super rare)."""
        pickups_to_remove = []
        for pickup_id, pickup in self.mine_pickups.items():
            for player in self.players.values():
                if not player.alive:
                    continue
                dx = player.x - pickup.x
                dy = player.y - pickup.y
                combined = player.radius + pickup.radius
                if dx * dx + dy * dy < combined * combined:
                    if player.mines_remaining >= MINE_MAX_COUNT:
                        continue
                    player.mines_remaining = min(player.mines_remaining + 1, MINE_MAX_COUNT)
                    pickups_to_remove.append(pickup_id)
                    break
        if pickups_to_remove:
            for pickup_id in pickups_to_remove:
                del self.mine_pickups[pickup_id]
            self._mine_pickups_cache = None
            for _ in pickups_to_remove:
                self.mine_pickup_respawn_timers.append(current_time + MINE_PICKUP_RESPAWN_DELAY)

    def _process_mine_pickup_respawns(self, current_time: float):
        """Respawn mine pickups after delay."""
        if self.mine_pickup_respawn_timers:
            respawns = [t for t in self.mine_pickup_respawn_timers if current_time >= t]
            if respawns:
                self.mine_pickup_respawn_timers = [t for t in self.mine_pickup_respawn_timers if current_time < t]
                self.spawn_mine_pickups()

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
            # Homing tracking - continuous proximity-based re-acquisition
            if isinstance(proj, HomingMissile):
                target = self.players.get(proj.target_id) if proj.target_id else None
                if target and (not target.alive or target.has_protection(current_time)):
                    target = None
                    proj.target_id = ""

                if not target:
                    nearest = None
                    min_dist_sq = HOMING_REACQUIRE_RANGE * HOMING_REACQUIRE_RANGE
                    for p in self.players.values():
                        if not p.alive or p.id == proj.owner_id or p.has_protection(current_time):
                            continue
                        pdx = p.x - proj.x
                        pdy = p.y - proj.y
                        d_sq = pdx * pdx + pdy * pdy
                        if d_sq < min_dist_sq:
                            if not self._line_blocked_by_wall(proj.x, proj.y, p.x, p.y):
                                min_dist_sq = d_sq
                                nearest = p
                    if nearest:
                        proj.target_id = nearest.id
                        target = nearest

                if target:
                    if self._line_blocked_by_wall(proj.x, proj.y, target.x, target.y):
                        proj.target_id = ""
                    else:
                        dx = target.x - proj.x
                        dy = target.y - proj.y
                        dist = math.sqrt(dx * dx + dy * dy)
                        if dist > 1:
                            target_dx = dx / dist
                            target_dy = dy / dist
                            proj.dx += (target_dx - proj.dx) * proj.tracking_strength
                            proj.dy += (target_dy - proj.dy) * proj.tracking_strength
                            mag = math.sqrt(proj.dx * proj.dx + proj.dy * proj.dy)
                            if mag > 0:
                                proj.dx /= mag
                                proj.dy /= mag

            if isinstance(proj, HomingMissile):
                age = current_time - proj.created_at
                ramp = min(1.0, HOMING_MISSILE_INITIAL_SPEED_RATIO + (1.0 - HOMING_MISSILE_INITIAL_SPEED_RATIO) * (age / HOMING_MISSILE_RAMP_TIME))
                speed = proj.speed * ramp
            else:
                speed = PROJECTILE_SPEED
            proj.x += proj.dx * speed
            proj.y += proj.dy * speed

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

    def _line_blocked_by_wall(self, x1: float, y1: float, x2: float, y2: float) -> bool:
        """Check if a line segment from (x1,y1) to (x2,y2) intersects any wall (Liang-Barsky)."""
        dx = x2 - x1
        dy = y2 - y1
        for wall in self.walls.values():
            p = [-dx, dx, -dy, dy]
            q = [x1 - wall.x, wall.x + wall.width - x1, y1 - wall.y, wall.y + wall.height - y1]
            t_min, t_max = 0.0, 1.0
            valid = True
            for i in range(4):
                if p[i] == 0:
                    if q[i] < 0:
                        valid = False
                        break
                else:
                    t = q[i] / p[i]
                    if p[i] < 0:
                        t_min = max(t_min, t)
                    else:
                        t_max = min(t_max, t)
                    if t_min > t_max:
                        valid = False
                        break
            if valid:
                return True
        return False

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
                damage = HOMING_MISSILE_DAMAGE if isinstance(proj, HomingMissile) else PROJECTILE_DAMAGE
                player.radius = max(MIN_RADIUS, player.radius - damage)
                if player.radius <= MIN_RADIUS:
                    shooter = self.players.get(proj.owner_id)
                    if shooter and shooter.alive and shooter.radius > player.radius * CONSUME_RATIO:
                        player.alive = False
                        shooter.score += KILL_BASE_SCORE + int(player.score * KILL_SCORE_RATIO)
                        player.score = 0
                        self.add_kill(shooter.name, player.name)
                return True
        return False

    def _update_mines(self, current_time: float):
        """Update mine state and check for proximity triggers."""
        mines_to_remove = []
        for mine_id, mine in self.mines.items():
            if current_time < mine.armed_at:
                continue

            for player in self.players.values():
                if not player.alive or player.id == mine.owner_id:
                    continue
                dx = player.x - mine.x
                dy = player.y - mine.y
                dist_sq = dx * dx + dy * dy

                if dist_sq < MINE_PROXIMITY_TRIGGER * MINE_PROXIMITY_TRIGGER:
                    self._detonate_mine(mine, current_time)
                    mines_to_remove.append(mine_id)
                    break

        for mine_id in mines_to_remove:
            owner_id = self.mines[mine_id].owner_id
            del self.mines[mine_id]
            if owner_id in self.players:
                self.players[owner_id].mines_placed -= 1

    def _detonate_mine(self, mine: Mine, current_time: float):
        """Detonate a mine, damaging nearby players."""
        for player in self.players.values():
            if not player.alive or player.has_protection(current_time):
                continue
            dx = player.x - mine.x
            dy = player.y - mine.y
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < MINE_BLAST_RADIUS:
                damage_factor = 1.0 - (dist / MINE_BLAST_RADIUS) * 0.5
                player.radius = max(MIN_RADIUS, player.radius - MINE_DAMAGE * damage_factor)

                if dist > 0:
                    knockback = 40 * damage_factor
                    player.x += (dx / dist) * knockback
                    player.y += (dy / dist) * knockback

                if player.radius <= MIN_RADIUS:
                    player.alive = False
                    player.score = 0
                    owner = self.players.get(mine.owner_id)
                    if owner:
                        self.add_kill(owner.name, player.name)

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

        magnet_energy_moved = False
        magnet_golden_moved = False
        for player in self.players.values():
            if not player.alive or player.active_powerup != "magnet" or current_time >= player.powerup_until:
                continue
            range_sq = MAGNET_RANGE * MAGNET_RANGE
            for orb in self.energy_orbs.values():
                dx = player.x - orb.x
                dy = player.y - orb.y
                dist_sq = dx * dx + dy * dy
                if dist_sq < range_sq and dist_sq > 1:
                    dist = math.sqrt(dist_sq)
                    orb.x += (dx / dist) * MAGNET_STRENGTH
                    orb.y += (dy / dist) * MAGNET_STRENGTH
                    magnet_energy_moved = True
            for orb in self.golden_orbs.values():
                dx = player.x - orb.x
                dy = player.y - orb.y
                dist_sq = dx * dx + dy * dy
                if dist_sq < range_sq and dist_sq > 1:
                    dist = math.sqrt(dist_sq)
                    orb.x += (dx / dist) * MAGNET_STRENGTH
                    orb.y += (dy / dist) * MAGNET_STRENGTH
                    magnet_golden_moved = True
        if magnet_energy_moved:
            self._energy_orbs_cache = None
        if magnet_golden_moved:
            self._golden_orbs_cache = None

    def _update_trail_segments(self, current_time: float):
        """Place new trail segments, expire old ones, check collisions."""
        for player in self.players.values():
            if not player.alive:
                continue
            if player.active_powerup != "trail" or current_time >= player.powerup_until:
                continue
            if current_time - player.trail_last_segment_time >= TRAIL_SEGMENT_INTERVAL:
                self.trail_segments.append({
                    "x": player.x,
                    "y": player.y,
                    "owner_id": player.id,
                    "color": player.color,
                    "expires_at": current_time + TRAIL_SEGMENT_LIFETIME,
                })
                player.trail_last_segment_time = current_time

        segments_to_remove = []
        for i, seg in enumerate(self.trail_segments):
            if current_time >= seg["expires_at"]:
                segments_to_remove.append(i)
                continue
            for player in self.players.values():
                if not player.alive or player.id == seg["owner_id"] or player.has_protection(current_time):
                    continue
                dx = player.x - seg["x"]
                dy = player.y - seg["y"]
                combined = player.radius + TRAIL_SEGMENT_RADIUS
                if dx * dx + dy * dy < combined * combined:
                    player.radius = max(MIN_RADIUS, player.radius - TRAIL_DAMAGE)
                    if player.radius <= MIN_RADIUS:
                        player.alive = False
                        player.score = 0
                        owner = self.players.get(seg["owner_id"])
                        if owner:
                            self.add_kill(owner.name, player.name)
                    segments_to_remove.append(i)
                    break

        for i in reversed(sorted(set(segments_to_remove))):
            self.trail_segments.pop(i)

    def _update_wormhole_portals(self, current_time: float):
        """Move traveling portals, check player collisions."""
        portals_to_remove = []
        for portal_id, portal in self.wormhole_portals.items():
            if portal.traveling:
                step = min(portal.speed, portal.travel_remaining)
                portal.x += portal.dx * step
                portal.y += portal.dy * step
                portal.travel_remaining -= step
                if portal.travel_remaining <= 0:
                    portal.traveling = False

            if current_time - portal.created_at > WORMHOLE_LIFETIME:
                portals_to_remove.append(portal_id)
                continue

            hit = False
            for player in self.players.values():
                if not player.alive:
                    continue
                dx = player.x - portal.x
                dy = player.y - portal.y
                combined = player.radius + WORMHOLE_RADIUS
                if dx * dx + dy * dy >= combined * combined:
                    continue

                if player.id == portal.owner_id:
                    if portal.traveling:
                        continue
                    for _ in range(100):
                        ex = random.uniform(50, WORLD_WIDTH - 50)
                        ey = random.uniform(50, WORLD_HEIGHT - 50)
                        dist_sq = (ex - portal.x) ** 2 + (ey - portal.y) ** 2
                        if dist_sq >= WORMHOLE_MIN_EXIT_DIST ** 2:
                            inside_wall = False
                            for wall in self.walls.values():
                                if (wall.x <= ex <= wall.x + wall.width and
                                        wall.y <= ey <= wall.y + wall.height):
                                    inside_wall = True
                                    break
                            if not inside_wall:
                                player.x = ex
                                player.y = ey
                                player.invincible_until = current_time + 1.0
                                break
                    hit = True
                else:
                    if not player.has_protection(current_time):
                        owner = self.players.get(portal.owner_id)
                        player.radius = max(MIN_RADIUS, player.radius - WORMHOLE_DAMAGE)
                        if player.radius <= MIN_RADIUS:
                            player.alive = False
                            player.score = 0
                            if owner:
                                self.add_kill(owner.name, player.name)
                    hit = True

                if hit:
                    portals_to_remove.append(portal_id)
                    break

        for portal_id in portals_to_remove:
            if portal_id in self.wormhole_portals:
                del self.wormhole_portals[portal_id]

    def tick(self):
        """Update game state for one tick."""
        current_time = time.time()
        self._move_players(current_time)
        self._check_orb_collisions(current_time)
        self._collect_mine_pickups(current_time)
        self._process_mine_pickup_respawns(current_time)
        self._check_player_collisions(current_time)
        self._update_projectiles(current_time)
        self._update_mines(current_time)
        self._update_critical_mass(current_time)
        self._update_powerups(current_time)
        self._update_trail_segments(current_time)
        self._update_wormhole_portals(current_time)
        self.disaster_manager.tick(current_time)
        for player in self.players.values():
            if player.score > player.peak_score:
                player.peak_score = player.score
            if player.played_with_others and player.score > player.peak_score_with_others:
                player.peak_score_with_others = player.score

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
        if self._energy_orbs_cache is None:
            self._energy_orbs_cache = [o.to_dict() for o in self.energy_orbs.values()]
        if self._spike_orbs_cache is None:
            self._spike_orbs_cache = [o.to_dict() for o in self.spike_orbs.values()]
        if self._golden_orbs_cache is None:
            self._golden_orbs_cache = [o.to_dict() for o in self.golden_orbs.values()]
        if self._powerup_orbs_cache is None:
            self._powerup_orbs_cache = [o.to_dict() for o in self.powerup_orbs.values()]
        if self._mine_pickups_cache is None:
            self._mine_pickups_cache = [o.to_dict() for o in self.mine_pickups.values()]

        state = {
            "type": "state",
            "players": [p.to_dict(current_time) for p in self.players.values()],
            "energy_orbs": self._energy_orbs_cache,
            "spike_orbs": self._spike_orbs_cache,
            "golden_orbs": self._golden_orbs_cache,
            "powerup_orbs": self._powerup_orbs_cache,
            "mine_pickups": self._mine_pickups_cache,
            "mines": [m.to_dict() for m in self.mines.values()],
            "projectiles": [p.to_dict() for p in self.projectiles.values()],
            "wormhole_portals": [p.to_dict() for p in self.wormhole_portals.values()],
            "trail_segments": [{"x": round(s["x"], 1), "y": round(s["y"], 1), "color": s["color"],
                                 "ttl": round(s["expires_at"] - current_time, 2)} for s in self.trail_segments],
            "kill_feed": self.get_kill_feed(),
            "leaderboard": self.get_leaderboard(),
            "disaster": self.disaster_manager.get_state(current_time)
        }

        if self._walls_dirty:
            if self._walls_cache is None:
                self._walls_cache = [w.to_dict() for w in self.walls.values()]
            state["walls"] = self._walls_cache
            self._walls_dirty = False

        return state

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
