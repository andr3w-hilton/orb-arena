"""
Orb Arena - Game Constants
All configuration values, derived constants, and layout pre-computations.
"""

import math

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
POWERUP_TYPES = ["shield", "rapid_fire", "magnet", "phantom", "speed_force", "homing_missiles", "trail", "wormhole"]
POWERUP_DURATIONS = {"shield": 5.0, "rapid_fire": 5.0, "magnet": 8.0, "phantom": 5.0, "speed_force": 7.0, "trail": 8.0}
HOMING_MISSILES_AMMO = 3  # discrete shots granted on pickup

# Wormhole power-up configuration
WORMHOLE_SPEED_BONUS = 4      # portal travels this many px/tick faster than the firing player
WORMHOLE_TRAVEL_DIST = 250    # px the portal travels before stopping dead
WORMHOLE_LIFETIME = 6.0       # seconds before portal closes on its own
WORMHOLE_DAMAGE = 15          # radius damage dealt to enemy who enters portal
WORMHOLE_RADIUS = 22          # collision/visual radius
WORMHOLE_MIN_EXIT_DIST = 600  # minimum px between entry and exit point
MAGNET_RANGE = 400  # radius for magnet pull
MAGNET_STRENGTH = 22  # speed orbs move toward player (must outpace base speed of 14)

# Trail (Tron) power-up configuration
TRAIL_SEGMENT_LIFETIME = 5.0   # seconds a placed segment persists
TRAIL_SEGMENT_RADIUS = 8       # collision/render radius (same as energy orb)
TRAIL_SEGMENT_INTERVAL = 0.1   # seconds between segment placements (3 ticks at 30 FPS)
TRAIL_DAMAGE = 10              # radius damage on contact (same as projectile)
TRAIL_SPEED_MULTIPLIER = 1.7   # speed boost while trail is actively laying segments

# Mine configuration
MINE_PICKUP_COUNT = 1  # only 1 on map at a time (super rare)
MINE_PICKUP_RESPAWN_DELAY = 90.0  # 90s respawn (3x longer than power-ups)
MINE_MAX_COUNT = 3  # max mines per player
MINE_ARM_DELAY = 0.5
MINE_BLAST_RADIUS = 80
MINE_DAMAGE = 25
MINE_PROXIMITY_TRIGGER = 60

# Nitro Orb (Rally Run) challenge configuration
RALLY_TRACK_HALF_WIDTH = 175    # px from centreline to barrier mine row
RALLY_MINE_SPACING = 140        # px between adjacent barrier mines along edge
RALLY_PLAYER_RADIUS = 20        # fixed orb radius throughout the run
RALLY_PLAYER_SPEED = 16.1       # BASE_SPEED * (INITIAL_RADIUS / 10) ** SPEED_SCALING
BARRIER_MINE_REARM_DELAY = 1.5  # seconds before a triggered barrier mine rearms
RALLY_CHECKPOINT_SPACING = 700  # px between sequential checkpoint orbs
RALLY_MAX_LAPS = 3              # laps per run (death ends early)
RALLY_TRACK_WAYPOINTS = [
    (700,  900),    # 0 - Start / Finish
    (4300, 900),    # 1 - Turn 1 entry (end of main straight)
    (4600, 1500),   # 2 - Turn 1 apex (sweeping right)
    (4500, 2200),   # 3 - Sector 2 entry
    (4100, 2700),   # 4 - Hairpin apex (tightest corner)
    (3200, 2400),   # 5 - Hairpin exit
    (3200, 3800),   # 6 - Back straight south
    (1600, 4200),   # 7 - South corner
    (700,  3600),   # 8 - Final sector entry
    (700,  900),    # 9 - Back to Start / Finish (closed loop)
]
RALLY_ESCALATION_CORNERS = [1, 4, 7]   # waypoint indices of tightest corners


