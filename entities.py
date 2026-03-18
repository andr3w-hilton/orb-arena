"""
Orb Arena - Entity Dataclasses
All game object definitions: orbs, players, projectiles, hazards, walls.
"""

import time
from dataclasses import dataclass
from typing import Optional

from constants import (
    ENERGY_ORB_RADIUS, SPIKE_ORB_RADIUS, GOLDEN_ORB_RADIUS, POWERUP_RADIUS,
    PROJECTILE_RADIUS, PROJECTILE_LIFETIME,
    WORMHOLE_TRAVEL_DIST,
    METEOR_BLAST_RADIUS, BLACK_HOLE_MAX_RADIUS, BOSS_RADIUS,
    BASE_SPEED, INITIAL_RADIUS, SPEED_SCALING,
    BOOST_SPEED_MULTIPLIER, TRAIL_SPEED_MULTIPLIER,
    CRITICAL_MASS_TIMER,
)


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
class HomingMissile(Projectile):
    target_id: str = ""
    tracking_strength: float = 0.08
    speed: float = 14

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "dx": round(self.dx, 3),
            "dy": round(self.dy, 3),
            "radius": self.radius,
            "color": self.color,
            "homing": True
        }


@dataclass
class WormholePortal:
    id: str
    owner_id: str
    x: float
    y: float
    dx: float           # normalized travel direction
    dy: float
    speed: float = 16.0
    travel_remaining: float = WORMHOLE_TRAVEL_DIST
    traveling: bool = True
    created_at: float = 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "dx": round(self.dx, 4),
            "dy": round(self.dy, 4),
            "traveling": self.traveling
        }


@dataclass
class Mine:
    id: str
    owner_id: str
    x: float
    y: float
    radius: float = 20
    color: str = "#ff6600"
    armed_at: float = 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "radius": self.radius,
            "color": self.color,
            "armed": time.time() >= self.armed_at
        }


@dataclass
class MinePickup(BaseOrb):
    radius: float = 18
    color: str = "#ff3300"


@dataclass
class MissileTurret:
    id: str
    x: float
    y: float
    active: bool = False
    last_fired: float = 0.0

    def to_dict(self):
        return {"id": self.id, "x": self.x, "y": self.y, "active": self.active}


@dataclass
class Wall:
    id: str
    x: float
    y: float
    width: float
    height: float
    color: str = "#334455"
    hp: int = 3
    max_hp: int = 3

    def to_dict(self):
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "color": self.color,
            "hp": self.hp,
            "max_hp": self.max_hp,
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
class BossOrb:
    id: str
    x: float
    y: float
    radius: float = BOSS_RADIUS
    weakened_until: float = 0.0
    shielded: bool = False

    def to_dict(self, current_time: float):
        return {
            "id": self.id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "radius": self.radius,
            "weakened": current_time < self.weakened_until,
            "weakened_remaining": round(max(0.0, self.weakened_until - current_time), 1),
            "shielded": self.shielded,
        }


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
    peak_score: int = 0
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
    # Mine tracking
    mines_remaining: int = 0  # how many mines can still be placed
    mines_placed: int = 0  # how many currently on map
    # Homing missile ammo
    homing_missiles_remaining: int = 0
    # Trail power-up tracking
    trail_held: bool = False  # held but not yet activated
    wormhole_held: bool = False  # held but not yet fired
    # Hall of fame: only tracks score earned while 2+ players are present
    played_with_others: bool = False
    peak_score_with_others: int = 0
    trail_last_segment_time: float = 0.0
    # Challenge mode: fixed speed override (bypasses radius-based scaling)
    speed_override: Optional[float] = None

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
            "powerup_remaining": round(max(0, self.powerup_until - current_time), 1) if self.active_powerup else 0,
            "mines_remaining": self.mines_remaining,
            "homing_missiles_remaining": self.homing_missiles_remaining,
            "trail_held": self.trail_held,
            "wormhole_held": self.wormhole_held
        }

    def get_speed(self, current_time: float):
        # Larger players move slower, smaller players are much faster
        base = self.speed_override if self.speed_override is not None \
            else BASE_SPEED * (INITIAL_RADIUS / self.radius) ** SPEED_SCALING
        # Apply boost multiplier if active
        if current_time < self.boost_active_until:
            return base * BOOST_SPEED_MULTIPLIER
        # Tron trail grants a speed boost while active - lean into the light-cycle fantasy
        if self.active_powerup == "trail" and current_time < self.powerup_until:
            return base * TRAIL_SPEED_MULTIPLIER
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


@dataclass
class Spectator:
    id: str
    name: str
    websocket: any
