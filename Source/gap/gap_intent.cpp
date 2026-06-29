#include "gap_intent.h"
#include <cstdint>
#include "gap_json.h"
#include "gap_core.h"
#include "gap_network.h"
#include "gap_stores.h"
#ifdef ENABLE_GAP
#include "gap_chat.h"
#include "../seat/seat.h"
#include "../seat/companion_seat.h"
#endif
#include "../player.h"
#include "../monster.h"
#include "../cursor.h"
#include "../control.h"
#include "../engine/point.hpp"
#include "../levels/gendung.h"
#include "../nthread.h"
#include "../msg.h"
#include "../items.h"
#include "../stores.h"  // TakePlrsMoney (gold-pile-aware spend)
#include "../objects.h"
#include "../spells.h"
#include "../inv.h"
#include "../controls/plrctrls.h"
#include "../engine/backbuffer_state.hpp"
#include <iostream>
#include <sstream>

namespace devilution::gap {

namespace {
// Get the controlled player for GAP operations
// One client, one player: GAP always drives this client's own MyPlayer. (These
// thin aliases remain only to avoid churning ~50 call sites; the sidecar
// slot-lookup they used to do is gone.)
Player* GetControlledPlayer() {
    return MyPlayer;
}

int GetControlledPlayerId() {
    return MyPlayerId;
}
} // namespace

void GapIntentProcessor::QueueIntent(const JsonParser& intent_msg) {
    if (intent_queue_.size() >= 3) {
        std::cerr << "GAP: Intent queue full, dropping intent" << std::endl;
        return;
    }
    
    Intent intent;
    
    // Check for compact format first ({"m":[x,y]}, {"a":id}, {"p":id}, etc.)
    if (intent_msg.HasKey("m")) {
        // Compact move: {"m":[x,y]}
        intent.action = "move";
        std::string move_str = intent_msg.GetObjectString("m");
        // Parse array [x,y] from string like "[50,55]"
        if (move_str.size() >= 5 && move_str[0] == '[' && move_str.back() == ']') {
            std::string coords = move_str.substr(1, move_str.size() - 2); // Remove [ ]
            size_t comma_pos = coords.find(',');
            if (comma_pos != std::string::npos) {
                intent.param_x = std::stoi(coords.substr(0, comma_pos));
                intent.param_y = std::stoi(coords.substr(comma_pos + 1));
            }
        }
    } else if (intent_msg.HasKey("a")) {
        // Compact attack: {"a":monster_id} or {"a":[x,y]}
        intent.action = "attack";
        std::string attack_str = intent_msg.GetObjectString("a");
        if (attack_str.size() > 0 && attack_str[0] == '[') {
            // Position attack: {"a":[x,y]}
            if (attack_str.size() >= 5 && attack_str.back() == ']') {
                std::string coords = attack_str.substr(1, attack_str.size() - 2); // Remove [ ]
                size_t comma_pos = coords.find(',');
                if (comma_pos != std::string::npos) {
                    intent.param_x = std::stoi(coords.substr(0, comma_pos));
                    intent.param_y = std::stoi(coords.substr(comma_pos + 1));
                }
            }
        } else {
            // Monster attack: {"a":42}
            intent.param_x = intent_msg.GetInt("a");
            intent.param_y = -1;
        }
    } else if (intent_msg.HasKey("p")) {
        // Compact pickup: {"p":item_id}
        intent.action = "pickup";
        intent.param_id = intent_msg.GetInt("p");
    } else if (intent_msg.HasKey("h")) {
        // Compact use potion: {"h":slot}
        intent.action = "use_potion";
        intent.param_slot = intent_msg.GetInt("h");
        intent.param_kind = "hp"; // Default to health potion
    } else if (intent_msg.HasKey("c")) {
        // Compact chat: {"c":"message"}
        intent.action = "chat";
        intent.param_kind = intent_msg.GetString("c");
    } else {
        // Standard format: {"type":"intent","action":"move","params":{"x":50,"y":55}}
        intent.action = intent_msg.GetString("action");
        
        std::string params_str = intent_msg.GetObjectString("params");
        JsonParser params(params_str);
        intent.param_x = params.GetInt("x");
        intent.param_y = params.GetInt("y");
        intent.param_id = params.GetInt("id");
        intent.param_slot = params.GetInt("slot");
        intent.param_kind = params.GetString("kind");
    }
    
    intent.target_tick = intent_msg.GetInt("target_tick");

    intent_queue_.push(intent);
}

void GapIntentProcessor::QueueDSLIntent(const std::string& dsl_line) {
    if (intent_queue_.size() >= 3) {
        std::cerr << "GAP: Intent queue full, dropping DSL intent" << std::endl;
        return;
    }

    // Parse DSL command: "MV x y", "AT id", "PK id", etc.
    std::istringstream iss(dsl_line);
    std::string cmd;
    iss >> cmd;

    if (cmd.empty()) {
        return;  // Empty line, ignore
    }

    Intent intent;
    intent.param_x = 0;
    intent.param_y = 0;
    intent.param_id = 0;
    intent.param_slot = -1;
    intent.param_inv_slot = -1;
    intent.target_tick = 0;

    if (cmd == "MV") {
        // MV x y
        intent.action = "move";
        iss >> intent.param_x >> intent.param_y;

    } else if (cmd == "AT") {
        // AT id OR AT x y
        intent.action = "attack";

        // Try to read first parameter
        if (iss >> intent.param_x) {
            // Check if there's a second parameter (position attack)
            if (iss >> intent.param_y) {
                // Two parameters: AT x y (position-based attack for ranged)
                intent.param_id = 0;  // No monster ID
            } else {
                // One parameter: AT id (monster ID attack)
                intent.param_id = intent.param_x;
                intent.param_x = 0;
                intent.param_y = -1;  // Marker for "convert ID to position"
            }
        }

    } else if (cmd == "PK") {
        // PK id
        intent.action = "pickup";
        iss >> intent.param_id;

    } else if (cmd == "IN") {
        // IN id
        intent.action = "interact";
        iss >> intent.param_id;

    } else if (cmd == "CS") {
        // CS slot - Cast scroll from belt slot (0-7)
        // Example: CS 2  (use scroll in belt slot 2)
        intent.action = "cast";
        iss >> intent.param_slot;

    } else if (cmd == "CAST") {
        // CAST spell_id x y - Cast memorized spell at target location
        // Example: CAST 2 45 30  (cast Firebolt at 45,30)
        // Example: CAST 3 50 25  (cast Fireball at 50,25)
        intent.action = "cast_spell";
        iss >> intent.param_id >> intent.param_x >> intent.param_y;

    } else if (cmd == "US") {
        // US slot
        intent.action = "use_potion";
        iss >> intent.param_slot;
        intent.param_kind = "hp";  // Default to health potion

    } else if (cmd == "UI") {
        // UI inv_slot — use/drink an item directly from inventory (right-click).
        // Lets her quaff an HP potion from the pack when the belt is full/empty.
        intent.action = "use_inv_item";
        iss >> intent.param_inv_slot;

    } else if (cmd == "SAY") {
        // SAY text...
        intent.action = "chat";
        // Get rest of line as chat message
        std::getline(iss, intent.param_kind);
        // Trim leading space
        if (!intent.param_kind.empty() && intent.param_kind[0] == ' ') {
            intent.param_kind = intent.param_kind.substr(1);
        }

    } else if (cmd == "BUY") {
        // BUY npc_code item_index
        // Example: BUY hl 5  (buy item #5 from healer)
        std::string npc_code;
        iss >> npc_code >> intent.param_id;
        intent.action = "buy";
        intent.param_kind = npc_code;  // "sm", "hl", "wt", "pg"

    } else if (cmd == "SELL") {
        // SELL inv_slot
        // Example: SELL 7  (sell inventory slot 7)
        intent.action = "sell";
        iss >> intent.param_slot;

    } else if (cmd == "ID") {
        // ID inv_slot
        // Example: ID 2  (identify inventory slot 2)
        intent.action = "identify";
        iss >> intent.param_slot;

    } else if (cmd == "ADDSTAT") {
        // ADDSTAT stat_name
        // Example: ADDSTAT STR, ADDSTAT DEX, ADDSTAT MAG, ADDSTAT VIT
        std::string stat_name;
        iss >> stat_name;
        intent.action = "addstat";
        intent.param_kind = stat_name;  // "STR", "DEX", "MAG", "VIT"

    } else if (cmd == "BELT") {
        // BELT inv_slot belt_slot
        // Example: BELT 12 3  (move item from inventory slot 12 to belt slot 3)
        intent.action = "belt_refill";
        iss >> intent.param_inv_slot >> intent.param_slot;

    } else if (cmd == "REPAIR") {
        // REPAIR body_slot_index
        // Example: REPAIR 4  (repair left hand weapon, body slot 4)
        // Body slots: 0=head, 4=hand_left, 5=hand_right, 6=chest
        intent.action = "repair_item";
        iss >> intent.param_slot;

    } else if (cmd == "EQUIP") {
        // EQUIP inv_slot
        // Example: EQUIP 3  (equip the item in inventory slot 3, swapping out the
        // currently-worn item in that body slot)
        intent.action = "equip_item";
        iss >> intent.param_inv_slot;

    } else if (cmd == "DROP") {
        // DROP inv_slot OR DROP GOLD amount
        // Example: DROP 5  (drop item from inventory slot 5)
        // Example: DROP GOLD 1000  (drop 1000 gold)
        std::string param1;
        iss >> param1;
        if (param1 == "GOLD") {
            intent.action = "drop_gold";
            iss >> intent.param_x;  // Use param_x to store gold amount
        } else {
            intent.action = "drop_item";
            intent.param_inv_slot = std::stoi(param1);
        }

    } else {
        std::cerr << "GAP DSL: Unknown command: " << cmd << std::endl;
        return;
    }

    intent_queue_.push(intent);
    std::cout << "GAP DSL: Queued " << intent.action << " command" << std::endl;
}

void GapIntentProcessor::ProcessPendingIntents(uint32_t current_tick) {
    while (!intent_queue_.empty()) {
        const Intent& intent = intent_queue_.front();
        
        if (intent.target_tick > 0 && intent.target_tick > current_tick) {
            break;
        }
        
        if (ExecuteIntent(intent)) {
            std::cout << "GAP: Executed intent: " << intent.action << std::endl;
        } else {
            std::cerr << "GAP: Failed to execute intent: " << intent.action << std::endl;
        }
        
        intent_queue_.pop();
    }
}

bool GapIntentProcessor::ExecuteIntent(const Intent& intent) {
    if (intent.action == "move") {
        return ExecuteMove(intent.param_x, intent.param_y);
    } else if (intent.action == "attack") {
        // Check if we have a monster ID (DSL format: AT id) or position (JSON format)
        std::cerr << "GAP: ExecuteIntent attack - param_id=" << intent.param_id
                  << " param_x=" << intent.param_x << " param_y=" << intent.param_y << std::endl;
        if (intent.param_id > 0) {
            // Monster ID attack - pass as (monster_id, -1)
            std::cerr << "GAP: Using monster ID attack path" << std::endl;
            return ExecuteAttack(intent.param_id, -1);
        } else {
            // Position-based attack - pass as (x, y)
            std::cerr << "GAP: Using position-based attack path" << std::endl;
            return ExecuteAttack(intent.param_x, intent.param_y);
        }
    } else if (intent.action == "cast") {
        return ExecuteCast(intent.param_slot, intent.param_x, intent.param_y);
    } else if (intent.action == "cast_spell") {
        return ExecuteCastSpell(intent.param_id, intent.param_x, intent.param_y);
    } else if (intent.action == "use_potion") {
        return ExecuteUsePotion(intent.param_kind, intent.param_slot);
    } else if (intent.action == "use_inv_item") {
        return ExecuteUseInvItem(intent.param_inv_slot);
    } else if (intent.action == "pickup") {
        return ExecutePickup(intent.param_id);
    } else if (intent.action == "equip_item") {
        return ExecuteEquip(intent.param_inv_slot);
    } else if (intent.action == "interact") {
        return ExecuteInteract(intent.param_id);
    } else if (intent.action == "path") {
        return ExecutePath(intent.param_x, intent.param_y);
    } else if (intent.action == "explore") {
        return ExecuteExplore();
    } else if (intent.action == "chat") {
        return ExecuteChat(intent.param_kind);
    } else if (intent.action == "buy") {
        return ExecuteBuy(intent.param_kind, intent.param_id);
    } else if (intent.action == "sell") {
        return ExecuteSell(intent.param_slot);
    } else if (intent.action == "identify") {
        return ExecuteIdentify(intent.param_slot);
    } else if (intent.action == "addstat") {
        return ExecuteAddStat(intent.param_kind);
    } else if (intent.action == "belt_refill") {
        return ExecuteBeltRefill(intent.param_inv_slot, intent.param_slot);
    } else if (intent.action == "repair_item") {
        return ExecuteRepairItem(intent.param_slot);
    } else if (intent.action == "drop_item") {
        return ExecuteDropItem(intent.param_inv_slot);
    } else if (intent.action == "drop_gold") {
        return ExecuteDropGold(intent.param_x);
    }

    std::cerr << "GAP: Unknown intent action: " << intent.action << std::endl;
    return false;
}

bool GapIntentProcessor::ExecuteMove(int x, int y) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP: ExecuteMove failed - GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }
    
    int controlled_id = GetControlledPlayerId();
    std::cerr << "GAP: ExecuteMove - Controlling player " << controlled_id 
              << " (name: " << player->_pName << ")" 
              << " at pos (" << static_cast<int>(player->position.tile.x) << ","
              << static_cast<int>(player->position.tile.y) << ")"
              << " to target (" << x << "," << y << ")" << std::endl;
    
    if (player->_pmode != PM_STAND) {
        std::cerr << "GAP: ExecuteMove failed - player mode is " << player->_pmode << " (not PM_STAND)" << std::endl;
        return false;
    }
    
    Point target(x, y);
    
    if (!InDungeonBounds(target)) {
        std::cerr << "GAP: ExecuteMove failed - target (" << x << "," << y << ") out of dungeon bounds" << std::endl;
        return false;
    }
    
    if (player->position.tile == target) {
        std::cerr << "GAP: ExecuteMove failed - already at target position" << std::endl;
        return false; // Already at target
    }
    
    // Use the game's pathfinding system like the normal controls do
    MakePlrPath(*player, target, true);
    player->destAction = ACTION_WALK;
    
    // Handle both single-player and multiplayer modes
    // In single-player mode with companion, we need direct execution
    // In multiplayer, use network isolation for correct routing
    if (controlled_id != MyPlayerId) {
        // Controlling a companion - use direct execution
        std::cerr << "GAP: Using direct execution for companion " << controlled_id << std::endl;
        return ExecuteDirectMove(controlled_id, target);
    } else if (gbIsMultiplayer) {
        // Controlling main player in multiplayer
        std::cerr << "GAP: Sending network command CMD_WALKXY for player " << controlled_id << std::endl;
        NetSendCmdLocForPlayer(controlled_id, true, CMD_WALKXY, target);
    }
    
    std::cerr << "GAP: ExecuteMove succeeded - path set for player " << controlled_id << std::endl;
    return true;
}