def _compute_rally_layout():
    """Pre-compute barrier mine positions and checkpoint orb centreline positions."""
    barriers = []
    # Segments stored for second-pass checkpoint placement: (x0, y0, ux, uy, seg_len)
    segments = []

    n = len(RALLY_TRACK_WAYPOINTS) - 1
    for i in range(n):
        x0, y0 = RALLY_TRACK_WAYPOINTS[i]
        x1, y1 = RALLY_TRACK_WAYPOINTS[i + 1]
        dx, dy = x1 - x0, y1 - y0
        seg_len = math.sqrt(dx * dx + dy * dy)
        if seg_len < 1:
            continue
        ux, uy = dx / seg_len, dy / seg_len
        nx, ny = -uy, ux  # left-hand normal

        # Barrier mines: start half a spacing in to avoid corner pile-ups
        t = RALLY_MINE_SPACING / 2
        while t < seg_len:
            cx, cy = x0 + ux * t, y0 + uy * t
            barriers.append((cx + nx * RALLY_TRACK_HALF_WIDTH, cy + ny * RALLY_TRACK_HALF_WIDTH))
            barriers.append((cx - nx * RALLY_TRACK_HALF_WIDTH, cy - ny * RALLY_TRACK_HALF_WIDTH))
            t += RALLY_MINE_SPACING

        segments.append((x0, y0, ux, uy, seg_len))

    # Post-filter: remove barrier mines that landed inside the track corridor.
    # At corners the normal-direction offset for the inside of a bend can land
    # much closer to an adjacent segment's centreline than RALLY_TRACK_HALF_WIDTH.
    _MIN_MINE_CENTRELINE_DIST = RALLY_TRACK_HALF_WIDTH - 40  # px

    def _min_dist_to_centreline(px: float, py: float) -> float:
        min_d = float('inf')
        for sx0, sy0, sux, suy, slen in segments:
            ddx, ddy = px - sx0, py - sy0
            proj = max(0.0, min(slen, ddx * sux + ddy * suy))
            rx, ry = px - (sx0 + sux * proj), py - (sy0 + suy * proj)
            d = math.sqrt(rx * rx + ry * ry)
            if d < min_d:
                min_d = d
        return min_d

    barriers = [
        (mx, my) for mx, my in barriers
        if _min_dist_to_centreline(mx, my) >= _MIN_MINE_CENTRELINE_DIST
    ]

    # Second pass: place checkpoint orbs on centreline, sliding clear of barrier mines
    _CHECKPOINT_MIN_MINE_DIST = 100  # px - minimum clearance from any barrier mine
    _CHECKPOINT_SLIDE_STEP = 35      # px - nudge along segment when too close
    _CHECKPOINT_MAX_SLIDES = 4       # attempts before accepting the position anyway

    checkpoints = []
    cp_dist = 0.0
    for x0, y0, ux, uy, seg_len in segments:
        offset = RALLY_CHECKPOINT_SPACING - (cp_dist % RALLY_CHECKPOINT_SPACING)
        t = offset
        while t < seg_len:
            cx, cy = x0 + ux * t, y0 + uy * t
            # Slide forward along centreline if too close to any barrier mine
            for _ in range(_CHECKPOINT_MAX_SLIDES):
                if all(
                    (cx - bx) ** 2 + (cy - by) ** 2 >= _CHECKPOINT_MIN_MINE_DIST ** 2
                    for bx, by in barriers
                ):
                    break
                cx += ux * _CHECKPOINT_SLIDE_STEP
                cy += uy * _CHECKPOINT_SLIDE_STEP
            checkpoints.append((cx, cy))
            t += RALLY_CHECKPOINT_SPACING
        cp_dist += seg_len

    # Remove any checkpoint that lands too close to the start/finish line
    sx, sy = RALLY_TRACK_WAYPOINTS[0]
    _FINISH_LINE_EXCLUSION = 500  # px radius around start/finish to keep clear
    checkpoints = [
        (cx, cy) for cx, cy in checkpoints
        if (cx - sx) ** 2 + (cy - sy) ** 2 >= _FINISH_LINE_EXCLUSION ** 2
    ]

    return barriers, checkpoints


RALLY_BARRIER_POSITIONS, RALLY_CHECKPOINT_POSITIONS = _compute_rally_layout()

