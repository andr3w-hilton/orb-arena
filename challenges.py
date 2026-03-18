"""
Orb Arena - Challenge Game Modes
ChallengeGame (Missile Magnet), RallyRunGame (Nitro Orb), BossHuntGame (Hunter Seeker).
"""

import math
import random
import time
from typing import Optional

from constants import (
    WORLD_WIDTH, WORLD_HEIGHT, MIN_RADIUS, INITIAL_RADIUS,
    BOOST_DURATION,
    HOMING_MISSILE_DAMAGE, PROJECTILE_DAMAGE, KILL_BASE_SCORE, KILL_SCORE_RATIO, CONSUME_RATIO,
    HOMING_MISSILES_AMMO, POWERUP_DURATIONS, POWERUP_RESPAWN_DELAY,
    TURRET_POSITIONS, TURRET_INITIAL_ACTIVE, TURRET_ACTIVATE_INTERVAL,
    TURRET_FIRE_INTERVAL_START, TURRET_FIRE_INTERVAL_MIN, TURRET_FIRE_INTERVAL_REDUCTION,
    TURRET_MISSILE_COLOR, TURRET_MISSILE_LIFETIME, TURRET_MISSILE_SPEED, TURRET_MISSILE_TRACKING,
    RALLY_TRACK_WAYPOINTS, RALLY_BARRIER_POSITIONS, RALLY_CHECKPOINT_POSITIONS,
    RALLY_TRACK_HALF_WIDTH, RALLY_MINE_SPACING, RALLY_PLAYER_RADIUS, RALLY_PLAYER_SPEED,
    RALLY_MAX_LAPS, RALLY_ESCALATION_CORNERS, BARRIER_MINE_REARM_DELAY,
    TRAIL_SEGMENT_INTERVAL, TRAIL_SEGMENT_LIFETIME, MINE_PROXIMITY_TRIGGER,
    BOSS_RADIUS, BOSS_SPEED_BASE, BOSS_SPEED_MAX, BOSS_SPEED_RAMP_DURATION,
    BOSS_WEAKEN_DURATION, BOSS_WEAKEN_SPEED_MULT, BOSS_WALL_REPULSION_RANGE,
    BOSS_SHOOT_PHASE_INTERVAL, BOSS_SHOOT_PHASE_DURATION, BOSS_SHOOT_COOLDOWN,
    BOSS_SHOOT_FIRE_INTERVAL, BOSS_SHOT_SPEED, BOSS_SHOT_DAMAGE, BOSS_SHOT_RADIUS, BOSS_SHOT_LIFETIME,
    BOSS_HUNT_POWERUP_TYPES,
    CAMP_TRIGGER_TIME, CAMP_CLOSE_THRESHOLD, CAMP_PLAYER_MOVE_THRESHOLD,
    STRIKE_PHASE_DURATION, STRIKE_COOLDOWN, STRIKE_BARRAGE_SHOTS, STRIKE_BARRAGE_INTERVAL,
    STRIKE_SCATTER, STRIKE_SHOT_SPEED, STRIKE_SHOT_RADIUS, STRIKE_SHOT_DAMAGE, STRIKE_SHOT_LIFETIME,
    _dist_to_track,
)
from entities import (
    Player, EnergyOrb, SpikeOrb, GoldenOrb, Mine, MissileTurret, Wall,
    Projectile, HomingMissile, BossOrb,
)
from game import GameState