bool GapIntentProcessor::ExecuteAttack(int x, int y) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        return false;
    }

    // Check if player is already attacking - prevent spam
    if (player->_pmode == PM_ATTACK || player->_pmode == PM_RATTACK) {
        // Already attacking, don't spam attacks
        return false;
    }

    // Allow attacking while walking or standing
    if (player->_pmode != PM_STAND &&
        player->_pmode != PM_WALK_NORTHWARDS &&
        player->_pmode != PM_WALK_SOUTHWARDS &&
        player->_pmode != PM_WALK_SIDEWAYS) {
        std::cerr << "GAP: ExecuteAttack - Player not in attackable mode (mode=" << player->_pmode << ")" << std::endl;
        return false;
    }
    
    // Check if we have a monster ID passed as x (when y is -1)
    // This allows attacking specific monsters by ID
    if (y == -1) {
        int monsterId = x;
        if (monsterId >= 0 && static_cast<size_t>(monsterId) < MaxMonsters) {
            const auto& monster = Monsters[monsterId];
            
            // Check if monster is alive
            if (monster.hitPoints <= 0) {
                return false;
            }
            
            // Check if monster is in range (reasonable attack range)
            Point monsterPos = monster.position.tile;
            Point playerPos = player->position.tile;
            int dx = std::abs(monsterPos.x - playerPos.x);
            int dy = std::abs(monsterPos.y - playerPos.y);
            
            // Allow attacking monsters within 15 tiles
            if (dx > 15 || dy > 15) {
                return false;
            }
            
            // Use appropriate attack command based on weapon type
            int controlled_id = GetControlledPlayerId();
            
            // Direct execution for companions
            if (controlled_id != MyPlayerId) {
                std::cerr << "GAP: Using direct attack for companion " << controlled_id << std::endl;
                return ExecuteDirectAttack(controlled_id, monsterId);
            } else if (gbIsMultiplayer) {
                // Network command for main player in multiplayer
                if (player->UsesRangedWeapon()) {
                    NetSendCmdParam1ForPlayer(controlled_id, true, CMD_RATTACKID, monsterId);
                } else {
                    NetSendCmdParam1ForPlayer(controlled_id, true, CMD_ATTACKID, monsterId);
                }
            } else {
                // Single player main character - use standard commands
                if (player->UsesRangedWeapon()) {
                    NetSendCmdParam1(true, CMD_RATTACKID, monsterId);
                } else {
                    NetSendCmdParam1(true, CMD_ATTACKID, monsterId);
                }
            }
            
            return true;
        }
    } else {
        // Attack a position (x, y) - useful for ranged attacks without pathfinding
        Point target(x, y);

        if (!InDungeonBounds(target)) {
            return false;
        }

        int controlled_id = GetControlledPlayerId();

        // For companions, we need to find the monster at/near this position and attack by ID
        // Network position commands don't work reliably for companions
        if (controlled_id != MyPlayerId) {
            // Find monster at or near target position (within 2 tiles)
            // Monsters move between ticks, so we need fuzzy matching
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
                std::cerr << "GAP: Position attack (" << x << "," << y << ") → Found monster "
                          << targetMonsterId << " at (" << static_cast<int>(foundMonster.position.tile.x) << ","
                          << static_cast<int>(foundMonster.position.tile.y) << ") search_dist=" << minDistance << std::endl;
                return ExecuteDirectAttack(controlled_id, targetMonsterId);
            } else {
                std::cerr << "GAP: Position attack failed - no monster near (" << x << "," << y << ")" << std::endl;
                return false;
            }
        } else {
            // Main player - use network command
            if (player->UsesRangedWeapon()) {
                NetSendCmdLocForPlayer(controlled_id, true, CMD_RATTACKXY, target);
            } else {
                NetSendCmdLocForPlayer(controlled_id, true, CMD_SATTACKXY, target);
            }
            return true;
        }
    }
    
    return false;
}