# Hunter Seeker challenge configuration
BOSS_RADIUS = 200.0
BOSS_SPEED_BASE = 4.0
BOSS_SPEED_MAX = 11.0
BOSS_SPEED_RAMP_DURATION = 120.0       # seconds to ramp from base to max speed
BOSS_WEAKEN_DURATION = 4.0             # seconds boss is slowed after being hit
BOSS_WEAKEN_SPEED_MULT = 0.45          # speed multiplier when weakened
BOSS_WALL_REPULSION_RANGE = 140        # px from wall edge to start repulsion force
BOSS_SHOOT_PHASE_INTERVAL = 90.0       # seconds between shooting phases starting
BOSS_SHOOT_PHASE_DURATION = 30.0       # seconds each shooting phase lasts
BOSS_SHOOT_COOLDOWN = 60.0             # seconds cooldown after shooting phase ends
BOSS_SHOOT_FIRE_INTERVAL = 2.5         # seconds between shots during shooting phase
BOSS_SHOT_SPEED = 18.0
BOSS_SHOT_DAMAGE = 15
BOSS_SHOT_RADIUS = 8
BOSS_SHOT_LIFETIME = 4.0
BOSS_HUNT_POWERUP_TYPES = ["shield", "rapid_fire", "speed_force", "phantom", "homing_missiles", "wormhole"]

# Corner-buster precision strike configuration
CAMP_TRIGGER_TIME = 10.0        # seconds boss cannot close distance before strike initiates
CAMP_CLOSE_THRESHOLD = 80.0     # boss must reduce distance by this much to reset timer
CAMP_PLAYER_MOVE_THRESHOLD = 300.0  # player moving this far from camp origin resets timer
STRIKE_PHASE_DURATION = 3.0     # seconds each alert phase lasts
STRIKE_COOLDOWN = 25.0          # seconds before another strike can trigger after one ends
STRIKE_BARRAGE_SHOTS = 15
STRIKE_BARRAGE_INTERVAL = 0.2   # seconds between barrage impacts
STRIKE_SCATTER = 50             # px radius scatter around locked target
STRIKE_SHOT_SPEED = 30.0
STRIKE_SHOT_RADIUS = 10
STRIKE_SHOT_DAMAGE = 22
STRIKE_SHOT_LIFETIME = 4.0


def _dist_to_track(px: float, py: float) -> float:
    """Minimum distance from a point to the nearest track segment centreline."""
    min_dist = float('inf')
    n = len(RALLY_TRACK_WAYPOINTS) - 1
    for i in range(n):
        x0, y0 = RALLY_TRACK_WAYPOINTS[i]
        x1, y1 = RALLY_TRACK_WAYPOINTS[i + 1]
        dx, dy = x1 - x0, y1 - y0
        seg_sq = dx * dx + dy * dy
        if seg_sq < 1:
            continue
        t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / seg_sq))
        cx, cy = x0 + t * dx, y0 + t * dy
        dist = math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
        if dist < min_dist:
            min_dist = dist
    return min_dist


# Homing missile configuration
HOMING_MISSILE_SPEED = 20
HOMING_MISSILE_INITIAL_SPEED_RATIO = 0.45  # starts at 45% of max speed
HOMING_MISSILE_RAMP_TIME = 1.2  # seconds to reach full speed
HOMING_MISSILE_DAMAGE = 20
HOMING_MISSILE_LIFETIME = 5.0
HOMING_TRACKING_STRENGTH = 0.15
HOMING_REACQUIRE_RANGE = 400  # proximity range for continuous target re-acquisition

# Respawn invincibility
RESPAWN_INVINCIBILITY = 3.0  # seconds

# Kill feed
KILL_FEED_MAX = 5  # max messages to show
KILL_FEED_DURATION = 5.0  # seconds before message expires

# Walls/Obstacles
WALL_COUNT = 20

# Natural Disaster Configuration
DISASTER_FIRST_MIN = 60.0      # first disaster: min delay after settle
DISASTER_FIRST_MAX = 90.0      # first disaster: max delay after settle
DISASTER_MIN_INTERVAL = 120.0  # ~2 minutes between subsequent disasters
DISASTER_MAX_INTERVAL = 150.0  # ~2 minutes + 10-30s jitter
DISASTER_WARNING_TIME = 5.0    # seconds of warning before disaster hits
DISASTER_MIN_PLAYERS = 2       # need at least 2 players to trigger
DISASTER_SETTLE_TIME = 30.0    # 30s grace period after lobby first fills

