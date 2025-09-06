#include "gap_network.h"
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

namespace devilution::gap {

// Direct execution for local companion - bypasses network routing
bool ExecuteDirectMove(int player_id, Point target) {
    if (player_id < 0 || player_id >= MAX_PLRS || !Players[player_id].plractive) {
        std::cerr << "GAP: ExecuteDirectMove - Invalid player ID " << player_id << std::endl;
        return false;
    }
    
    Player& player = Players[player_id];
    
    if (player._pmode != PM_STAND) {
        std::cerr << "GAP: ExecuteDirectMove - Player " << player_id << " not in stand mode" << std::endl;
        return false;
    }
    
    if (!InDungeonBounds(target)) {
        std::cerr << "GAP: ExecuteDirectMove - Target out of bounds" << std::endl;
        return false;
    }
    
    if (player.position.tile == target) {
        return false; // Already at target
    }
    
    // Execute movement directly on the companion player
    std::cerr << "GAP: ExecuteDirectMove - Moving player " << player_id 
              << " (" << player._pName << ") from (" 
              << player.position.tile.x << "," << player.position.tile.y 
              << ") to (" << target.x << "," << target.y << ")" << std::endl;
    
    // Use the game's pathfinding system
    MakePlrPath(player, target, true);
    player.destAction = ACTION_WALK;
    
    // For multiplayer, we need to broadcast this action
    if (gbIsMultiplayer) {
        // Create a walk command that appears to come from the companion
        // This is the key fix - we need to ensure other players see the companion move
        // For now, we'll use the existing network command but we need to handle it specially
        
        // We're the host controlling the companion, so we can directly update the companion's state
        // and then sync it to other players
        TCmdLoc cmd;
        cmd.bCmd = CMD_WALKXY;
        cmd.x = target.x;
        cmd.y = target.y;
        
        // Process the command immediately for the companion
        ClrPlrPath(player);
        MakePlrPath(player, target, true);
        player.destAction = ACTION_NONE;
        
        // Send to other players so they see the companion move
        // This requires a special handling in the network layer
        // For now, we'll use the standard approach but mark it as companion command
        multi_send_msg_packet(
            (1 << player_id), // Send to all except the companion itself
            reinterpret_cast<std::byte*>(&cmd),
            sizeof(cmd)
        );
    }
    
    return true;
}

bool ExecuteDirectAttack(int player_id, int monster_id) {
    if (player_id < 0 || player_id >= MAX_PLRS || !Players[player_id].plractive) {
        std::cerr << "GAP: ExecuteDirectAttack - Invalid player ID " << player_id << std::endl;
        return false;
    }
    
    Player& player = Players[player_id];
    
    // Allow attacking while walking or standing
    if (player._pmode != PM_STAND && 
        player._pmode != PM_WALK_NORTHWARDS && 
        player._pmode != PM_WALK_SOUTHWARDS && 
        player._pmode != PM_WALK_SIDEWAYS) {
        std::cerr << "GAP: ExecuteDirectAttack - Player " << player_id << " in mode " << player._pmode << " (not ready to attack)" << std::endl;
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
    
    // Check range
    Point monsterPos = monster.position.tile;
    Point playerPos = player.position.tile;
    int dx = std::abs(monsterPos.x - playerPos.x);
    int dy = std::abs(monsterPos.y - playerPos.y);
    
    // Allow attacking monsters within reasonable range
    if (dx > 15 || dy > 15) {
        std::cerr << "GAP: ExecuteDirectAttack - Monster " << monster_id << " out of range" << std::endl;
        return false;
    }
    
    std::cerr << "GAP: ExecuteDirectAttack - Player " << player_id 
              << " (" << player._pName << ") attacking monster " << monster_id 
              << " at (" << monsterPos.x << "," << monsterPos.y << ")" << std::endl;
    
    // Direct attack execution
    // Set up the attack action - use ATTACKMON for monsters
    player.destAction = ACTION_ATTACKMON;
    player.destParam1 = monster_id;
    
    // Clear any existing path so the attack happens immediately
    ClrPlrPath(player);
    
    // If we're within melee range (adjacent), we can attack immediately
    if (dx <= 1 && dy <= 1) {
        // Calculate direction to monster
        Direction dir = GetDirection(playerPos, monsterPos);
        player._pdir = dir;
        
        // Set attack mode based on weapon type
        if (player.UsesRangedWeapon()) {
            player._pmode = PM_RATTACK;
        } else {
            player._pmode = PM_ATTACK;
        }
        player.AnimInfo.currentFrame = 0;
    } else if (dx <= 10 && dy <= 10) {
        // For ranged attacks or when not adjacent, move closer first
        MakePlrPath(player, monsterPos, false);
    }
    
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