bool GapIntentProcessor::ExecuteCast(int slot, int x, int y) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP: ExecuteCast failed - no controlled player" << std::endl;
        return false;
    }

    // Allow scroll use in more states than standing (similar to potion use)
    if (player->_pmode == PM_DEATH || player->_pmode == PM_QUIT || player->_pmode == PM_NEWLVL) {
        std::cerr << "GAP: ExecuteCast failed - invalid player mode (" << player->_pmode << ")" << std::endl;
        return false;
    }

    // Validate belt slot
    if (slot < 0 || slot >= MaxBeltItems) {
        std::cerr << "GAP: ExecuteCast failed - invalid belt slot " << slot << std::endl;
        return false;
    }

    // Check if slot has a scroll
    const Item& beltItem = player->SpdList[slot];
    if (beltItem.isEmpty()) {
        std::cerr << "GAP: ExecuteCast failed - belt slot " << slot << " is empty" << std::endl;
        return false;
    }

    // Verify it's a scroll
    if (beltItem._iMiscId != IMISC_SCROLL && beltItem._iMiscId != IMISC_SCROLLT) {
        std::cerr << "GAP: ExecuteCast failed - belt slot " << slot << " is not a scroll" << std::endl;
        return false;
    }

    std::cout << "GAP: Using scroll " << beltItem._iIName
              << " (spell=" << static_cast<int>(beltItem._iSpell) << ")"
              << " from belt slot " << slot << std::endl;

    // Use the belt item (INVITEM_BELT_FIRST = 47, so slot 0 = inv index 47)
    int invIndex = INVITEM_BELT_FIRST + slot;

    // UseInvItem handles scroll consumption and spell casting
    bool success = UseInvItem(*player, invIndex);

    if (success) {
        std::cout << "GAP: Successfully used scroll from slot " << slot << std::endl;
    } else {
        std::cerr << "GAP: UseInvItem returned FALSE for scroll at slot " << slot << std::endl;
    }

    return success;
}

