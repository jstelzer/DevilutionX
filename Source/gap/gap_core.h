#pragma once

#include <cstdint>
#include <memory>
#include <string>

namespace devilution::gap {

class GapCore {
public:
    static GapCore& Instance();
    
    bool Initialize();
    void Shutdown();
    bool IsEnabled() const { return enabled_; }
    
    void OnGameTick(uint32_t tick);
    void ProcessIntents(uint32_t tick);
    
    void SetStateDivisor(uint32_t divisor) { state_divisor_ = divisor; }
    void SetTickRate(uint32_t rate) { tick_rate_ = rate; }
    
    void SetControlledPlayer(int slot) { controlled_player_ = slot; }
    int GetControlledPlayer() const { return controlled_player_; }
    
    bool SendMessage(const std::string& message);
    
private:
    GapCore() = default;
    ~GapCore() = default;
    GapCore(const GapCore&) = delete;
    GapCore& operator=(const GapCore&) = delete;
    
    bool enabled_ = false;
    uint32_t state_divisor_ = 2;
    uint32_t tick_rate_ = 30;
    uint32_t last_state_tick_ = 0;
    int controlled_player_ = 0;  // Default to player 0 (host)
    
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace devilution::gap