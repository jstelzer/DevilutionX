#include "gap_network.h"
#include <cstdint>
#include "gap_core.h"
#include "../player.h"
#include "../monster.h"
#include "../cursor.h"
#include "../control.h"
#include "../levels/gendung.h"
#include "../nthread.h"
#include "../objects.h"
#include "../items.h"
#include "../inv.h"
#include "../multi.h"
#include "../engine/direction.hpp"
#include <iostream>
#include <cmath>

namespace devilution::gap {

// Direct execution for local companion - bypasses network routing
bool ExecuteDirectMove(int player_id, Point target) {
    if (player_id < 0 || player_id >= MAX_PLRS || !Players[player_id].plractive) {
        std::cerr << "GAP: ExecuteDirectMove - Invalid player ID " << player_id << std::endl;
        return false;
    }
    
    Player& player = Players[player_id];

    // Validate player position data is initialized
    Point playerPos = player.position.tile;
    if (!InDungeonBounds(playerPos)) {
        std::cerr << "GAP: ExecuteDirectMove - Player " << player_id
                  << " has invalid position (" << playerPos.x << "," << playerPos.y
                  << ") - player not fully initialized yet" << std::endl;
        return false;
    }

    // Cannot move if dead
    if (player._pmode == PM_DEATH || player._pHitPoints == 0) {
        return false; // Silent failure for death state
    }

    // Allow movement while standing or already walking (update destination mid-movement)
    // This prevents command spam rejection when movement takes longer than think interval
    if (player._pmode != PM_STAND &&
        player._pmode != PM_WALK_NORTHWARDS &&
        player._pmode != PM_WALK_SOUTHWARDS &&
        player._pmode != PM_WALK_SIDEWAYS) {
        std::cerr << "GAP: ExecuteDirectMove - Player " << player_id << " in mode " << player._pmode << " (cannot move)" << std::endl;
        return false;
    }
    
    if (!InDungeonBounds(target)) {
        std::cerr << "GAP: ExecuteDirectMove - Target out of bounds" << std::endl;
        return false;
    }

    if (playerPos == target) {
        return false; // Already at target
    }

    // Execute movement directly on the companion player
    std::cerr << "GAP: ExecuteDirectMove - Moving player " << player_id
              << " (" << player._pName << ") from ("
              << playerPos.x << "," << playerPos.y
              << ") to (" << target.x << "," << target.y << ")" << std::endl;

    // Verify AnimInfo is initialized before setting walk action
    std::cerr << "GAP: ExecuteDirectMove - Checking AnimInfo: numberOfFrames="
              << static_cast<int>(player.AnimInfo.numberOfFrames)
              << " _pWFrames=" << static_cast<int>(player._pWFrames) << std::endl;

    if (player.AnimInfo.numberOfFrames == 0 || player._pWFrames == 0) {
        // AnimInfo not initialized - this causes FPE crashes in animation calculations
        // This happens when companion spawns in town before graphics are loaded
        // Block movement until companion enters dungeon (triggers graphics load)
        std::cerr << "GAP: ExecuteDirectMove - ERROR: AnimInfo not initialized! Blocking movement to prevent FPE crash." << std::endl;
        return false;
    }

    // Use the game's pathfinding system
    std::cerr << "GAP: ExecuteDirectMove - About to call MakePlrPath" << std::endl;
    MakePlrPath(player, target, true);
    std::cerr << "GAP: ExecuteDirectMove - MakePlrPath done, setting destAction" << std::endl;
    player.destAction = ACTION_WALK;
    std::cerr << "GAP: ExecuteDirectMove - destAction set, checking multiplayer" << std::endl;
    
    // For multiplayer, we need to broadcast this action
    if (gbIsMultiplayer) {
        std::cerr << "GAP: ExecuteDirectMove - In multiplayer block" << std::endl;
        // Create a walk command that appears to come from the companion
        // This is the key fix - we need to ensure other players see the companion move
        // For now, we'll use the existing network command but we need to handle it specially

        // We're the host controlling the companion, so we can directly update the companion's state
        // and then sync it to other players
        TCmdLoc cmd;
        cmd.bCmd = CMD_WALKXY;
        cmd.x = target.x;
        cmd.y = target.y;

        std::cerr << "GAP: ExecuteDirectMove - About to ClrPlrPath" << std::endl;
        // Process the command immediately for the companion
        ClrPlrPath(player);
        std::cerr << "GAP: ExecuteDirectMove - About to second MakePlrPath" << std::endl;
        MakePlrPath(player, target, true);
        std::cerr << "GAP: ExecuteDirectMove - About to set ACTION_NONE" << std::endl;
        player.destAction = ACTION_NONE;

        std::cerr << "GAP: ExecuteDirectMove - About to multi_send_msg_packet" << std::endl;
        // Send to other players so they see the companion move
        // This requires a special handling in the network layer
        // For now, we'll use the standard approach but mark it as companion command
        multi_send_msg_packet(
            (1 << player_id), // Send to all except the companion itself
            reinterpret_cast<std::byte*>(&cmd),
            sizeof(cmd)
        );
        std::cerr << "GAP: ExecuteDirectMove - multi_send_msg_packet done" << std::endl;
    }

    std::cerr << "GAP: ExecuteDirectMove - About to return true" << std::endl;
    return true;
}

bool ExecuteDirectAttack(int player_id, int monster_id) {
    if (player_id < 0 || player_id >= MAX_PLRS || !Players[player_id].plractive) {
        std::cerr << "GAP: ExecuteDirectAttack - Invalid player ID " << player_id << std::endl;
        return false;
    }
    
    Player& player = Players[player_id];

    // Validate player position data is initialized
    Point playerPos = player.position.tile;
    if (!InDungeonBounds(playerPos)) {
        std::cerr << "GAP: ExecuteDirectAttack - Player " << player_id
                  << " has invalid position (" << playerPos.x << "," << playerPos.y
                  << ") - player not fully initialized yet" << std::endl;
        return false;
    }

    // Cannot attack if dead
    if (player._pmode == PM_DEATH || player._pHitPoints == 0) {
        return false; // Silent failure for death state
    }

    // Allow attacking in most modes - real players can queue attacks
    // Only block during critical transitions
    if (player._pmode == PM_QUIT || player._pmode == PM_NEWLVL) {
        std::cerr << "GAP: ExecuteDirectAttack - Player " << player_id << " in mode " << player._pmode << " (transition)" << std::endl;
        return false;
    }
    
    if (monster_id < 0 || static_cast<size_t>(monster_id) >= MaxMonsters) {
        std::cerr << "GAP: ExecuteDirectAttack - Invalid monster ID " << monster_id << std::endl;
        return false;
    }
    
    const auto& monster = Monsters[monster_id];
    
    if (monster.hitPoints <= 0) {
        std::cerr << "GAP: ExecuteDirectAttack - Monster " << monster_id << " already dead" << std::endl;
        return false;
    }
    
    // Get monster position for direction/distance calculations
    Point monsterPos = monster.position.tile;
    int dx = std::abs(monsterPos.x - playerPos.x);
    int dy = std::abs(monsterPos.y - playerPos.y);
    int maxDist = std::max(dx, dy);

    // SHIFT-KEY BEHAVIOR: For ranged weapons, refuse to attack if out of range
    // This prevents auto-pathing and gives the agent explicit control over positioning
    // Just like a human player holding shift to avoid accidental movement
    if (player.UsesRangedWeapon()) {
        // Typical bow range is 1-15 tiles (game engine limit)
        if (maxDist > 15) {
            std::cerr << "GAP: ExecuteDirectAttack - Monster " << monster_id
                      << " out of bow range (dist=" << maxDist << "), refusing attack (shift-key behavior)" << std::endl;
            return false; // Agent must reposition first
        }
    } else {
        // Melee range - must be adjacent
        if (maxDist > 1) {
            std::cerr << "GAP: ExecuteDirectAttack - Monster " << monster_id
                      << " out of melee range (dist=" << maxDist << "), refusing attack" << std::endl;
            return false; // Agent must move closer first
        }
    }

    std::cerr << "GAP: ExecuteDirectAttack - Player " << player_id
              << " (" << player._pName << ") attacking monster " << monster_id
              << " at (" << monsterPos.x << "," << monsterPos.y << ") dist=" << maxDist << std::endl;

    // Clear any existing path - we're attacking from current position (shift-key behavior)
    ClrPlrPath(player);

    // Set player direction to face monster
    Direction dir = GetDirection(playerPos, monsterPos);
    player._pdir = dir;

    // Call attack functions directly - this is true shift-key behavior!
    // These functions start the attack animation WITHOUT creating a path
    if (player.UsesRangedWeapon()) {
        StartRangeAttack(player, dir, monsterPos.x, monsterPos.y, true);
        std::cerr << "GAP: Called StartRangeAttack (stand-and-shoot)" << std::endl;
    } else {
        StartAttack(player, dir, true);
        std::cerr << "GAP: Called StartAttack (melee)" << std::endl;
    }

    std::cerr << "GAP: Attack started directly (no destAction, no movement)" << std::endl;
    
    // Sync to network if multiplayer
    if (gbIsMultiplayer) {
        // Send attack command for other players to see
        TCmdParam1 cmd;
        cmd.bCmd = player.UsesRangedWeapon() ? CMD_RATTACKID : CMD_ATTACKID;
        cmd.wParam1 = SDL_SwapLE16(static_cast<uint16_t>(monster_id));
        
        multi_send_msg_packet(
            (1 << player_id), // Send to all except the companion
            reinterpret_cast<std::byte*>(&cmd),
            sizeof(cmd)
        );
    }
    
    return true;
}

bool ExecutePositionAttack(int player_id, int target_x, int target_y) {
    // Find monster at or near the target position and attack it
    Point target(target_x, target_y);

    if (!InDungeonBounds(target)) {
        std::cerr << "GAP: ExecutePositionAttack - Target position out of bounds" << std::endl;
        return false;
    }

    // Find monster at or near target position (within 2 tiles)
    int targetMonsterId = -1;
    int minDistance = 3; // Allow up to 2 tiles away

    for (size_t i = 0; i < ActiveMonsterCount; i++) {
        const auto& monster = Monsters[ActiveMonsters[i]];
        if (monster.hitPoints > 0) {
            int dx = std::abs(monster.position.tile.x - target.x);
            int dy = std::abs(monster.position.tile.y - target.y);
            int dist = std::max(dx, dy); // Chebyshev distance

            if (dist < minDistance) {
                minDistance = dist;
                targetMonsterId = ActiveMonsters[i];
            }
        }
    }

    if (targetMonsterId >= 0) {
        const auto& foundMonster = Monsters[targetMonsterId];
        std::cerr << "GAP: ExecutePositionAttack (" << target_x << "," << target_y
                  << ") → Found monster " << targetMonsterId << " at ("
                  << foundMonster.position.tile.x << "," << foundMonster.position.tile.y
                  << ") search_dist=" << minDistance << std::endl;
        return ExecuteDirectAttack(player_id, targetMonsterId);
    } else {
        std::cerr << "GAP: ExecutePositionAttack failed - no monster near ("
                  << target_x << "," << target_y << ")" << std::endl;
        return false;
    }
}

bool ExecuteDirectInteract(int player_id, Point position) {
    if (player_id < 0 || player_id >= MAX_PLRS || !Players[player_id].plractive) {
        return false;
    }
    
    Player& player = Players[player_id];
    
    if (player._pmode != PM_STAND) {
        return false;
    }
    
    if (!InDungeonBounds(position)) {
        return false;
    }
    
    // Find object at position
    for (int i = 0; i < ActiveObjectCount; i++) {
        const auto& obj = Objects[ActiveObjects[i]];
        if (obj.position == position) {
            // Check if object is within range (adjacent)
            Point playerPos = player.position.tile;
            int dx = std::abs(position.x - playerPos.x);
            int dy = std::abs(position.y - playerPos.y);
            
            if (dx <= 1 && dy <= 1) {
                // Direct object interaction
                player.destAction = ACTION_OPERATE;
                player.destParam1 = ActiveObjects[i];
                
                // Sync to network if multiplayer
                if (gbIsMultiplayer) {
                    TCmdLoc cmd;
                    cmd.bCmd = CMD_OPOBJXY;
                    cmd.x = position.x;
                    cmd.y = position.y;
                    
                    multi_send_msg_packet(
                        (1 << player_id),
                        reinterpret_cast<std::byte*>(&cmd),
                        sizeof(cmd)
                    );
                }
                
                return true;
            }
        }
    }
    
    return false;
}

bool ExecuteDirectPickup(int player_id, int item_id) {
    if (player_id < 0 || player_id >= MAX_PLRS || !Players[player_id].plractive) {
        std::cerr << "GAP: ExecuteDirectPickup - Invalid player ID " << player_id << std::endl;
        return false;
    }

    Player& player = Players[player_id];

    std::cerr << "GAP: ExecuteDirectPickup - Player " << player_id
              << " (" << player._pName << ") attempting to pick up item " << item_id << std::endl;

    // Allow pickup in most modes (like real player)
    if (player._pmode == PM_DEATH || player._pmode == PM_QUIT || player._pmode == PM_NEWLVL) {
        std::cerr << "GAP: ExecuteDirectPickup - Invalid player mode (" << player._pmode << ")" << std::endl;
        return false;
    }

    // Find the item in the active items list
    for (uint8_t i = 0; i < ActiveItemCount; i++) {
        if (ActiveItems[i] == item_id) {
            const auto& item = Items[item_id];

            std::cerr << "GAP: ExecuteDirectPickup - Found item " << item_id
                      << " (" << item._iIName << ") at (" << item.position.x << "," << item.position.y << ")" << std::endl;

            // Check if item is within reasonable range (adjacent)
            Point itemPos = item.position;
            Point playerPos = player.position.tile;
            int dx = std::abs(itemPos.x - playerPos.x);
            int dy = std::abs(itemPos.y - playerPos.y);

            std::cerr << "GAP: ExecuteDirectPickup - Player at (" << playerPos.x << "," << playerPos.y
                      << "), distance dx=" << dx << " dy=" << dy << std::endl;

            if (dx <= 1 && dy <= 1) {
                std::cerr << "GAP: ExecuteDirectPickup - Item within range, calling AutoGetItem" << std::endl;

                // Direct pickup with auto-placement - avoids cursor pollution
                // AutoGetItem tries belt first (potions), then inventory, only cursor as fallback
                AutoGetItem(player, &Items[item_id], item_id);

                // Sync to network if multiplayer
                if (gbIsMultiplayer) {
                    // Notify other players about the pickup
                    TCmdGItem cmd;
                    cmd.bCmd = CMD_GETITEM;
                    cmd.bPnum = player_id;  // Important: Use companion's ID, not MyPlayerId
                    cmd.x = itemPos.x;
                    cmd.y = itemPos.y;
                    PrepareItemForNetwork(item, cmd.item);  // Use .item not .def (they're a union)

                    multi_send_msg_packet(
                        (1 << player_id),  // Send to all except the companion
                        reinterpret_cast<std::byte*>(&cmd),
                        sizeof(cmd)
                    );
                }

                return true;
            } else {
                std::cerr << "GAP: ExecuteDirectPickup - Item too far away (need to be adjacent)" << std::endl;
            }
        }
    }

    std::cerr << "GAP: ExecuteDirectPickup - Item " << item_id << " not found in ActiveItems" << std::endl;
    return false;
}

// Network wrapper functions that route commands to the correct implementation
void NetSendCmdLocForPlayer(int actual_player_id, bool bHiPri, _cmd_id bCmd, Point position) {
    // Check if we're controlling a companion locally
    if (actual_player_id != MyPlayerId && Players[actual_player_id].plractive) {
        // This is a companion we're controlling locally
        std::cerr << "GAP: NetSendCmdLocForPlayer - Routing command " << static_cast<int>(bCmd) 
                  << " for companion " << actual_player_id << std::endl;
        
        // Use direct execution for local companion
        switch (bCmd) {
            case CMD_WALKXY:
                ExecuteDirectMove(actual_player_id, position);
                break;
            case CMD_SATTACKXY:
            case CMD_RATTACKXY:
                // For position-based attacks, we'd need to find the target at that position
                // For now, this is not fully implemented
                std::cerr << "GAP: Position-based attack not yet implemented for companion" << std::endl;
                break;
            case CMD_OPOBJXY:
                ExecuteDirectInteract(actual_player_id, position);
                break;
            default:
                std::cerr << "GAP: Unhandled command type " << static_cast<int>(bCmd) << std::endl;
                break;
        }
    } else {
        // Normal command for local player
        NetSendCmdLoc(MyPlayerId, bHiPri, bCmd, position);
    }
}

void NetSendCmdParam1ForPlayer(int actual_player_id, bool bHiPri, _cmd_id bCmd, uint16_t wParam1) {
    // Check if we're controlling a companion locally
    if (actual_player_id != MyPlayerId && Players[actual_player_id].plractive) {
        // This is a companion we're controlling locally
        std::cerr << "GAP: NetSendCmdParam1ForPlayer - Routing command " << static_cast<int>(bCmd)
                  << " for companion " << actual_player_id << std::endl;
        
        // Use direct execution for local companion
        switch (bCmd) {
            case CMD_ATTACKID:
            case CMD_RATTACKID:
                ExecuteDirectAttack(actual_player_id, wParam1);
                break;
            default:
                std::cerr << "GAP: Unhandled param1 command type " << static_cast<int>(bCmd) << std::endl;
                break;
        }
    } else {
        // Normal command for local player
        NetSendCmdParam1(bHiPri, bCmd, wParam1);
    }
}

} // namespace devilution::gap