bool GapIntentProcessor::ExecuteCastSpell(int spell_id, int x, int y) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP: ExecuteCastSpell failed - no controlled player" << std::endl;
        return false;
    }

    // Validate player state
    if (player->_pmode == PM_DEATH || player->_pmode == PM_QUIT || player->_pmode == PM_NEWLVL) {
        std::cerr << "GAP: ExecuteCastSpell failed - invalid player mode (" << player->_pmode << ")" << std::endl;
        return false;
    }

    // Convert spell_id to SpellID enum
    SpellID spellID = static_cast<SpellID>(spell_id);

    // Validate spell ID
    if (!IsValidSpell(spellID)) {
        std::cerr << "GAP: ExecuteCastSpell failed - invalid spell ID " << spell_id << std::endl;
        return false;
    }

    // Determine the spell SOURCE the way the engine does: a spell may come from
    // memory (costs mana), the equipped staff/items (charges, no mana), a scroll,
    // or be a class ability. CAST must use the matching SpellType or the engine
    // rejects it as "doesn't know spell" — a staff's spell lives in _pISpells,
    // NOT _pMemSpells (this is why the Sorc's staff ChargedBolt kept failing).
    // Pick the spell SOURCE the way a real player would, but DON'T fail a low-mana
    // caster who can cast the same spell for free off a charged staff. A spell can
    // live in memory (costs mana, scales with spell level), on the equipped
    // staff/item (charges, no mana), on a scroll, or be a class ability. GetManaAmount
    // already returns fixed-point (it `ma <<= 6` internally), so compare _pMana directly.
    const uint64_t mask = GetSpellBitmask(spellID);
    const bool memHas = (player->_pMemSpells & mask) != 0;
    const bool staffHas = (player->_pISpells & mask) != 0;  // equipped staff/item charges
    const bool canAffordMana = memHas && player->_pMana >= GetManaAmount(*player, spellID);

    SpellType castType;
    if (canAffordMana) {
        castType = SpellType::Spell;    // memorized and affordable — cast from mana
    } else if (staffHas) {
        // Not memorized, OR mana too low: fall back to the staff's charges. This is
        // the whole point of carrying a charged staff — keep blasting when the blue
        // bar is empty. Before this fallback the engine preferred the memorized
        // version and a low-mana Sorc's CAST failed "not enough mana" with 42 staff
        // charges in hand, so he just stopped casting.
        castType = SpellType::Charges;
    } else if (memHas) {
        std::cerr << "GAP: ExecuteCastSpell failed - not enough mana for spell " << spell_id << std::endl;
        return false;
    } else if (player->_pScrlSpells & mask) {
        castType = SpellType::Scroll;   // a carried scroll
    } else if (player->_pAblSpells & mask) {
        castType = SpellType::Skill;    // class ability (Repair/Disarm/Recharge)
    } else {
        std::cerr << "GAP: ExecuteCastSpell failed - player can't cast spell " << spell_id << std::endl;
        return false;
    }

    std::cout << "GAP: ExecuteCastSpell - spell_id=" << spell_id
              << " type=" << static_cast<int>(castType)
              << " target=(" << x << "," << y << ")" << std::endl;

    // Ready the spell (mirrors selecting it on the panel).
    player->_pRSpell = spellID;
    player->_pRSplType = castType;

    // CMD_SPELLXY is a THREE-param command (spellID, spellType, spellFrom); the
    // engine computes the spell level itself on receipt. spellFrom=0 means
    // memory / equipped staff / ability. The previous Param4 form shoved the
    // level into the spellFrom slot, which IsValidSpellFrom rejected — so every
    // cast silently failed InitNewSpell.
    const int spellFrom = 0;
    NetSendCmdLocParam3(true, CMD_SPELLXY, Point{x, y},
                        static_cast<int8_t>(spellID),
                        static_cast<uint8_t>(castType),
                        spellFrom);

    std::cout << "GAP: Successfully queued spell " << spell_id << " (type "
              << static_cast<int>(castType) << ") at (" << x << "," << y << ")" << std::endl;
    return true;
}

