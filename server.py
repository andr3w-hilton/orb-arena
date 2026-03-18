"""
Orb Arena - Multiplayer WebSocket Game Server
A competitive arena game where players control orbs, collect energy, and consume smaller players.
"""

import asyncio
import json
import os
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
import socket
import http.server
import threading

from constants import TICK_RATE, WORLD_WIDTH, WORLD_HEIGHT, RALLY_TRACK_WAYPOINTS
from utils import safe_float, sanitize_name
import scores
from scores import record_challenge_score, record_rally_score, record_boss_hunt_score, record_alltime_score
from game import GameState
from challenges import ChallengeGame, RallyRunGame, BossHuntGame

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
        try:
            game.tick()
        except Exception as e:
            print(f"Error in game tick: {e}")
        current_time = time.time()

        # Build shared state once and serialize to JSON once
        shared_state = game.build_shared_state(current_time)
        # Serialize without 'you' - we'll splice it in per player
        shared_json = json.dumps(shared_state)
        # Remove trailing '}' so we can append ',"you":...}'
        shared_json_prefix = shared_json[:-1] + ',"you":'

        # Send state to each player and spectator
        disconnected = []
        for client_id, websocket in list(game.connections.items()):
            try:
                # Check if this is a spectator or player
                if client_id in game.spectators:
                    # Spectators get state without "you" field
                    message = shared_json
                else:
                    # Players get state with their "you" field
                    player = game.players.get(client_id)
                    if not player:
                        continue
                    you_json = json.dumps(player.to_dict(current_time))
                    message = shared_json_prefix + you_json + '}'

                await asyncio.wait_for(
                    websocket.send(message),
                    timeout=SEND_TIMEOUT
                )
            except asyncio.TimeoutError:
                print(f"Client {client_id} send timeout - dropping connection")
                disconnected.append(client_id)
            except ConnectionClosed:
                disconnected.append(client_id)
            except Exception as e:
                print(f"Error sending to {client_id}: {e}")
                disconnected.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            if client_id in game.spectators:
                game.remove_spectator(client_id)
                print(f"Spectator {client_id} disconnected")
            else:
                game.remove_player(client_id)
                print(f"Player {client_id} disconnected")

        await asyncio.sleep(TICK_RATE)


async def run_challenge_loop(player_id: str, challenge_game: ChallengeGame, websocket):
    """Tick a solo challenge game and send state to the player each frame."""
    try:
        while True:
            try:
                challenge_game.tick()
            except Exception as e:
                print(f"Challenge tick error: {e}")

            current_time = time.time()
            player = challenge_game.players.get(player_id)
            if not player:
                break

            elapsed = challenge_game.get_elapsed()
            shared_state = challenge_game.build_shared_state(current_time)
            shared_state["challenge"] = {
                "time_survived": round(elapsed, 1),
                "wave": challenge_game.get_wave(),
                "active_turrets": [t.id for t in challenge_game.turrets if t.active],
                "fire_interval": round(challenge_game._current_fire_interval, 2),
            }

            if not player.alive:
                time_survived = round(elapsed, 1)
                rank = record_challenge_score(player.name, time_survived)
                shared_state["type"] = "challenge_result"
                shared_state["challenge"]["rank"] = rank
                shared_state["challenge"]["total"] = len(scores.missile_magnet_scores)
                shared_state["challenge"]["top_scores"] = scores.missile_magnet_scores[:5]
                try:
                    await asyncio.wait_for(websocket.send(json.dumps(shared_state)), timeout=SEND_TIMEOUT)
                except Exception:
                    pass
                break

            you_json = json.dumps(player.to_dict(current_time))
            shared_json = json.dumps(shared_state)
            message = shared_json[:-1] + ',"you":' + you_json + '}'
            try:
                await asyncio.wait_for(websocket.send(message), timeout=SEND_TIMEOUT)
            except (asyncio.TimeoutError, ConnectionClosed):
                break
            except Exception as e:
                print(f"Challenge send error: {e}")
                break

            await asyncio.sleep(TICK_RATE)
    except asyncio.CancelledError:
        pass