# Black Hole
BLACK_HOLE_DURATION = 30.0
BLACK_HOLE_MAX_RADIUS = 350    # visual/kill radius at full size
BLACK_HOLE_PULL_RANGE = 2000   # gravitational pull range (40% of map)
BLACK_HOLE_PULL_STRENGTH = 45  # base pull speed (scaled by distance)
BLACK_HOLE_MASS_FACTOR = 0.7   # smaller players pulled harder (inverse mass)

# Meteor Shower
METEOR_SHOWER_DURATION = 20.0
METEOR_INTERVAL = 0.15         # seconds between meteor strikes
METEOR_DAMAGE = 30             # radius removed on hit
METEOR_BLAST_RADIUS = 120      # area of effect per meteor
METEOR_COUNT_PER_WAVE = 5      # meteors per interval tick

# Fog of War
FOG_DURATION = 15.0
FOG_VISIBILITY_RADIUS = 300    # pixels around player

# Feeding Frenzy
FRENZY_DURATION = 10.0
FRENZY_ORB_COUNT = 1500        # orbs spawned at start

# Supernova
SUPERNOVA_RADIUS = 2200        # blast radius from center (~44% of map width)
SUPERNOVA_PULSE_COUNT = 10     # number of ripple pulses
SUPERNOVA_PULSE_INTERVAL = 1.5 # seconds between each pulse
SUPERNOVA_PULSE_EXPAND_TIME = 1.2  # seconds for each ring to expand
SUPERNOVA_MASS_LOSS_MIN = 0.15 # 15% mass loss per pulse at edge
SUPERNOVA_MASS_LOSS_MAX = 0.20 # 20% mass loss per pulse at edge (up to 2x at epicentre)

# Earthquake
EARTHQUAKE_DURATION = 3.0      # wall transition time

# Derived / internal constants
WALL_COLLISION_ITERATIONS = 3          # stability passes for wall push-out
MOVE_THRESHOLD_SQ = 25                 # 5^2 - minimum distance before moving
KILL_BASE_SCORE = 100                  # base score for consuming a player
KILL_SCORE_RATIO = 0.1                 # fraction of victim's score awarded as bonus
BLACK_HOLE_INITIAL_RADIUS = 5.0        # starting radius before growth
BLACK_HOLE_KILL_RADIUS_FACTOR = 0.6    # fraction of current_radius that kills
BLACK_HOLE_ORB_PULL_STRENGTH = 15      # orb-specific pull strength
BLACK_HOLE_EXIT_ORB_COUNT = 30         # orbs scattered on collapse
METEOR_MARKER_DURATION = 0.5           # seconds to keep impact marker visible

# Disaster and challenge type lists
DISASTER_TYPES = ["black_hole", "meteor_shower", "fog_of_war", "feeding_frenzy", "supernova", "earthquake"]

# Challenge Mode Configuration
TURRET_POSITIONS = [
    (300, 300), (4700, 300), (300, 4700), (4700, 4700),    # corners (start active)
    (2500, 150), (2500, 4850), (150, 2500), (4850, 2500),  # edge midpoints (unlock over time)
]
TURRET_INITIAL_ACTIVE = 4
TURRET_FIRE_INTERVAL_START = 4.0   # seconds between shots at the start
TURRET_FIRE_INTERVAL_MIN = 1.5     # fastest possible fire rate
TURRET_FIRE_INTERVAL_REDUCTION = 0.3  # interval reduction per 30s elapsed
TURRET_ACTIVATE_INTERVAL = 30.0    # new turret unlocks every N seconds
TURRET_MISSILE_COLOR = "#ff3300"
TURRET_MISSILE_LIFETIME = 8.0      # longer than normal - player is far away
TURRET_MISSILE_SPEED = 18
TURRET_MISSILE_TRACKING = 0.12

# Network
MAX_CLIENTS = 50
RATE_LIMIT_WINDOW = 1.0   # seconds
RATE_LIMIT_MAX_MESSAGES = 60