bool GapIntentProcessor::ExecutePickup(int item_id) {
    int player_id = GetControlledPlayerId();

    // Use direct pickup execution for companions (bypasses network routing bug)
    return gap::ExecuteDirectPickup(player_id, item_id);
}

bool GapIntentProcessor::ExecuteUsePotion(const std::string& kind, int slot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP: ExecuteUsePotion failed - no controlled player" << std::endl;
        return false;
    }

    std::cout << "GAP: ExecuteUsePotion - Player " << player->getId()
              << " (" << player->_pName << ") attempting to use slot " << slot
              << ", HP=" << (player->_pHitPoints >> 6) << "/" << (player->_pMaxHP >> 6)
              << ", mode=" << player->_pmode << std::endl;

    // Allow potion use in most modes (like real player)
    // Block only during death/quit/newlvl transitions
    if (player->_pmode == PM_DEATH || player->_pmode == PM_QUIT || player->_pmode == PM_NEWLVL) {
        std::cerr << "GAP: ExecuteUsePotion failed - invalid player mode (" << player->_pmode << ")" << std::endl;
        return false;
    }

    // Validate belt slot
    if (slot < 0 || slot >= MaxBeltItems) {
        std::cerr << "GAP: Invalid belt slot " << slot << " (must be 0-" << (MaxBeltItems-1) << ")" << std::endl;
        return false;
    }

    // Check if slot has an item
    const Item& beltItem = player->SpdList[slot];
    std::cout << "GAP: Belt slot " << slot << " - isEmpty=" << beltItem.isEmpty()
              << ", itype=" << static_cast<int>(beltItem._itype)
              << ", name='" << (beltItem.isEmpty() ? "empty" : beltItem._iIName) << "'" << std::endl;

    if (beltItem.isEmpty()) {
        std::cerr << "GAP: Belt slot " << slot << " is empty" << std::endl;
        return false;
    }

    // Dump full belt state for debugging
    std::cout << "GAP: Full belt state for player " << player->getId() << ": ";
    for (int i = 0; i < MaxBeltItems; i++) {
        const Item& item = player->SpdList[i];
        if (item.isEmpty()) {
            std::cout << "[" << i << ":empty] ";
        } else {
            std::cout << "[" << i << ":" << item._iIName << "] ";
        }
    }
    std::cout << std::endl;

    // Use the belt item (INVITEM_BELT_FIRST = 47, so slot 0 = inv index 47)
    int invIndex = INVITEM_BELT_FIRST + slot;

    std::cout << "GAP: Using belt item at slot " << slot
              << " (inv index " << invIndex << ")"
              << " - " << beltItem._iIName << std::endl;

    // Call the game's UseInvItem function
    // This handles all the logic: consuming the item, applying effects, etc.
    bool success = UseInvItem(*player, invIndex);

    if (success) {
        std::cout << "GAP: Successfully used belt item at slot " << slot
                  << ", new HP=" << (player->_pHitPoints >> 6) << "/" << (player->_pMaxHP >> 6)
                  << std::endl;
    } else {
        std::cerr << "GAP: UseInvItem returned FALSE for slot " << slot << std::endl;
    }

    return success;
}

bool GapIntentProcessor::ExecuteUseInvItem(int inv_slot) {
    // Use/drink an item straight from the inventory grid (the right-click move) —
    // e.g. quaff an HP potion from the pack when the belt is full or empty. The
    // DSL inv slot is the InvList index; UseInvItem wants INVITEM_INV_FIRST + idx.
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP: ExecuteUseInvItem failed - no controlled player" << std::endl;
        return false;
    }
    if (player->_pmode == PM_DEATH || player->_pmode == PM_QUIT || player->_pmode == PM_NEWLVL) {
        std::cerr << "GAP: ExecuteUseInvItem failed - invalid player mode (" << player->_pmode << ")" << std::endl;
        return false;
    }
    if (inv_slot < 0 || inv_slot >= player->_pNumInv) {
        std::cerr << "GAP: ExecuteUseInvItem failed - invalid inv slot " << inv_slot
                  << " (have " << player->_pNumInv << ")" << std::endl;
        return false;
    }
    const Item& item = player->InvList[inv_slot];
    if (item.isEmpty()) {
        std::cerr << "GAP: ExecuteUseInvItem failed - inv slot " << inv_slot << " empty" << std::endl;
        return false;
    }

    std::cout << "GAP: ExecuteUseInvItem - drinking/using '" << item._iIName
              << "' from inv slot " << inv_slot << " (HP=" << (player->_pHitPoints >> 6)
              << "/" << (player->_pMaxHP >> 6) << ")" << std::endl;

    bool success = UseInvItem(*player, INVITEM_INV_FIRST + inv_slot);
    if (!success)
        std::cerr << "GAP: UseInvItem returned FALSE for inv slot " << inv_slot << std::endl;
    return success;
}

bool GapIntentProcessor::ExecuteInteract(int object_id) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        return false;
    }
    
    if (player->_pmode != PM_STAND) {
        return false;
    }
    
    // Find the object in the active objects list
    for (int i = 0; i < ActiveObjectCount; i++) {
        if (ActiveObjects[i] == object_id) {
            const auto& obj = Objects[object_id];
            
            // Check if object is within range (adjacent)
            Point objPos = obj.position;
            Point playerPos = player->position.tile;
            int dx = std::abs(objPos.x - playerPos.x);
            int dy = std::abs(objPos.y - playerPos.y);
            
            if (dx <= 1 && dy <= 1) {
                // Use existing object interaction with correct player routing
                int controlled_id = GetControlledPlayerId();
                NetSendCmdLocForPlayer(controlled_id, true, CMD_OPOBJXY, objPos);
                return true;
            }
        }
    }
    
    return false;
}

bool GapIntentProcessor::ExecutePath(int x, int y) {
    // Path intent is similar to move but implies longer distance pathfinding
    // For now, delegate to ExecuteMove - pathfinding improvements will come later
    return ExecuteMove(x, y);
}

