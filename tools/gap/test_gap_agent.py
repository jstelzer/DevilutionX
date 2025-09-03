#!/usr/bin/env python3
"""
Basic test agent for DevilutionX GAP (Game Agent Protocol)
Connects to the game and demonstrates movement in town.
"""

import json
import socket
import struct
import time
import sys
import os
import argparse

class DevilutionXAgent:
    def __init__(self, socket_path="/tmp/devilutionx-gap.sock", password=None):
        self.socket_path = socket_path
        self.password = password
        self.sock = None
        self.tick_rate = None
        self.player_pos = None
        self.tick_count = 0
        
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
    
    def on_state(self, state):
        """Process game state update."""
        self.tick_count += 1
        
        # Extract player info
        player = state.get('data', {}).get('player', {})
        if player:
            self.player_pos = player.get('pos', [0, 0])
            hp = player.get('hp', 0)
            hp_max = player.get('hp_max', 1)
            in_town = player.get('in_town', False)
            
            if self.tick_count % 10 == 0:  # Print status every 10 state updates
                print(f"[Tick {state.get('tick', 0)}] Player at ({self.player_pos[0]}, {self.player_pos[1]}) | "
                      f"HP: {hp}/{hp_max} | In Town: {in_town}")
        
        # Extract nearby entities
        nearby = state.get('data', {}).get('nearby', {})
        monsters = nearby.get('monsters', [])
        items = nearby.get('items', [])
        
        if monsters and self.tick_count % 20 == 0:
            print(f"  Nearby monsters: {len(monsters)}")
            
        # Simple AI: Move around town in a pattern
        if player.get('in_town', False) and self.player_pos:
            self.move_in_pattern()
    
    def move_in_pattern(self):
        """Simple movement pattern for testing."""
        if not self.player_pos:
            return
            
        x, y = self.player_pos
        
        # Simple square pattern around town center
        target_x, target_y = x, y
        
        # Define waypoints for a square pattern
        waypoints = [
            (48, 48),  # Town center area
            (52, 48),
            (52, 52),
            (48, 52),
        ]
        
        # Find closest waypoint that we're not at
        min_dist = float('inf')
        next_waypoint = None
        
        for wp in waypoints:
            dist = abs(wp[0] - x) + abs(wp[1] - y)
            if dist > 2 and dist < min_dist:  # Not at this waypoint
                min_dist = dist
                next_waypoint = wp
        
        if next_waypoint:
            target_x, target_y = next_waypoint
            
            # Move towards target
            if abs(target_x - x) > abs(target_y - y):
                # Move horizontally first
                if target_x > x:
                    target_x = x + 1
                else:
                    target_x = x - 1
                target_y = y
            else:
                # Move vertically
                target_x = x
                if target_y > y:
                    target_y = y + 1
                else:
                    target_y = y - 1
            
            # Send move intent
            intent = {
                "type": "intent",
                "action": "move",
                "params": {
                    "x": target_x,
                    "y": target_y
                }
            }
            
            print(f"  -> Moving to ({target_x}, {target_y})")
            self.send_message(intent)
    
    def run(self):
        """Main agent loop."""
        if not self.connect():
            return False
            
        if not self.handshake():
            print("Handshake failed!")
            return False
        
        print("\nAgent running! Waiting for game states...")
        print("(Make sure you're in a game, preferably in town)")
        print("Press Ctrl+C to stop\n")
        
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
                    print(f"  Intent acknowledged: {msg.get('intent_action')}")
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
    parser = argparse.ArgumentParser(description="DevilutionX GAP Test Agent")
    parser.add_argument("--password", "-p", type=str, help="Password for multiplayer games")
    parser.add_argument("--socket", "-s", type=str, default="/tmp/devilutionx-gap.sock", 
                       help="Path to GAP socket (default: /tmp/devilutionx-gap.sock)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("DevilutionX GAP Test Agent")
    print("=" * 60)
    print()
    print("This agent will connect to a running DevilutionX game")
    print("compiled with -DENABLE_GAP=ON and move the player around.")
    print()
    print("To use:")
    print("1. Build DevilutionX with: cmake -DENABLE_GAP=ON ..")
    print("2. Start the game and load a character (preferably in town)")
    print("3. Run this agent")
    if args.password:
        print(f"4. Using password: {args.password}")
    print()
    print("=" * 60)
    print()
    
    agent = DevilutionXAgent(socket_path=args.socket, password=args.password)
    success = agent.run()
    
    if success:
        print("\nAgent terminated successfully")
    else:
        print("\nAgent failed to run properly")
        sys.exit(1)

if __name__ == "__main__":
    main()