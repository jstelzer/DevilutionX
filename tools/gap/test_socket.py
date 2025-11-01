#!/usr/bin/env python3
"""
Simple socket test - connects to game and echoes state

This tests the C++ → Python communication without needing Ollama
"""

import socket
import struct
import sys
from dsl_parser import parse_dsl_state

SOCKET_PATH = "/tmp/devilutionx-gap.sock"

def test_socket():
    """Connect to GAP socket and echo states"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(SOCKET_PATH)
        sock.settimeout(1.0)
        print(f"✅ Connected to {SOCKET_PATH}")

        state_count = 0
        max_states = 10  # Test with 10 state updates

        while state_count < max_states:
            try:
                # Read length header
                length_bytes = sock.recv(4)
                if len(length_bytes) < 4:
                    continue

                length = struct.unpack('<I', length_bytes)[0]

                # Read message data
                data = b""
                while len(data) < length:
                    chunk = sock.recv(length - len(data))
                    if not chunk:
                        break
                    data += chunk

                dsl_line = data.decode('utf-8')

                # Parse and display
                state = parse_dsl_state(dsl_line)

                if state["tick"] > 0:
                    state_count += 1
                    me_x, me_y, hp_pct, mp_pct = state["me"]
                    print(f"[{state_count}] Tick={state['tick']} Floor={state['floor']} "
                          f"Pos=({me_x},{me_y}) HP={hp_pct}% "
                          f"Mobs={len(state['mobs'])} Loot={len(state['loot'])}")

                    # Send a command every 3 states to avoid overwhelming chat buffer
                    if state_count % 3 == 0:
                        command = f"SAY Test {state_count // 3}"
                        command_bytes = command.encode('utf-8')
                        length = struct.pack('<I', len(command_bytes))
                        sock.sendall(length + command_bytes)
                        print(f"  → Sent: {command}")

            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error: {e}")
                break

        sock.close()
        print(f"\n✅ Successfully received and parsed {state_count} states!")
        return True

    except FileNotFoundError:
        print(f"❌ Socket not found: {SOCKET_PATH}")
        print("   Start the game first:")
        print("   ./build/devilutionx --companion-save multi_1.sv --companion-slot 1")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("GAP DSL Socket Test")
    print("=" * 60)
    print("This tests C++ → Python communication without needing Ollama")
    print()

    success = test_socket()
    sys.exit(0 if success else 1)