bool GapIntentProcessor::ExecuteExplore() {
    // Explore intent means "move to next unexplored area"
    // For now, return false - this will be implemented with frontier detection
    std::cerr << "GAP: Exploration not yet implemented - needs frontier detection" << std::endl;
    return false;
}

bool GapIntentProcessor::ExecuteChat(const std::string& message) {
    // Send a chat message from the AI agent
#ifdef ENABLE_GAP
    // The network chat buffer is MAX_SEND_STR_LEN (80); SendAIResponse adds the
    // "[GAP AI] " prefix (9) and chunking may add "..." markers (up to 6). Keep
    // each chunk small enough that the final broadcast string isn't truncated.
    const size_t MAX_CHAT_LENGTH = MAX_SEND_STR_LEN - 16;  // ~64 chars
    
    if (message.length() <= MAX_CHAT_LENGTH) {
        // Message fits in one line
        GAPChatHandler::getInstance().SendAIResponse(message);
    } else {
        // Break long message into chunks
        size_t pos = 0;
        int fragment = 1;
        
        while (pos < message.length()) {
            // Find a good break point (space) near the limit
            size_t chunkEnd = pos + MAX_CHAT_LENGTH;
            if (chunkEnd > message.length()) {
                chunkEnd = message.length();
            } else {
                // Look for last space before limit to avoid breaking words
                size_t lastSpace = message.rfind(' ', chunkEnd);
                if (lastSpace != std::string::npos && lastSpace > pos) {
                    chunkEnd = lastSpace;
                }
            }
            
            std::string chunk = message.substr(pos, chunkEnd - pos);
            
            // Add continuation marker for multi-part messages
            if (fragment > 1 || chunkEnd < message.length()) {
                if (fragment == 1) {
                    chunk += "...";
                } else if (chunkEnd < message.length()) {
                    chunk = "..." + chunk + "...";
                } else {
                    chunk = "..." + chunk;
                }
            }
            
            GAPChatHandler::getInstance().SendAIResponse(chunk);
            
            pos = chunkEnd;
            // Skip the space we broke on
            if (pos < message.length() && message[pos] == ' ') {
                pos++;
            }
            fragment++;
        }
    }
    return true;
#else
    std::cerr << "GAP: Chat intent requires ENABLE_GAP flag" << std::endl;
    return false;
#endif
}

#ifdef ENABLE_GAP
void GapIntentProcessor::ProcessPendingIntentsViaSeat(uint32_t current_tick) {
    // NOTE: Chat intents are handled globally at the GAP protocol level and never reach here
    while (!intent_queue_.empty()) {
        const Intent& gap_intent = intent_queue_.front();

        if (gap_intent.target_tick > 0 && gap_intent.target_tick > current_tick) {
            break; // Wait for target tick
        }

        // One client, one player: every intent executes directly on MyPlayer.
        // The sidecar Seat/CompanionSeat bridge is gone — in the true-MP client
        // it always fell through to direct execution anyway.
        if (!ExecuteIntent(gap_intent)) {
            std::cerr << "GAP: Failed to execute " << gap_intent.action << " intent" << std::endl;
        }

        intent_queue_.pop();
    }
}

devilution::Intent GapIntentProcessor::ConvertToSeatIntent(const Intent& gap_intent, uint64_t tick) {
    // Convert GAP intent format to Seat intent format
    if (gap_intent.action == "move") {
        return devilution::Intent(devilution::Intent::Type::Move, tick, 
                                 gap_intent.param_x, gap_intent.param_y);
    } else if (gap_intent.action == "attack") {
        return devilution::Intent(devilution::Intent::Type::Attack, tick,
                                 gap_intent.param_x, gap_intent.param_y, gap_intent.param_id);
    } else if (gap_intent.action == "pickup") {
        // Pickup is Interact with item_id in param1
        return devilution::Intent(devilution::Intent::Type::Interact, tick,
                                 gap_intent.param_x, gap_intent.param_y, gap_intent.param_id);
    } else if (gap_intent.action == "use_potion") {
        return devilution::Intent(devilution::Intent::Type::UseItem, tick,
                                 0, 0, gap_intent.param_slot);
    } else if (gap_intent.action == "cast") {
        return devilution::Intent(devilution::Intent::Type::Cast, tick,
                                 gap_intent.param_x, gap_intent.param_y, gap_intent.param_slot);
    } else if (gap_intent.action == "cast_spell") {
        // Cast memorized spell - use param_id for spell ID
        return devilution::Intent(devilution::Intent::Type::Cast, tick,
                                 gap_intent.param_x, gap_intent.param_y, gap_intent.param_id);
    } else if (gap_intent.action == "interact") {
        return devilution::Intent(devilution::Intent::Type::Interact, tick,
                                 gap_intent.param_x, gap_intent.param_y);
    } else if (gap_intent.action == "chat") {
        return devilution::Intent(devilution::Intent::Type::Chat, tick,
                                 gap_intent.param_kind);
    } else {
        // Default to move for unknown actions
        std::cerr << "GAP: Unknown action '" << gap_intent.action << "', defaulting to move" << std::endl;
        return devilution::Intent(devilution::Intent::Type::Move, tick,
                                 gap_intent.param_x, gap_intent.param_y);
    }
}

bool GapIntentProcessor::ExecuteBuy(const std::string& npcCode, int itemIndex) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Store: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    // Map NPC code to _talker_id
    _talker_id npcType;
    if (npcCode == "sm") {
        npcType = TOWN_SMITH;
    } else if (npcCode == "hl") {
        npcType = TOWN_HEALER;
    } else if (npcCode == "wt") {
        npcType = TOWN_WITCH;
    } else if (npcCode == "pg") {
        npcType = TOWN_PEGBOY;
    } else {
        std::cerr << "GAP Store: Unknown NPC code: " << npcCode << std::endl;
        return false;
    }

    return CompanionBuyItem(*player, npcType, itemIndex);
}

bool GapIntentProcessor::ExecuteSell(int invSlot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Store: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    return CompanionSellItem(*player, invSlot);
}

bool GapIntentProcessor::ExecuteIdentify(int invSlot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Store: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    return CompanionIdentifyItem(*player, invSlot);
}

