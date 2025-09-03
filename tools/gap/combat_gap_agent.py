#!/usr/bin/env python3
"""
Combat-aware agent for DevilutionX GAP (Game Agent Protocol)
This agent can engage monsters, kite when low on health, and make tactical decisions.
"""

import json
import socket
import struct
import time
import sys
import os
import argparse
import math

class CombatAgent:
    def __init__(self, socket_path="/tmp/devilutionx-gap.sock", password=None):
        self.socket_path = socket_path
        self.password = password
        self.sock = None
        self.tick_rate = None
        self.player_pos = None
        self.player_hp = 0
        self.player_hp_max = 1
        self.tick_count = 0
        self.last_attack_tick = 0
        self.retreat_mode = False
        self.post_attack_retreat_until = 0  # Tick when to resume attacking
        self.last_attack_target = None  # Remember last target for re-engagement
        
    def connect(self):
        """Connect to the GAP socket."""
        print(f"Connecting to {self.socket_path}...")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        
        # Wait for game to create socket
        max_attempts = 30
        for attempt in range(max_attempts):
            if not os.path.exists(self.socket_path):
                if attempt < max_attempts - 1:
                    print(f"Waiting for game to start GAP... (attempt {attempt + 1}/{max_attempts})")
                    time.sleep(1)
                    continue
                else:
                    print(f"Socket {self.socket_path} not found")
                    return False
            
            try:
                self.sock.connect(self.socket_path)
                print("Connected!")
                return True
            except socket.error as e:
                if attempt < max_attempts - 1:
                    print(f"Connection failed, retrying... (attempt {attempt + 1}/{max_attempts}): {e}")
                    time.sleep(1)
                else:
                    print(f"Failed to connect: {e}")
                    return False
        return False
        
    def read_message(self):
        """Read a message from the socket."""
        try:
            # Read 4-byte length prefix
            length_bytes = self.sock.recv(4)
            if len(length_bytes) != 4:
                print("Connection closed")
                return None
                
            length = struct.unpack('<I', length_bytes)[0]
            
            # Read the JSON payload
            data = b''
            while len(data) < length:
                chunk = self.sock.recv(min(4096, length - len(data)))
                if not chunk:
                    print("Connection closed while reading message")
                    return None
                data += chunk
                
            return json.loads(data.decode('utf-8'))
        except Exception as e:
            print(f"Error reading message: {e}")
            return None
    
    def send_message(self, msg):
        """Send a message to the socket."""
        try:
            data = json.dumps(msg).encode('utf-8')
            length = struct.pack('<I', len(data))
            self.sock.sendall(length + data)
            return True
        except Exception as e:
            print(f"Error sending message: {e}")
            return False
    
    def handshake(self):
        """Perform initial handshake with the game."""
        print("Sending hello...")
        hello_msg = {
            "type": "hello",
            "version": "0.2.0",
            "capabilities": ["move", "attack", "use_item"]
        }
        
        # Add password if provided
        if self.password:
            hello_msg["password"] = self.password
            print(f"  (with password: {self.password})")
        
        if not self.send_message(hello_msg):
            return False
            
        print("Waiting for hello response...")
        response = self.read_message()
        if not response:
            return False
            
        if response.get("type") == "hello":
            print(f"Handshake successful!")
            print(f"  Game version: {response.get('version')}")
            print(f"  Tick rate: {response.get('tick_rate')}")
            print(f"  State divisor: {response.get('state_divisor')}")
            print(f"  Game mode: {response.get('game_mode')}")
            print(f"  Capabilities: {response.get('capabilities')}")
            self.tick_rate = response.get('tick_rate', 30)
            return True
        else:
            print(f"Unexpected response: {response}")
            return False
    
    def find_closest_monster(self, monsters):
        """Find the closest alive monster."""
        closest = None
        min_distance = float('inf')
        
        for monster in monsters:
            is_alive = monster.get('is_alive', True)  # Default to alive if not specified
            is_minion = monster.get('is_minion', False)  # Default to not minion
            
            if is_alive and not is_minion:
                dist = monster.get('distance', float('inf'))
                if dist < min_distance:
                    min_distance = dist
                    closest = monster
        
        return closest
    
    def find_retreat_position(self, monsters):
        """Find a safe position to retreat to."""
        if not self.player_pos:
            return None
            
        px, py = self.player_pos
        
        # Calculate average monster direction
        avg_x = 0
        avg_y = 0
        count = 0
        
        for monster in monsters:
            if monster.get('is_alive') and not monster.get('is_minion'):
                mx, my = monster.get('pos', [px, py])
                avg_x += mx - px
                avg_y += my - py
                count += 1
        
        if count > 0:
            # Move away from average monster position
            avg_x = avg_x / count
            avg_y = avg_y / count
            
            # Normalize and invert direction
            length = math.sqrt(avg_x*avg_x + avg_y*avg_y)
            if length > 0:
                retreat_x = px - int((avg_x / length) * 3)
                retreat_y = py - int((avg_y / length) * 3)
                return (retreat_x, retreat_y)
        
        # Default retreat to town center
        return (48, 48)
    
    def on_state(self, state):
        """Process game state update and make combat decisions."""
        self.tick_count += 1
        current_tick = state.get('tick', 0)
        
        # Extract player info
        player = state.get('data', {}).get('player', {})
        if player:
            self.player_pos = player.get('pos', [0, 0])
            self.player_hp = player.get('hp', 0)
            self.player_hp_max = player.get('hp_max', 1)
            hp_percent = (self.player_hp * 100) // max(self.player_hp_max, 1)
            in_town = player.get('in_town', False)
            
            # Print status every 10 state updates
            if self.tick_count % 10 == 0:
                status = f"[Tick {current_tick}] HP: {self.player_hp}/{self.player_hp_max} ({hp_percent}%) | Pos: ({self.player_pos[0]}, {self.player_pos[1]})"
                if self.retreat_mode:
                    status += " | MODE: RETREATING"
                print(status)
        
        # Extract nearby entities
        nearby = state.get('data', {}).get('nearby', {})
        monsters = nearby.get('monsters', [])
        
        # Check UI state
        ui_state = state.get('data', {}).get('ui_state', {})
        if not ui_state.get('can_act', True):
            return
        
        # Debug: Print monster data occasionally (commented out)
        # if self.tick_count % 50 == 0 and monsters:
        #     print(f"  Debug: Found {len(monsters)} monsters")
        #     if len(monsters) > 0:
        #         first_monster = monsters[0]
        #         print(f"    First monster: {first_monster}")
        
        # Make combat decisions
        hp_percent = (self.player_hp * 100) // max(self.player_hp_max, 1)
        
        # Decision logic
        if hp_percent < 30:
            # Low health - retreat!
            if not self.retreat_mode:
                print("  !!! LOW HEALTH - RETREATING !!!")
                self.retreat_mode = True
            
            retreat_pos = self.find_retreat_position(monsters)
            if retreat_pos:
                self.move_to(retreat_pos[0], retreat_pos[1])
                
        elif hp_percent > 50:
            # Health recovered enough - can fight again
            if self.retreat_mode:
                print("  Health recovered - engaging combat")
                self.retreat_mode = False
        
        if not self.retreat_mode:
            # Check if we're in post-attack retreat phase
            if current_tick < self.post_attack_retreat_until:
                # Simple retreat - move away from all nearby monsters
                if monsters and self.player_pos:
                    px, py = self.player_pos
                    
                    # Find closest monster to retreat from
                    closest_distance = float('inf')
                    closest_monster = None
                    for monster in monsters:
                        dist = monster.get('distance', 999)
                        if dist < closest_distance:
                            closest_distance = dist
                            closest_monster = monster
                    
                    if closest_monster and closest_distance <= 8:
                        # Move away from closest monster
                        mx, my = closest_monster.get('pos', self.player_pos)
                        
                        # Calculate retreat direction
                        dx = px - mx
                        dy = py - my
                        
                        # Move away (at least 1 tile in each direction)
                        if dx == 0 and dy == 0:
                            # If on same tile, just move up
                            retreat_x, retreat_y = px, py - 2
                        else:
                            # Move away from monster
                            retreat_x = px + (2 if dx >= 0 else -2)
                            retreat_y = py + (2 if dy >= 0 else -2)
                        
                        self.move_to(retreat_x, retreat_y)
                        
                        if self.tick_count % 10 == 0:
                            print(f"  -> Retreating from {closest_monster.get('name', 'Unknown')} (distance: {closest_distance})")
                        return
                
                # No monsters to retreat from - just wait
                if self.tick_count % 15 == 0:
                    print(f"  -> Post-attack cooldown ({self.post_attack_retreat_until - current_tick} ticks left)")
                return
            
            # Combat mode - find and attack closest monster
            closest_monster = self.find_closest_monster(monsters)
            
            if closest_monster:
                monster_id = closest_monster.get('id')
                distance = closest_monster.get('distance', 999)
                name = closest_monster.get('name', 'Unknown')
                hp_pct = closest_monster.get('hp_percent', 0)
                
                # Print target info occasionally
                if self.tick_count % 20 == 0:
                    print(f"  Target: {name} (ID:{monster_id}) at distance {distance}, HP: {hp_pct}%")
                
                # Attack if in range, otherwise move closer
                if distance <= 2:  # Melee range
                    # Attack every few ticks to avoid spamming
                    if current_tick - self.last_attack_tick >= 8:  # Slower attack rate
                        self.attack_monster(monster_id)
                        self.last_attack_tick = current_tick
                        self.last_attack_target = monster_id
                        # Retreat for 15 ticks after melee attack
                        self.post_attack_retreat_until = current_tick + 15
                elif distance <= 8:  # Ranged attack distance
                    # Attack with ranged weapon if we have one
                    if current_tick - self.last_attack_tick >= 6:  # Slower attack rate
                        self.attack_monster(monster_id)
                        self.last_attack_tick = current_tick
                        self.last_attack_target = monster_id
                        # Retreat for 10 ticks after ranged attack
                        self.post_attack_retreat_until = current_tick + 10
                else:
                    # Move towards monster
                    mx, my = closest_monster.get('pos', self.player_pos)
                    self.move_towards(mx, my)
            else:
                # No monsters - explore or return to town
                if self.tick_count % 30 == 0:
                    print("  No monsters nearby - exploring...")
                    # Simple exploration pattern
                    px, py = self.player_pos
                    self.move_to(px + 2, py)
    
    def move_to(self, x, y):
        """Send movement intent to specific position."""
        intent = {
            "type": "intent",
            "action": "move",
            "params": {
                "x": x,
                "y": y
            }
        }
        self.send_message(intent)
    
    def move_towards(self, target_x, target_y):
        """Move one step towards target position."""
        if not self.player_pos:
            return
            
        px, py = self.player_pos
        
        # Calculate direction
        dx = target_x - px
        dy = target_y - py
        
        # Move one step in that direction
        if abs(dx) > abs(dy):
            move_x = px + (1 if dx > 0 else -1)
            move_y = py
        else:
            move_x = px
            move_y = py + (1 if dy > 0 else -1)
        
        self.move_to(move_x, move_y)
    
    def attack_monster(self, monster_id):
        """Send attack intent for specific monster."""
        intent = {
            "type": "intent",
            "action": "attack",
            "params": {
                "x": monster_id,
                "y": -1  # Special value to indicate monster ID attack
            }
        }
        print(f"  -> Attacking monster {monster_id}")
        self.send_message(intent)
    
    def run(self):
        """Main agent loop."""
        if not self.connect():
            return False
            
        if not self.handshake():
            print("Handshake failed!")
            return False
        
        print("\nCombat agent running!")
        print("The agent will:")
        print("  - Attack nearby monsters")
        print("  - Retreat when health < 30%")
        print("  - Resume fighting when health > 50%")
        print("  - Kite monsters when possible")
        print("\nPress Ctrl+C to stop\n")
        
        try:
            while True:
                msg = self.read_message()
                if not msg:
                    print("Connection lost!")
                    break
                    
                msg_type = msg.get('type')
                
                if msg_type == 'state':
                    self.on_state(msg)
                elif msg_type == 'ack':
                    # Intent acknowledged
                    pass
                elif msg_type == 'error':
                    print(f"  Error: {msg.get('reason')} - {msg.get('detail')}")
                else:
                    print(f"Unknown message type: {msg_type}")
                    
        except KeyboardInterrupt:
            print("\n\nShutting down agent...")
        finally:
            if self.sock:
                self.sock.close()
        
        return True

def main():
    parser = argparse.ArgumentParser(description="DevilutionX GAP Combat Agent")
    parser.add_argument("--password", "-p", type=str, help="Password for multiplayer games")
    parser.add_argument("--socket", "-s", type=str, default="/tmp/devilutionx-gap.sock", 
                       help="Path to GAP socket (default: /tmp/devilutionx-gap.sock)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("DevilutionX GAP Combat Agent")
    print("=" * 60)
    print()
    print("WARNING: This agent will control your character in combat!")
    print("Make sure you're in a safe area or ready for battle.")
    print()
    
    agent = CombatAgent(socket_path=args.socket, password=args.password)
    success = agent.run()
    
    if success:
        print("\nAgent terminated successfully")
    else:
        print("\nAgent failed to run properly")
        sys.exit(1)

if __name__ == "__main__":
    main()