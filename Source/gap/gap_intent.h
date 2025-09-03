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
};

} // namespace devilution::gap