bool GapIntentProcessor::ExecuteAddStat(const std::string& statName) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Stats: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    // Check if player has stat points available
    if (player->_pStatPts <= 0) {
        std::cerr << "GAP Stats: No stat points available" << std::endl;
        return false;
    }

    // Apply stat increase
    if (statName == "STR") {
        ModifyPlrStr(*player, 1);
        std::cout << "GAP Stats: Added 1 point to STR" << std::endl;
    } else if (statName == "DEX") {
        ModifyPlrDex(*player, 1);
        std::cout << "GAP Stats: Added 1 point to DEX" << std::endl;
    } else if (statName == "MAG") {
        ModifyPlrMag(*player, 1);
        std::cout << "GAP Stats: Added 1 point to MAG" << std::endl;
    } else if (statName == "VIT") {
        ModifyPlrVit(*player, 1);
        std::cout << "GAP Stats: Added 1 point to VIT" << std::endl;
    } else {
        std::cerr << "GAP Stats: Unknown stat name: " << statName << std::endl;
        return false;
    }

    // Deduct stat point
    player->_pStatPts--;

    std::cout << "GAP Stats: Stat points remaining: " << player->_pStatPts << std::endl;

    return true;
}

bool GapIntentProcessor::ExecuteBeltRefill(int invSlot, int beltSlot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Belt: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    // Validate inventory slot
    if (invSlot < 0 || invSlot >= player->_pNumInv) {
        std::cerr << "GAP Belt: Invalid inventory slot: " << invSlot << std::endl;
        return false;
    }

    // Validate belt slot
    if (beltSlot < 0 || beltSlot >= MaxBeltItems) {
        std::cerr << "GAP Belt: Invalid belt slot: " << beltSlot << std::endl;
        return false;
    }

    // Check if inventory slot has a consumable item
    const Item& invItem = player->InvList[invSlot];
    if (invItem.isEmpty()) {
        std::cerr << "GAP Belt: Inventory slot " << invSlot << " is empty" << std::endl;
        return false;
    }

    // Check if item can be placed on belt (1x1 consumables only)
    if (!CanBePlacedOnBelt(*player, invItem)) {
        std::cerr << "GAP Belt: Item in slot " << invSlot << " cannot be placed on belt" << std::endl;
        return false;
    }

    const bool sync = (GetControlledPlayerId() == MyPlayerId);

    // If the target belt slot is occupied, lift its current item back into the
    // pack so a higher-priority consumable (a health potion) can take its place —
    // the belt-swap the agent asks for when the belt is clogged with utility
    // scrolls and the spare potions are stranded in the pack. Mirrors EQUIP's
    // swap: AutoPlaceItemInInventory restocks the pack and (for MyPlayer)
    // broadcasts CMD_CHANGEINVITEMS so the other client stays in sync. Removing
    // the inventory potion frees a 1x1 cell, so the 1x1 belt item always has room.
    Item displaced;
    const bool swapping = !player->SpdList[beltSlot].isEmpty();
    if (swapping) {
        displaced = player->SpdList[beltSlot];
    }

    // Move the inventory item onto the belt.
    player->SpdList[beltSlot] = invItem;
    player->RemoveInvItem(invSlot, false);  // self-syncs the inv removal; no scroll calc yet
    if (swapping) {
        AutoPlaceItemInInventory(*player, displaced, sync);  // stash the bumped item back
    }
    player->CalcScrolls();  // Recalculate scrolls after belt update
    RedrawComponent(PanelDrawComponent::Belt);

    if (sync) {
        NetSendCmdChBeltItem(false, beltSlot);
    }

    std::cout << "GAP Belt: " << (swapping ? "Swapped" : "Moved") << " inv slot " << invSlot
              << " onto belt slot " << beltSlot
              << (swapping ? " (bumped item back to pack)" : "") << std::endl;

    return true;
}

bool GapIntentProcessor::ExecuteRepairItem(int bodySlot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Repair: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    // Map body slot index to INVLOC enum
    // Python sends: 0=head, 4=hand_left, 5=hand_right, 6=chest
    // C++ uses: INVLOC_HEAD=0, INVLOC_HAND_LEFT=4, INVLOC_HAND_RIGHT=5, INVLOC_CHEST=3
    inv_body_loc slot;
    if (bodySlot == 0) {
        slot = INVLOC_HEAD;
    } else if (bodySlot == 4) {
        slot = INVLOC_HAND_LEFT;
    } else if (bodySlot == 5) {
        slot = INVLOC_HAND_RIGHT;
    } else if (bodySlot == 6 || bodySlot == 3) {
        slot = INVLOC_CHEST;
    } else {
        std::cerr << "GAP Repair: Invalid body slot: " << bodySlot << std::endl;
        return false;
    }

    // Get the item in that body slot
    Item& item = player->InvBody[slot];
    if (item.isEmpty()) {
        std::cerr << "GAP Repair: No item in body slot " << bodySlot << std::endl;
        return false;
    }

    // Check if item needs repair
    if (item._iDurability >= item._iMaxDur) {
        std::cerr << "GAP Repair: Item already at full durability" << std::endl;
        return false;
    }

    // Calculate repair cost (same formula as stores.cpp AddStoreHoldRepair)
    int due = item._iMaxDur - item._iDurability;
    int cost;
    if (item._iMagical != ITEM_QUALITY_NORMAL && item._iIdentified) {
        cost = 30 * item._iIvalue * due / (item._iMaxDur * 100 * 2);
        if (cost == 0) cost = 1;
    } else {
        cost = item._ivalue * due / (item._iMaxDur * 2);
        cost = std::max(cost, 1);
    }

    // Check if player can afford it
    if (player->_pGold < cost) {
        std::cerr << "GAP Repair: Not enough gold (need " << cost << ", have " << player->_pGold << ")" << std::endl;
        return false;
    }

    // Repair the item
    std::cout << "GAP Repair: Repairing " << item._iIName
              << " (durability " << item._iDurability << "/" << item._iMaxDur
              << ") for " << cost << " gold" << std::endl;

    item._iDurability = item._iMaxDur;
    // Pile-aware spend: a raw `_pGold -= cost` is reverted by CalcPlrInv (which
    // recomputes _pGold from the inventory gold-piles every tick), so the repair
    // would be free. TakePlrsMoney removes the piles too. (companion == MyPlayer.)
    TakePlrsMoney(cost);
    CalcPlrInv(*player, true);

    return true;
}