class ChallengeGame(GameState):
    """Isolated single-player challenge game instance."""

    def __init__(self, player_id: str):
        super().__init__()
        self.player_id = player_id
        self.challenge_start_time = time.time()
        self.turrets = [
            MissileTurret(
                id=f"turret_{i}",
                x=float(x),
                y=float(y),
                active=(i < TURRET_INITIAL_ACTIVE),
                last_fired=self.challenge_start_time - random.uniform(0.0, 2.0),
            )
            for i, (x, y) in enumerate(TURRET_POSITIONS)
        ]
        self._current_fire_interval = TURRET_FIRE_INTERVAL_START
        self._wall_respawns: list = []
        self._wall_respawn_counter: int = 0

    def get_elapsed(self) -> float:
        return time.time() - self.challenge_start_time

    def get_wave(self) -> int:
        return 1 + int(self.get_elapsed() / TURRET_ACTIVATE_INTERVAL)

    def tick(self):
        super().tick()
        current_time = time.time()
        elapsed = self.get_elapsed()
        self._update_turret_difficulty(elapsed)
        self._fire_turret_missiles(current_time)
        self._check_projectile_collisions()
        self._update_wall_respawns(current_time)

    def _update_turret_difficulty(self, elapsed: float):
        turrets_active = min(len(self.turrets), TURRET_INITIAL_ACTIVE + int(elapsed / TURRET_ACTIVATE_INTERVAL))
        for i, turret in enumerate(self.turrets):
            turret.active = i < turrets_active
        reduction = min(
            TURRET_FIRE_INTERVAL_START - TURRET_FIRE_INTERVAL_MIN,
            (elapsed / TURRET_ACTIVATE_INTERVAL) * TURRET_FIRE_INTERVAL_REDUCTION
        )
        self._current_fire_interval = TURRET_FIRE_INTERVAL_START - reduction

    def _fire_turret_missiles(self, current_time: float):
        player = self.players.get(self.player_id)
        if not player or not player.alive:
            return
        for turret in self.turrets:
            if not turret.active:
                continue
            if current_time - turret.last_fired >= self._current_fire_interval:
                turret.last_fired = current_time
                self._spawn_turret_missile(turret, player, current_time)

    def _spawn_turret_missile(self, turret: MissileTurret, player: Player, current_time: float):
        dx = player.x - turret.x
        dy = player.y - turret.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1:
            return
        ndx, ndy = dx / dist, dy / dist
        self.projectile_counter += 1
        proj_id = f"tmissile_{self.projectile_counter}"
        self.projectiles[proj_id] = HomingMissile(
            id=proj_id,
            owner_id=turret.id,
            x=turret.x + ndx * 30,
            y=turret.y + ndy * 30,
            dx=ndx,
            dy=ndy,
            color=TURRET_MISSILE_COLOR,
            created_at=current_time,
            lifetime=TURRET_MISSILE_LIFETIME,
            radius=8,
            target_id=player.id,
            speed=TURRET_MISSILE_SPEED,
            tracking_strength=TURRET_MISSILE_TRACKING,
        )

    def _check_projectile_collisions(self):
        """Player-fired projectiles can destroy incoming turret missiles."""
        player_projs = {pid: p for pid, p in self.projectiles.items()
                        if p.owner_id == self.player_id}
        turret_missiles = {pid: p for pid, p in self.projectiles.items()
                           if p.owner_id.startswith("turret_")}
        to_remove = set()
        for ppid, pp in player_projs.items():
            if ppid in to_remove:
                continue
            for tmid, tm in turret_missiles.items():
                if tmid in to_remove:
                    continue
                dx = pp.x - tm.x
                dy = pp.y - tm.y
                combined = pp.radius + tm.radius
                if dx * dx + dy * dy < combined * combined:
                    to_remove.add(ppid)
                    to_remove.add(tmid)
                    break
        for proj_id in to_remove:
            if proj_id in self.projectiles:
                del self.projectiles[proj_id]

    def _projectile_hit_wall(self, proj) -> bool:
        """Override: turret missiles damage walls (3 hits to destroy). Player shots pass through walls."""
        if not proj.owner_id.startswith("turret_"):
            return False
        for wall_id, wall in list(self.walls.items()):
            closest_x = max(wall.x, min(proj.x, wall.x + wall.width))
            closest_y = max(wall.y, min(proj.y, wall.y + wall.height))
            dist_x = proj.x - closest_x
            dist_y = proj.y - closest_y
            if math.sqrt(dist_x * dist_x + dist_y * dist_y) < proj.radius:
                wall.hp -= 1
                if wall.hp <= 0:
                    del self.walls[wall_id]
                    self._wall_respawns.append((time.time() + 10.0, wall.width, wall.height))
                self._walls_cache = None
                self._walls_dirty = True
                return True
        return False

    def _update_wall_respawns(self, current_time: float):
        """Respawn destroyed walls as single rectangles at random positions."""
        remaining = []
        spawned = False
        for respawn_time, width, height in self._wall_respawns:
            if current_time >= respawn_time:
                x = random.uniform(200, WORLD_WIDTH - 200 - width)
                y = random.uniform(200, WORLD_HEIGHT - 200 - height)
                self._wall_respawn_counter += 1
                wall_id = f"wall_r{self._wall_respawn_counter}"
                self.walls[wall_id] = Wall(id=wall_id, x=x, y=y, width=width, height=height, hp=3, max_hp=3)
                spawned = True
            else:
                remaining.append((respawn_time, width, height))
        self._wall_respawns = remaining
        if spawned:
            self._walls_cache = None
            self._walls_dirty = True

    def _projectile_hit_player(self, proj, current_time: float) -> bool:
        """Override: turret missiles kill the player when they drop to MIN_RADIUS."""
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
                    if proj.owner_id.startswith("turret_"):
                        player.alive = False
                        player.score = 0
                        self.add_kill("Turret", player.name)
                    else:
                        shooter = self.players.get(proj.owner_id)
                        if shooter and shooter.alive and shooter.radius > player.radius * CONSUME_RATIO:
                            player.alive = False
                            shooter.score += KILL_BASE_SCORE + int(player.score * KILL_SCORE_RATIO)
                            player.score = 0
                            self.add_kill(shooter.name, player.name)
                return True
        return False