async def run_rally_loop(player_id: str, rally_game: RallyRunGame, websocket):
    """Tick a solo Nitro Orb rally game and send state to the player each frame."""
    try:
        while True:
            try:
                rally_game.tick()
            except Exception as e:
                print(f"Rally tick error: {e}")

            current_time = time.time()
            player = rally_game.players.get(player_id)
            if not player:
                break

            shared_state = rally_game.build_shared_state(current_time)
            shared_state["challenge"] = rally_game.get_rally_state()

            run_over = not player.alive or rally_game.is_run_complete()
            if run_over:
                rank = None
                # Only post a score if all 3 laps were completed - DNF gets nothing
                if rally_game.is_run_complete() and rally_game.final_time is not None:
                    rank = record_rally_score(player.name, rally_game.final_time)
                shared_state["type"] = "challenge_result"
                shared_state["challenge"]["rank"] = rank
                shared_state["challenge"]["total"] = len(scores.rally_run_scores)
                shared_state["challenge"]["top_scores"] = scores.rally_run_scores[:5]
                shared_state["challenge"]["laps_completed"] = rally_game.lap_count
                shared_state["challenge"]["final_time"] = rally_game.final_time
                shared_state["challenge"]["is_complete"] = rally_game.is_run_complete()
                try:
                    await asyncio.wait_for(websocket.send(json.dumps(shared_state)), timeout=SEND_TIMEOUT)
                except Exception:
                    pass
                break

            you_json = json.dumps(player.to_dict(current_time))
            shared_json = json.dumps(shared_state)
            message = shared_json[:-1] + ',"you":' + you_json + '}'
            try:
                await asyncio.wait_for(websocket.send(message), timeout=SEND_TIMEOUT)
            except (asyncio.TimeoutError, ConnectionClosed):
                break
            except Exception as e:
                print(f"Rally send error: {e}")
                break

            await asyncio.sleep(TICK_RATE)
    except asyncio.CancelledError:
        pass


