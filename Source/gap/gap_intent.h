#pragma once

#include <cstdint>
#include <queue>
#include <string>

#ifdef ENABLE_GAP
// Forward declaration for seat intent
namespace devilution {
    struct Intent;
}
#endif

namespace devilution::gap {

class JsonParser;

struct Intent {
    std::string action;
    int param_x;
    int param_y;
    uint32_t target_tick;

    // Additional parameters for new intent types
    int param_id;           // For pickup item ID, object ID, monster ID
    int param_slot;         // For spell slot, belt slot
    int param_inv_slot;     // For inventory slot (belt refill)
    std::string param_kind; // For potion kind ("hp", "mp")
};

class GapIntentProcessor {
public:
    void QueueIntent(const JsonParser& intent_msg);

    // DSL intent parser - parses text commands like "MV 37 18", "AT 12", etc.
    void QueueDSLIntent(const std::string& dsl_line);

    void ProcessPendingIntents(uint32_t current_tick);

#ifdef ENABLE_GAP
    // Bridge to new Seat system
    void ProcessPendingIntentsViaSeat(uint32_t current_tick);
    static devilution::Intent ConvertToSeatIntent(const Intent& gap_intent, uint64_t tick);
#endif
    
private:
    std::queue<Intent> intent_queue_;
    
    bool ExecuteIntent(const Intent& intent);
    bool ExecuteMove(int x, int y);
    bool ExecuteAttack(int x, int y);
    bool ExecuteCast(int slot, int x, int y);
    bool ExecuteCastSpell(int spell_id, int x, int y);
    bool ExecutePickup(int item_id);
    bool ExecuteUsePotion(const std::string& kind, int slot = -1);
    bool ExecuteInteract(int object_id);
    bool ExecutePath(int x, int y);
    bool ExecuteExplore();
    bool ExecuteChat(const std::string& message);
    bool ExecuteBuy(const std::string& npcCode, int itemIndex);
    bool ExecuteSell(int invSlot);
    bool ExecuteRepair(int invSlot);
    bool ExecuteIdentify(int invSlot);
    bool ExecuteAddStat(const std::string& statName);
    bool ExecuteBeltRefill(int invSlot, int beltSlot);
    bool ExecuteDropItem(int invSlot);
    bool ExecuteDropGold(int amount);
};

} // namespace devilution::gap