class RallyRunGame(GameState):
    """Isolated single-player Nitro Orb rally challenge."""

    def __init__(self, player_id: str):
        super().__init__()
        self.player_id = player_id
        self.challenge_start_time = time.time()
        self.lap_count = 0
        self.lap_start_time: Optional[float] = None
        self.run_start_time: Optional[float] = None
        self.final_time: Optional[float] = None
        self.checkpoint_index = 0
        self.total_checkpoints = len(RALLY_CHECKPOINT_POSITIONS)
        self._escalation_mine_counter = 0
        self.decorative_turrets: list = []
        self.countdown_end = time.time() + 3.0
        # Clear normal world populated by parent __init__
        self.energy_orbs.clear()
        self.spike_orbs.clear()
        self.golden_orbs.clear()
        self.powerup_orbs.clear()
        self.mine_pickups.clear()
        self.walls.clear()
        self._energy_orbs_cache = []
        self._spike_orbs_cache = []
        self._powerup_orbs_cache = []
        self._mine_pickups_cache = []
        self._walls_cache = []
        self._walls_dirty = False
        # Build track
        self._spawn_barrier_mines()
        self._spawn_checkpoint_orbs()
        self._spawn_decorative_elements()

    def _spawn_barrier_mines(self):
        for i, (x, y) in enumerate(RALLY_BARRIER_POSITIONS):
            mine_id = f"barrier_{i}"
            self.mines[mine_id] = Mine(
                id=mine_id, owner_id="barrier",
                x=x, y=y, armed_at=0.0, color="#cc2200", radius=15,
            )

    def _spawn_checkpoint_orbs(self):
        i = self.checkpoint_index
        if i >= self.total_checkpoints:
            return
        x, y = RALLY_CHECKPOINT_POSITIONS[i]
        orb_id = f"checkpoint_{i}"
        self.golden_counter += 1
        self.golden_orbs[orb_id] = GoldenOrb(id=orb_id, x=x, y=y)
        self._golden_orbs_cache = None

    def _find_off_track_pos(self, margin: float = 80) -> Optional[tuple]:
        """Find a random world position safely outside the track barriers."""
        min_clear = RALLY_TRACK_HALF_WIDTH + margin
        for _ in range(40):
            x = random.uniform(150, WORLD_WIDTH - 150)
            y = random.uniform(150, WORLD_HEIGHT - 150)
            if _dist_to_track(x, y) > min_clear:
                return (x, y)
        return None

    def _spawn_decorative_elements(self):
        """Scatter game elements in non-track areas for visual richness."""
        # Energy orbs
        for _ in range(60):
            pos = self._find_off_track_pos(margin=60)
            if pos:
                self.orb_counter += 1
                oid = f"orb_{self.orb_counter}"
                self.energy_orbs[oid] = EnergyOrb(id=oid, x=pos[0], y=pos[1])
        self._energy_orbs_cache = None

        # Spike orbs
        for _ in range(20):
            pos = self._find_off_track_pos(margin=60)
            if pos:
                self.spike_counter += 1
                sid = f"spike_{self.spike_counter}"
                self.spike_orbs[sid] = SpikeOrb(id=sid, x=pos[0], y=pos[1])
        self._spike_orbs_cache = None

        # Obstacle walls (infield / outfield)
        wall_specs = [(200, 40), (40, 200), (160, 30), (30, 160), (120, 120), (240, 30)]
        for w, h in wall_specs:
            pos = self._find_off_track_pos(margin=max(w, h) + 80)
            if pos:
                self.wall_counter += 1
                wid = f"wall_d{self.wall_counter}"
                self.walls[wid] = Wall(
                    id=wid, x=pos[0] - w / 2, y=pos[1] - h / 2,
                    width=w, height=h, hp=3, max_hp=3,
                )
        self._walls_cache = None
        self._walls_dirty = True

        # Decorative (inactive) turret emplacements
        turret_candidates = [
            (2100, 1600),
            (2600, 2900),
            (1300, 2700),
            (300,  300),
            (4750, 4750),
        ]
        for i, (tx, ty) in enumerate(turret_candidates):
            if _dist_to_track(tx, ty) > RALLY_TRACK_HALF_WIDTH + 150:
                self.decorative_turrets.append(
                    MissileTurret(id=f"deco_{i}", x=float(tx), y=float(ty), active=False)
                )

    def _collect_energy_orbs(self):
        """Override: decorative only - no collection or respawn."""
        pass

    def _collect_spike_orbs(self, current_time: float):
        """Override: decorative only - no damage or respawn."""
        pass

    def activate_boost(self, player_id: str):
        """Override: no cooldown, no mass cost - boost any time."""
        player = self.players.get(player_id)
        if not player or not player.alive:
            return
        player.boost_active_until = time.time() + BOOST_DURATION
        player.boost_cooldown_until = 0

    def add_rally_player(self, player_id: str, name: str, websocket) -> Player:
        player = self.add_player(player_id, name, websocket)
        player.radius = RALLY_PLAYER_RADIUS
        player.speed_override = RALLY_PLAYER_SPEED
        sx, sy = RALLY_TRACK_WAYPOINTS[0]
        player.x, player.y = float(sx), float(sy)
        player.target_x, player.target_y = float(sx), float(sy)
        return player

    def tick(self):
        player = self.players.get(self.player_id)
        if player and time.time() < self.countdown_end:
            sx, sy = RALLY_TRACK_WAYPOINTS[0]
            player.target_x = float(sx)
            player.target_y = float(sy)
        super().tick()
        player = self.players.get(self.player_id)
        if player and player.alive:
            player.radius = RALLY_PLAYER_RADIUS
            self._check_checkpoints(player)

    def _check_checkpoints(self, player):
        orb_id = f"checkpoint_{self.checkpoint_index}"
        orb = self.golden_orbs.get(orb_id)
        if not orb:
            return
        dx, dy = player.x - orb.x, player.y - orb.y
        collect_sq = (player.radius + orb.radius + 10) ** 2
        if dx * dx + dy * dy < collect_sq:
            del self.golden_orbs[orb_id]
            self._golden_orbs_cache = None
            self.checkpoint_index += 1
            if self.checkpoint_index == 1 and self.run_start_time is None:
                now = time.time()
                self.run_start_time = now
                self.lap_start_time = now
            if self.checkpoint_index >= self.total_checkpoints:
                self._complete_lap()
            else:
                self._spawn_checkpoint_orbs()

    def _complete_lap(self):
        now = time.time()
        self.lap_count += 1
        if self.lap_count >= RALLY_MAX_LAPS:
            if self.run_start_time is not None:
                self.final_time = round(now - self.run_start_time, 2)
            return
        self.lap_start_time = now
        self.checkpoint_index = 0
        self._spawn_checkpoint_orbs()
        if self.lap_count <= 5:
            self._add_escalation_mines()

    def _add_escalation_mines(self):
        """Progressively narrow tight corners after each lap."""
        inner_dist = max(100, RALLY_TRACK_HALF_WIDTH - self.lap_count * 15)
        for corner_idx in RALLY_ESCALATION_CORNERS:
            x, y = RALLY_TRACK_WAYPOINTS[corner_idx]
            prev_x, prev_y = RALLY_TRACK_WAYPOINTS[corner_idx - 1]
            dx, dy = x - prev_x, y - prev_y
            seg_len = math.sqrt(dx * dx + dy * dy)
            if seg_len < 1:
                continue
            ux, uy = dx / seg_len, dy / seg_len
            nx, ny = -uy, ux
            for k in range(3):
                t = seg_len - RALLY_MINE_SPACING * (k + 0.5)
                if t < 0:
                    continue
                mx, my = prev_x + ux * t, prev_y + uy * t
                for side in [1, -1]:
                    self._escalation_mine_counter += 1
                    mine_id = f"esc_{self._escalation_mine_counter}"
                    self.mines[mine_id] = Mine(
                        id=mine_id, owner_id="barrier",
                        x=mx + nx * inner_dist * side,
                        y=my + ny * inner_dist * side,
                        armed_at=0.0, color="#990000", radius=15,
                    )

    def _collect_golden_orbs(self):
        """Override: checkpoint orbs give no mass/score - handled by _check_checkpoints."""
        pass

    def _update_trail_segments(self, current_time: float):
        """Override: visual-only trail always active for the rally player - no collision damage."""
        player = self.players.get(self.player_id)
        if player and player.alive:
            if current_time - player.trail_last_segment_time >= TRAIL_SEGMENT_INTERVAL:
                self.trail_segments.append({
                    "x": player.x,
                    "y": player.y,
                    "owner_id": player.id,
                    "color": player.color,
                    "expires_at": current_time + TRAIL_SEGMENT_LIFETIME,
                })
                player.trail_last_segment_time = current_time
        self.trail_segments = [s for s in self.trail_segments if current_time < s["expires_at"]]

    def _update_mines(self, current_time: float):
        """Override: barrier mines rearm after triggering instead of being removed."""
        for mine in self.mines.values():
            if current_time < mine.armed_at:
                continue
            player = self.players.get(self.player_id)
            if not player or not player.alive:
                continue
            dx, dy = player.x - mine.x, player.y - mine.y
            if dx * dx + dy * dy < MINE_PROXIMITY_TRIGGER * MINE_PROXIMITY_TRIGGER:
                self._detonate_mine(mine, current_time)
                mine.armed_at = current_time + BARRIER_MINE_REARM_DELAY

    def get_rally_state(self) -> dict:
        now = time.time()
        lap_time = round(now - self.lap_start_time, 1) if self.lap_start_time is not None else None
        total_time = round(now - self.run_start_time, 1) if self.run_start_time is not None else None
        return {
            "type": "rally_run",
            "lap": min(self.lap_count + 1, RALLY_MAX_LAPS),
            "max_laps": RALLY_MAX_LAPS,
            "lap_time": lap_time,
            "total_time": total_time,
            "checkpoint": self.checkpoint_index,
            "total_checkpoints": self.total_checkpoints,
            "countdown": round(max(0.0, self.countdown_end - now), 2),
        }

    def is_run_complete(self) -> bool:
        return self.lap_count >= RALLY_MAX_LAPS


