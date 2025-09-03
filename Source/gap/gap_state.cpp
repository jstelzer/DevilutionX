#include "gap_state.h"
#include "gap_json.h"
#include "../player.h"
#include "../monster.h"
#include "../items.h"
#include "../diablo.h"
#include "../levels/town.h"
#include "../stores.h"
#include "../nthread.h"
#include <chrono>
#include <cstdlib>

namespace devilution::gap {


std::string GapStateExtractor::ExtractState(uint32_t tick, uint32_t tick_rate) {
    auto now = std::chrono::system_clock::now();
    auto timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()).count();
    
    JsonBuilder state;
    state.BeginObject()
        .AddString("type", "state")
        .AddUInt("tick", tick)
        .AddUInt("tick_rate", tick_rate)
        .AddUInt("timestamp", static_cast<uint32_t>(timestamp));
    
    JsonBuilder data;
    data.BeginObject()
        .AddRaw("player", ExtractPlayerState())
        .AddRaw("nearby", ExtractNearbyEntities())
        .AddRaw("ui_state", ExtractUIState())
        .EndObject();
    
    state.AddRaw("data", data.ToString())
        .EndObject();
    
    return state.ToString();
}

std::string GapStateExtractor::ExtractPlayerState() {
    if (MyPlayerId >= MAX_PLRS) {
        return "{}";
    }
    
    const auto& player = Players[MyPlayerId];
    
    JsonBuilder state;
    state.BeginObject()
        .AddInt("hp", player._pHitPoints >> 6)
        .AddInt("hp_max", player._pMaxHP >> 6)
        .AddInt("mana", player._pMana >> 6)
        .AddInt("mana_max", player._pMaxMana >> 6)
        .AddArray("pos", {player.position.tile.x, player.position.tile.y})
        .AddInt("level", static_cast<int>(currlevel))
        .AddBool("in_town", leveltype == DTYPE_TOWN)
        .EndObject();
    
    return state.ToString();
}

std::string GapStateExtractor::ExtractNearbyEntities() {
    const int VIEW_RADIUS = 20;
    JsonBuilder result;
    result.BeginObject();
    
    if (MyPlayerId >= MAX_PLRS) {
        result.AddRaw("monsters", "[]")
              .AddRaw("items", "[]")
              .AddRaw("other_players", "[]")
              .EndObject();
        return result.ToString();
    }
    
    const auto& player = Players[MyPlayerId];
    Point playerPos = player.position.tile;
    
    std::stringstream monsters_json;
    monsters_json << "[";
    bool first_monster = true;
    
    for (size_t i = 0; i < ActiveMonsterCount; i++) {
        const auto& monster = Monsters[ActiveMonsters[i]];
        Point monsterPos = monster.position.tile;
        
        int dx = std::abs(monsterPos.x - playerPos.x);
        int dy = std::abs(monsterPos.y - playerPos.y);
        
        if (dx <= VIEW_RADIUS && dy <= VIEW_RADIUS) {
            if (!first_monster) monsters_json << ",";
            first_monster = false;
            
            JsonBuilder monsterData;
            monsterData.BeginObject()
                .AddInt("id", static_cast<int>(ActiveMonsters[i]))
                .AddString("type", "MON")
                .AddArray("pos", {monsterPos.x, monsterPos.y})
                .AddInt("hp_percent", monster.hitPoints > 0 ? 
                    (monster.hitPoints * 100 / monster.maxHitPoints) : 0)
                .EndObject();
            monsters_json << monsterData.ToString();
        }
    }
    monsters_json << "]";
    
    std::stringstream items_json;
    items_json << "[";
    bool first_item = true;
    
    for (uint8_t i = 0; i < ActiveItemCount; i++) {
        const auto& item = Items[ActiveItems[i]];
        Point itemPos = item.position;
        
        int dx = std::abs(itemPos.x - playerPos.x);
        int dy = std::abs(itemPos.y - playerPos.y);
        
        if (dx <= VIEW_RADIUS && dy <= VIEW_RADIUS) {
            if (!first_item) items_json << ",";
            first_item = false;
            
            JsonBuilder itemData;
            itemData.BeginObject()
                .AddInt("id", static_cast<int>(ActiveItems[i]))
                .AddArray("pos", {itemPos.x, itemPos.y})
                .EndObject();
            items_json << itemData.ToString();
        }
    }
    items_json << "]";
    
    result.AddRaw("monsters", monsters_json.str())
          .AddRaw("items", items_json.str())
          .AddRaw("other_players", "[]")
          .EndObject();
    
    return result.ToString();
}

std::string GapStateExtractor::ExtractUIState() {
    JsonBuilder state;
    state.BeginObject()
        .AddBool("in_menu", false)
        .AddBool("in_store", IsPlayerInStore())
        .AddBool("can_act", !gbIsMultiplayer || !nthread_has_500ms_passed(nullptr))
        .EndObject();
    
    return state.ToString();
}

} // namespace devilution::gap