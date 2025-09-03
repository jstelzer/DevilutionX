#pragma once

#include <cstdint>
#include <queue>
#include <string>

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
    std::string param_kind; // For potion kind ("hp", "mp")
};

class GapIntentProcessor {
public:
    void QueueIntent(const JsonParser& intent_msg);
    void ProcessPendingIntents(uint32_t current_tick);
    
private:
    std::queue<Intent> intent_queue_;
    
    bool ExecuteIntent(const Intent& intent);
    bool ExecuteMove(int x, int y);
    bool ExecuteAttack(int x, int y);
    bool ExecuteCast(int slot, int x, int y);
    bool ExecutePickup(int item_id);
    bool ExecuteUsePotion(const std::string& kind, int slot = -1);
    bool ExecuteInteract(int object_id);
    bool ExecutePath(int x, int y);
    bool ExecuteExplore();
    bool ExecuteChat(const std::string& message);
};

} // namespace devilution::gap