class BossHuntGame(GameState):
    """Isolated single-player Hunter Seeker challenge."""

    def __init__(self, player_id: str):
        super().__init__()
        self.player_id = player_id
        self.challenge_start_time = time.time()
        corners = [(400.0, 400.0), (4600.0, 400.0), (400.0, 4600.0), (4600.0, 4600.0)]
        bx, by = random.choice(corners)
        self.boss = BossOrb(id="boss", x=bx, y=by)
        self._shooting_phase = False
        self._next_phase_change = self.challenge_start_time + BOSS_SHOOT_PHASE_INTERVAL
        self._boss_shoot_cooldown_until = 0.0
        self._camp_best_dist = float('inf')
        self._camp_start_time = self.challenge_start_time
        self._camp_player_pos = None
        self._strike_phase = None
        self._strike_phase_until = 0.0
        self._strike_origin = (0.0, 0.0)
        self._strike_next_shot = 0.0
        self._strike_shots_fired = 0
        self._strike_cooldown_until = 0.0

    def get_elapsed(self) -> float:
        return time.time() - self.challenge_start_time

    # Disable mine mechanic for this mode

    def spawn_mine_pickups(self):
        pass

    def _collect_mine_pickups(self, current_time: float):
        pass

    def _process_mine_pickup_respawns(self, current_time: float):
        pass

    def _update_mines(self, current_time: float):
        pass

    # Restrict powerup pool to relevant types

    def _collect_powerup_orbs(self, current_time: float):
        powerups_to_remove = []
        for orb_id, orb in self.powerup_orbs.items():
            player = self.players.get(self.player_id)
            if not player or not player.alive:
                continue
            dx = player.x - orb.x
            dy = player.y - orb.y
            combined = player.radius + orb.radius
            if dx * dx + dy * dy < combined * combined:
                powerup_type = random.choice(BOSS_HUNT_POWERUP_TYPES)
                if powerup_type == "homing_missiles":
                    player.homing_missiles_remaining = HOMING_MISSILES_AMMO
                elif powerup_type == "wormhole":
                    player.trail_held = False
                    player.wormhole_held = True
                else:
                    player.active_powerup = powerup_type
                    player.powerup_until = current_time + POWERUP_DURATIONS.get(powerup_type, 5.0)
                powerups_to_remove.append(orb_id)
                break
        if powerups_to_remove:
            for orb_id in powerups_to_remove:
                del self.powerup_orbs[orb_id]
            self._powerup_orbs_cache = None
            for _ in powerups_to_remove:
                self.powerup_respawn_timers.append(current_time + POWERUP_RESPAWN_DELAY)

    # Boss shot hit detection: kill player at MIN_RADIUS

    def _projectile_hit_player(self, proj, current_time: float) -> bool:
        player = self.players.get(self.player_id)
        if not player or not player.alive or player.has_protection(current_time):
            return False
        if player.id == proj.owner_id:
            return False
        dx = player.x - proj.x
        dy = player.y - proj.y
        combined = player.radius + proj.radius
        if dx * dx + dy * dy < combined * combined:
            damage = HOMING_MISSILE_DAMAGE if isinstance(proj, HomingMissile) else PROJECTILE_DAMAGE
            player.radius = max(MIN_RADIUS, player.radius - damage)
            if player.radius <= MIN_RADIUS and proj.owner_id in ("boss", "strike"):
                player.alive = False
                self.add_kill("Hunter Seeker", player.name)
            return True
        return False

    # Boss AI

    def _move_boss(self, current_time: float):
        """Move boss toward player with wall repulsion for smooth flow."""
        player = self.players.get(self.player_id)
        if not player or not player.alive:
            return

        elapsed = self.get_elapsed()
        ramp = min(elapsed / BOSS_SPEED_RAMP_DURATION, 1.0)
        speed = BOSS_SPEED_BASE + (BOSS_SPEED_MAX - BOSS_SPEED_BASE) * ramp
        if current_time < self.boss.weakened_until:
            speed *= BOSS_WEAKEN_SPEED_MULT

        dx = player.x - self.boss.x
        dy = player.y - self.boss.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1:
            return
        fx = dx / dist
        fy = dy / dist

        for wall in self.walls.values():
            cx = max(wall.x, min(self.boss.x, wall.x + wall.width))
            cy = max(wall.y, min(self.boss.y, wall.y + wall.height))
            wdx = self.boss.x - cx
            wdy = self.boss.y - cy
            wdist = math.sqrt(wdx * wdx + wdy * wdy)
            if 0 < wdist < BOSS_WALL_REPULSION_RANGE:
                strength = (1.0 - wdist / BOSS_WALL_REPULSION_RANGE) * 2.5
                fx += (wdx / wdist) * strength
                fy += (wdy / wdist) * strength

        mag = math.sqrt(fx * fx + fy * fy)
        if mag > 0:
            fx /= mag
            fy /= mag

        self.boss.x = max(self.boss.radius, min(WORLD_WIDTH - self.boss.radius,
                                                 self.boss.x + fx * speed))
        self.boss.y = max(self.boss.radius, min(WORLD_HEIGHT - self.boss.radius,
                                                 self.boss.y + fy * speed))

        # Hard wall collision: push boss out of any wall it has entered
        for wall in self.walls.values():
            cx = max(wall.x, min(self.boss.x, wall.x + wall.width))
            cy = max(wall.y, min(self.boss.y, wall.y + wall.height))
            wdx = self.boss.x - cx
            wdy = self.boss.y - cy
            wdist = math.sqrt(wdx * wdx + wdy * wdy)
            if wdist < self.boss.radius:
                if wdist < 0.001:
                    wdx, wdy, wdist = 0.0, -1.0, 1.0
                overlap = self.boss.radius - wdist
                self.boss.x += (wdx / wdist) * overlap
                self.boss.y += (wdy / wdist) * overlap

    def _check_boss_collision(self, current_time: float):
        """Boss contact-kills the player (boss is always large enough to consume)."""
        player = self.players.get(self.player_id)
        if not player or not player.alive or player.has_protection(current_time):
            return
        dx = player.x - self.boss.x
        dy = player.y - self.boss.y
        combined = player.radius + self.boss.radius
        if dx * dx + dy * dy < combined * combined:
            player.alive = False
            self.add_kill("Hunter Seeker", player.name)

    def _check_player_shots_hit_boss(self, current_time: float):
        """Player projectiles weaken the boss (slow it temporarily)."""
        if self.boss.shielded:
            return
        projs_to_remove = []
        for proj_id, proj in self.projectiles.items():
            if proj.owner_id != self.player_id:
                continue
            dx = proj.x - self.boss.x
            dy = proj.y - self.boss.y
            combined = proj.radius + self.boss.radius
            if dx * dx + dy * dy < combined * combined:
                self.boss.weakened_until = max(
                    self.boss.weakened_until, current_time + BOSS_WEAKEN_DURATION
                )
                projs_to_remove.append(proj_id)
        for proj_id in projs_to_remove:
            if proj_id in self.projectiles:
                del self.projectiles[proj_id]

    def _update_shooting_phase(self, current_time: float):
        """Manage the boss shooting phase state machine and fire shots."""
        if current_time >= self._next_phase_change:
            if not self._shooting_phase:
                self._shooting_phase = True
                self._next_phase_change = current_time + BOSS_SHOOT_PHASE_DURATION
            else:
                self._shooting_phase = False
                self._next_phase_change = current_time + BOSS_SHOOT_COOLDOWN

        if not self._shooting_phase:
            return

        player = self.players.get(self.player_id)
        if not player or not player.alive:
            return
        if current_time < self._boss_shoot_cooldown_until:
            return

        dx = player.x - self.boss.x
        dy = player.y - self.boss.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1:
            return
        ndx, ndy = dx / dist, dy / dist

        self.projectile_counter += 1
        proj_id = f"bossshot_{self.projectile_counter}"
        self.projectiles[proj_id] = Projectile(
            id=proj_id,
            owner_id="boss",
            x=self.boss.x + ndx * (self.boss.radius + 12),
            y=self.boss.y + ndy * (self.boss.radius + 12),
            dx=ndx,
            dy=ndy,
            color="#ff2200",
            created_at=current_time,
            lifetime=BOSS_SHOT_LIFETIME,
            radius=BOSS_SHOT_RADIUS,
        )
        self._boss_shoot_cooldown_until = current_time + BOSS_SHOOT_FIRE_INTERVAL

    def _fire_strike_shot(self, current_time: float):
        """Fire a single barrage round at the locked strike origin with scatter."""
        tx = self._strike_origin[0] + random.uniform(-STRIKE_SCATTER, STRIKE_SCATTER)
        ty = self._strike_origin[1] + random.uniform(-STRIKE_SCATTER, STRIKE_SCATTER)
        angle = random.uniform(0, 2 * math.pi)
        spawn_dist = random.uniform(1500, 2200)
        sx = max(50.0, min(float(WORLD_WIDTH - 50), tx + math.cos(angle) * spawn_dist))
        sy = max(50.0, min(float(WORLD_HEIGHT - 50), ty + math.sin(angle) * spawn_dist))
        dx, dy = tx - sx, ty - sy
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1:
            return
        ndx, ndy = dx / dist, dy / dist
        self.projectile_counter += 1
        self.projectiles[f"strike_{self.projectile_counter}"] = Projectile(
            id=f"strike_{self.projectile_counter}",
            owner_id="strike",
            x=sx, y=sy, dx=ndx, dy=ndy,
            color="#ff8800",
            created_at=current_time,
            lifetime=STRIKE_SHOT_LIFETIME,
            radius=STRIKE_SHOT_RADIUS,
        )

    def _update_precision_strike(self, current_time: float):
        """Track corner camping and run the 3-phase precision strike sequence."""
        player = self.players.get(self.player_id)
        if not player or not player.alive:
            self._strike_phase = None
            self.boss.shielded = False
            return

        current_dist = math.sqrt((self.boss.x - player.x) ** 2 + (self.boss.y - player.y) ** 2)

        if self._strike_phase is not None:
            if self._strike_phase == "targeting" and current_time >= self._strike_phase_until:
                self._strike_phase = "cleared_hot"
                self._strike_phase_until = current_time + STRIKE_PHASE_DURATION

            elif self._strike_phase == "cleared_hot" and current_time >= self._strike_phase_until:
                self._strike_phase = "danger_close"
                self._strike_phase_until = current_time + STRIKE_PHASE_DURATION
                self.boss.shielded = True

            elif self._strike_phase == "danger_close" and current_time >= self._strike_phase_until:
                self._strike_phase = "barrage"
                self._strike_phase_until = current_time + STRIKE_BARRAGE_SHOTS * STRIKE_BARRAGE_INTERVAL + 0.5
                self._strike_next_shot = current_time
                self._strike_shots_fired = 0

            elif self._strike_phase == "barrage":
                if self._strike_shots_fired < STRIKE_BARRAGE_SHOTS and current_time >= self._strike_next_shot:
                    self._fire_strike_shot(current_time)
                    self._strike_shots_fired += 1
                    self._strike_next_shot = current_time + STRIKE_BARRAGE_INTERVAL
                if current_time >= self._strike_phase_until:
                    self._strike_phase = None
                    self.boss.shielded = False
                    self._strike_cooldown_until = current_time + STRIKE_COOLDOWN
                    self._camp_best_dist = current_dist
                    self._camp_start_time = current_time
                    self._camp_player_pos = (player.x, player.y)
            return

        if self._camp_player_pos is None:
            self._camp_player_pos = (player.x, player.y)
        player_moved = math.sqrt(
            (player.x - self._camp_player_pos[0]) ** 2 +
            (player.y - self._camp_player_pos[1]) ** 2
        ) > CAMP_PLAYER_MOVE_THRESHOLD

        if current_dist < self._camp_best_dist - CAMP_CLOSE_THRESHOLD or player_moved:
            self._camp_best_dist = current_dist
            self._camp_start_time = current_time
            self._camp_player_pos = (player.x, player.y)
        elif (current_time - self._camp_start_time >= CAMP_TRIGGER_TIME
              and current_time >= self._strike_cooldown_until):
            self._strike_origin = (player.x, player.y)
            self._strike_phase = "targeting"
            self._strike_phase_until = current_time + STRIKE_PHASE_DURATION
            self._camp_best_dist = current_dist
            self._camp_start_time = current_time
            self._camp_player_pos = (player.x, player.y)

    def tick(self):
        super().tick()
        current_time = time.time()
        self._move_boss(current_time)
        self._check_boss_collision(current_time)
        self._check_player_shots_hit_boss(current_time)
        self._update_shooting_phase(current_time)
        self._update_precision_strike(current_time)

    def build_shared_state(self, current_time: float) -> dict:
        state = super().build_shared_state(current_time)
        state["boss"] = self.boss.to_dict(current_time)
        return state

    def get_boss_hunt_state(self) -> dict:
        now = time.time()
        return {
            "type": "hunter_seeker",
            "time_survived": round(self.get_elapsed(), 1),
            "boss_weakened": now < self.boss.weakened_until,
            "boss_weakened_remaining": round(max(0.0, self.boss.weakened_until - now), 1),
            "shooting_phase": self._shooting_phase,
            "next_phase_in": round(max(0.0, self._next_phase_change - now), 1),
            "strike_phase": self._strike_phase,
            "strike_target": [round(self._strike_origin[0], 1), round(self._strike_origin[1], 1)]
                              if self._strike_phase else None,
        }
