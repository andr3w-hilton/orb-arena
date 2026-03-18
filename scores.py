"""
Orb Arena - Score Persistence
Leaderboard globals, load/save, and record functions for all game modes.
"""

import json
import os

SCORES_PATH = "/data/scores.json"

# Persistent leaderboards (loaded from SCORES_PATH on startup)
missile_magnet_scores: list = []
rally_run_scores: list = []
all_time_scores: list = []
boss_hunt_scores: list = []


def load_scores():
    global missile_magnet_scores, rally_run_scores, all_time_scores, boss_hunt_scores
    try:
        if os.path.exists(SCORES_PATH):
            with open(SCORES_PATH, "r") as f:
                data = json.load(f)
            missile_magnet_scores = data.get("missile_magnet", [])[:10]
            rally_run_scores = data.get("rally_run", [])[:10]
            all_time_scores = data.get("all_time", [])[:10]
            boss_hunt_scores = data.get("boss_hunt", [])[:10]
            print(f"Scores loaded from {SCORES_PATH}")
        else:
            print(f"No scores file at {SCORES_PATH} - starting fresh")
    except Exception as e:
        print(f"Could not load scores: {e}")


def save_scores():
    try:
        os.makedirs(os.path.dirname(SCORES_PATH), exist_ok=True)
        with open(SCORES_PATH, "w") as f:
            json.dump({
                "missile_magnet": missile_magnet_scores,
                "rally_run": rally_run_scores,
                "all_time": all_time_scores,
                "boss_hunt": boss_hunt_scores,
            }, f, indent=2)
    except Exception as e:
        print(f"Could not save scores: {e}")


def record_challenge_score(name: str, time_survived: float) -> int:
    """Record survival time, personal best only, keep top 10 sorted, return 1-indexed rank."""
    global missile_magnet_scores
    existing = next((s for s in missile_magnet_scores if s["name"] == name), None)
    if existing and existing["time"] >= time_survived:
        return next((i + 1 for i, s in enumerate(missile_magnet_scores) if s["name"] == name), len(missile_magnet_scores))
    missile_magnet_scores = [s for s in missile_magnet_scores if s["name"] != name]
    entry = {"name": name, "time": time_survived}
    missile_magnet_scores.append(entry)
    missile_magnet_scores.sort(key=lambda s: s["time"], reverse=True)
    missile_magnet_scores = missile_magnet_scores[:10]
    save_scores()
    for i, s in enumerate(missile_magnet_scores):
        if s is entry:
            return i + 1
    return len(missile_magnet_scores)


def record_rally_score(name: str, best_lap: float) -> int:
    """Record best lap time, personal best only, keep top 10 ascending, return 1-indexed rank."""
    global rally_run_scores
    existing = next((s for s in rally_run_scores if s["name"] == name), None)
    if existing and existing["time"] <= best_lap:
        return next((i + 1 for i, s in enumerate(rally_run_scores) if s["name"] == name), len(rally_run_scores))
    rally_run_scores = [s for s in rally_run_scores if s["name"] != name]
    entry = {"name": name, "time": best_lap}
    rally_run_scores.append(entry)
    rally_run_scores.sort(key=lambda s: s["time"])  # lowest lap time = best
    rally_run_scores = rally_run_scores[:10]
    save_scores()
    for i, s in enumerate(rally_run_scores):
        if s is entry:
            return i + 1
    return len(rally_run_scores)


def record_boss_hunt_score(name: str, time_survived: float) -> int:
    """Record survival time for Hunter Seeker. Personal best only, top 10 descending, return 1-indexed rank."""
    global boss_hunt_scores
    existing = next((s for s in boss_hunt_scores if s["name"] == name), None)
    if existing and existing["time"] >= time_survived:
        return next((i + 1 for i, s in enumerate(boss_hunt_scores) if s["name"] == name), len(boss_hunt_scores))
    boss_hunt_scores = [s for s in boss_hunt_scores if s["name"] != name]
    entry = {"name": name, "time": time_survived}
    boss_hunt_scores.append(entry)
    boss_hunt_scores.sort(key=lambda s: s["time"], reverse=True)
    boss_hunt_scores = boss_hunt_scores[:10]
    save_scores()
    for i, s in enumerate(boss_hunt_scores):
        if s is entry:
            return i + 1
    return len(boss_hunt_scores)


def record_alltime_score(name: str, score: int):
    """Record a multiplayer peak score, keep top 10 descending. Only updates if new score beats personal best."""
    global all_time_scores
    existing = next((s for s in all_time_scores if s["name"] == name), None)
    if existing and existing["score"] >= score:
        return
    all_time_scores = [s for s in all_time_scores if s["name"] != name]
    all_time_scores.append({"name": name, "score": score})
    all_time_scores.sort(key=lambda s: s["score"], reverse=True)
    all_time_scores = all_time_scores[:10]
    save_scores()


# Load persisted scores on startup
load_scores()