bool GapIntentProcessor::ExecuteEquip(int invSlot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Equip: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    if (invSlot < 0 || invSlot >= player->_pNumInv) {
        std::cerr << "GAP Equip: Invalid inventory slot: " << invSlot << std::endl;
        return false;
    }

    const Item& invItem = player->InvList[invSlot];
    if (invItem.isEmpty()) {
        std::cerr << "GAP Equip: Inventory slot " << invSlot << " is empty" << std::endl;
        return false;
    }

    // Map the item's equip type to a body slot.
    inv_body_loc bodyLoc;
    switch (invItem._iLoc) {
    case ILOC_HELM:    bodyLoc = INVLOC_HEAD; break;
    case ILOC_ARMOR:   bodyLoc = INVLOC_CHEST; break;
    case ILOC_AMULET:  bodyLoc = INVLOC_AMULET; break;
    case ILOC_RING:    bodyLoc = player->InvBody[INVLOC_RING_LEFT].isEmpty() ? INVLOC_RING_LEFT : INVLOC_RING_RIGHT; break;
    case ILOC_ONEHAND: bodyLoc = INVLOC_HAND_LEFT; break;
    case ILOC_TWOHAND: bodyLoc = INVLOC_HAND_LEFT; break;
    default:
        std::cerr << "GAP Equip: Item not equippable (iLoc=" << static_cast<int>(invItem._iLoc) << ")" << std::endl;
        return false;
    }

    const bool sync = (GetControlledPlayerId() == MyPlayerId);

    std::cout << "GAP Equip: Equipping " << invItem._iIName << " from slot " << invSlot
              << " into body loc " << static_cast<int>(bodyLoc) << std::endl;

    // Lift the currently-equipped item(s) so the target slot is free. AutoEquip's
    // CMD_CHANGEPLRITEMS will overwrite the target slot on all clients, so we only
    // need an explicit del-sync for the off-hand a two-hander (bow) also vacates.
    std::vector<Item> displaced;
    if (!player->InvBody[bodyLoc].isEmpty()) {
        displaced.push_back(player->InvBody[bodyLoc]);
        player->InvBody[bodyLoc].clear();
    }
    if (invItem._iLoc == ILOC_TWOHAND && !player->InvBody[INVLOC_HAND_RIGHT].isEmpty()) {
        displaced.push_back(player->InvBody[INVLOC_HAND_RIGHT]);
        player->InvBody[INVLOC_HAND_RIGHT].clear();
        if (sync) NetSendCmdDelItem(false, INVLOC_HAND_RIGHT);
    }

    // Equip the new item the real-player way: AutoEquip copies it into the freed
    // slot and (for MyPlayer) broadcasts CMD_CHANGEPLRITEMS.
    if (!AutoEquip(*player, invItem, true, sync)) {
        for (Item& it : displaced)  // restore on failure
            AutoEquip(*player, it, true, sync);
        std::cerr << "GAP Equip: AutoEquip failed (slot occupied / not wieldable)" << std::endl;
        return false;
    }

    // Remove the now-equipped item from inventory (self-syncs CMD_DELINVITEMS),
    // then stash the swapped-out item(s) back into the pack (CMD_CHANGEINVITEMS).
    player->RemoveInvItem(invSlot, false);
    for (Item& it : displaced)
        AutoPlaceItemInInventory(*player, it, sync);

    return true;
}

bool GapIntentProcessor::ExecuteDropItem(int invSlot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Drop: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    // Validate inventory slot
    if (invSlot < 0 || invSlot >= player->_pNumInv) {
        std::cerr << "GAP Drop: Invalid inventory slot: " << invSlot << std::endl;
        return false;
    }

    // Check if inventory slot has an item
    const Item& invItem = player->InvList[invSlot];
    if (invItem.isEmpty()) {
        std::cerr << "GAP Drop: Inventory slot " << invSlot << " is empty" << std::endl;
        return false;
    }

    // Find adjacent position to drop the item
    std::optional<Point> dropPosition = FindAdjacentPositionForItem(
        player->position.tile,
        player->_pdir
    );

    if (!dropPosition) {
        std::cerr << "GAP Drop: No adjacent position available to drop item" << std::endl;
        return false;
    }

    // Drop the item
    std::cout << "GAP Drop: Dropping " << invItem._iIName
              << " from slot " << invSlot
              << " at (" << dropPosition->x << "," << dropPosition->y << ")" << std::endl;

    // Send network command to drop item
    // CMD_PUTITEM is used to place items from cursor onto ground
    NetSendCmdPItem(true, CMD_PUTITEM, *dropPosition, invItem);

    // Remove item from inventory
    player->RemoveInvItem(invSlot, true);  // Recalculate scrolls

    return true;
}

bool GapIntentProcessor::ExecuteDropGold(int amount) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Drop Gold: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    // Validate gold amount
    if (amount <= 0) {
        std::cerr << "GAP Drop Gold: Invalid amount: " << amount << std::endl;
        return false;
    }

    // Check if player has enough gold
    if (player->_pGold < amount) {
        std::cerr << "GAP Drop Gold: Not enough gold (has " << player->_pGold
                  << ", wants to drop " << amount << ")" << std::endl;
        return false;
    }

    // Find adjacent position to drop the gold
    std::optional<Point> dropPosition = FindAdjacentPositionForItem(
        player->position.tile,
        player->_pdir
    );

    if (!dropPosition) {
        std::cerr << "GAP Drop Gold: No adjacent position available" << std::endl;
        return false;
    }

    // Create a gold item
    Item goldItem;
    MakeGoldStack(goldItem, amount);

    std::cout << "GAP Drop Gold: Dropping " << amount << " gold at ("
              << dropPosition->x << "," << dropPosition->y << ")" << std::endl;

    // Drop the gold
    NetSendCmdPItem(true, CMD_PUTITEM, *dropPosition, goldItem);

    // Remove the gold from the player via the pile-aware path. A raw
    // `_pGold -= amount` is reverted by CalcPlrInv (it recomputes _pGold from the
    // inventory gold-piles every tick), so the player would keep the gold AND have
    // dropped a copy into the world — a dupe. TakePlrsMoney removes the piles too.
    TakePlrsMoney(amount);

    return true;
}

#endif

} // namespace devilution::gap