async def run_boss_loop(player_id: str, boss_game: BossHuntGame, websocket):
    """Tick a solo Hunter Seeker game and send state to the player each frame."""
    try:
        while True:
            try:
                boss_game.tick()
            except Exception as e:
                print(f"Boss hunt tick error: {e}")

            current_time = time.time()
            player = boss_game.players.get(player_id)
            if not player:
                break

            shared_state = boss_game.build_shared_state(current_time)
            shared_state["challenge"] = boss_game.get_boss_hunt_state()

            if not player.alive:
                time_survived = round(boss_game.get_elapsed(), 1)
                rank = record_boss_hunt_score(player.name, time_survived)
                shared_state["type"] = "challenge_result"
                shared_state["challenge"]["rank"] = rank
                shared_state["challenge"]["total"] = len(scores.boss_hunt_scores)
                shared_state["challenge"]["top_scores"] = scores.boss_hunt_scores[:5]
                try:
                    await asyncio.wait_for(websocket.send(json.dumps(shared_state)), timeout=SEND_TIMEOUT)
                except Exception:
                    pass
                break

            you_json = json.dumps(player.to_dict(current_time))
            shared_json = json.dumps(shared_state)
            message = shared_json[:-1] + ',"you":' + you_json + '}'
            try:
                await asyncio.wait_for(websocket.send(message), timeout=SEND_TIMEOUT)
            except (asyncio.TimeoutError, ConnectionClosed):
                break
            except Exception as e:
                print(f"Boss hunt send error: {e}")
                break

            await asyncio.sleep(TICK_RATE)
    except asyncio.CancelledError:
        pass


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
            mode = data.get("mode", "player")  # "player" or "spectate"

            if mode == "spectate":
                # Send welcome message before adding to connections
                # (avoids race with broadcast loop sending state concurrently)
                welcome_data = {
                    "type": "welcome",
                    "player_id": player_id,
                    "mode": "spectate"
                }
                welcome_data.update(game.get_static_data())
                await websocket.send(json.dumps(welcome_data))

                # Now add to game so broadcast loop can send state
                spectator = game.add_spectator(player_id, name, websocket)
                print(f"Spectator {name} ({player_id}) joined!")
            elif mode == "challenge":
                # Solo challenge mode - isolated game instance per player
                challenge_name = data.get("challenge", "missile_magnet")

                if challenge_name == "rally_run":
                    challenge_game = RallyRunGame(player_id)
                    player = challenge_game.add_rally_player(player_id, name, websocket)
                    welcome_data = {
                        "type": "welcome",
                        "player_id": player_id,
                        "mode": "challenge",
                        "challenge": "rally_run",
                        "player": player.to_dict(time.time()),
                        "track_waypoints": list(RALLY_TRACK_WAYPOINTS),
                        "total_checkpoints": challenge_game.total_checkpoints,
                        "turrets": [t.to_dict() for t in challenge_game.decorative_turrets],
                    }
                    welcome_data.update(challenge_game.get_static_data())
                    await websocket.send(json.dumps(welcome_data))
                    print(f"Challenge player {name} ({player_id}) started Nitro Orb!")
                    tick_task = asyncio.create_task(run_rally_loop(player_id, challenge_game, websocket))
                elif challenge_name == "boss_hunt":
                    challenge_game = BossHuntGame(player_id)
                    player = challenge_game.add_player(player_id, name, websocket)
                    welcome_data = {
                        "type": "welcome",
                        "player_id": player_id,
                        "mode": "challenge",
                        "challenge": "boss_hunt",
                        "player": player.to_dict(time.time()),
                        "boss": challenge_game.boss.to_dict(time.time()),
                        "top_scores": scores.boss_hunt_scores[:5],
                    }
                    welcome_data.update(challenge_game.get_static_data())
                    await websocket.send(json.dumps(welcome_data))
                    print(f"Challenge player {name} ({player_id}) started Hunter Seeker!")
                    tick_task = asyncio.create_task(run_boss_loop(player_id, challenge_game, websocket))
                else:
                    challenge_game = ChallengeGame(player_id)
                    player = challenge_game.add_player(player_id, name, websocket)
                    welcome_data = {
                        "type": "welcome",
                        "player_id": player_id,
                        "mode": "challenge",
                        "challenge": challenge_name,
                        "player": player.to_dict(time.time()),
                        "turrets": [t.to_dict() for t in challenge_game.turrets],
                    }
                    welcome_data.update(challenge_game.get_static_data())
                    await websocket.send(json.dumps(welcome_data))
                    print(f"Challenge player {name} ({player_id}) started {challenge_name}!")
                    tick_task = asyncio.create_task(run_challenge_loop(player_id, challenge_game, websocket))
                try:
                    async for message in websocket:
                        now = time.time()
                        if now - window_start >= RATE_LIMIT_WINDOW:
                            msg_count = 0
                            window_start = now
                        msg_count += 1
                        if msg_count > RATE_LIMIT_MAX_MSGS:
                            continue
                        try:
                            data = json.loads(message)
                            msg_type = data.get("type")
                            if msg_type == "move":
                                challenge_game.update_player_target(
                                    player_id,
                                    safe_float(data.get("x", 0)),
                                    safe_float(data.get("y", 0))
                                )
                            elif msg_type == "boost":
                                challenge_game.activate_boost(player_id)
                            elif msg_type == "shoot":
                                challenge_game.shoot(
                                    player_id,
                                    safe_float(data.get("x", 0)),
                                    safe_float(data.get("y", 0)),
                                    wormhole=bool(data.get("wormhole", False))
                                )
                            elif msg_type == "place_mine":
                                challenge_game.place_mine(player_id)
                        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
                            pass
                finally:
                    tick_task.cancel()

            else:
                # Add as player
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

            # Handle messages from this client (multiplayer only - challenge has its own loop above)
            if mode not in ("challenge",):
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
                                safe_float(data.get("y", 0)),
                                wormhole=bool(data.get("wormhole", False))
                            )

                        elif msg_type == "place_mine":
                            game.place_mine(player_id)

                        elif msg_type == "respawn":
                            game.respawn_player(player_id)

                        elif msg_type == "test_disasters":
                            game.disaster_manager.start_test_cycle(time.time())

                        elif msg_type == "ping":
                            await websocket.send(json.dumps({"type": "pong", "t": data.get("t", 0)}))

                    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
                        pass  # Silently drop malformed messages

    except ConnectionClosed:
        pass
    finally:
        active_connections -= 1
        if player_id:
            # Remove player or spectator (challenge players are not in game.players)
            if player_id in game.spectators:
                game.remove_spectator(player_id)
                print(f"Spectator {player_id} left")
            elif player_id in game.players:
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
        # Normalize path and only allow index.html (plus API endpoints)
        path = self.path.split("?")[0].split("#")[0]  # strip query/fragment
        if path == "/api/challenge/scores":
            self._serve_challenge_scores()
            return
        if path == "/api/rally/scores":
            self._serve_rally_scores()
            return
        if path == "/api/alltime/scores":
            self._serve_alltime_scores()
            return
        if path == "/api/boss/scores":
            self._serve_boss_scores()
            return
        if path == "/api/status":
            self._serve_status()
            return
        if path.startswith("/static/js/") and path.endswith(".js"):
            file_path = os.path.join(os.path.dirname(__file__), path.lstrip("/"))
            if os.path.isfile(file_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
            return
        if path not in ALLOWED_HTTP_FILES:
            self.send_error(404, "Not Found")
            return
        # Always serve index.html
        self.path = "/index.html"
        super().do_GET()

    def _serve_challenge_scores(self):
        data = json.dumps(scores.missile_magnet_scores[:10]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_rally_scores(self):
        data = json.dumps(scores.rally_run_scores[:10]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_boss_scores(self):
        data = json.dumps(scores.boss_hunt_scores[:10]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_alltime_scores(self):
        data = json.dumps(scores.all_time_scores[:10]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_status(self):
        data = json.dumps({"players": len(game.players)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

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
