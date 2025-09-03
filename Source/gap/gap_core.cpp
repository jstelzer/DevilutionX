#include "gap_core.h"
#include "gap_ipc.h"
#include "gap_state.h"
#include "gap_intent.h"
#include "gap_json.h"
#include "../diablo.h"
#include "../player.h"
#include <iostream>

namespace devilution::gap {


class GapCore::Impl {
public:
    GapIPC ipc;
    GapStateExtractor state_extractor;
    GapIntentProcessor intent_processor;
    
    bool SendMessage(const std::string& msg) {
        return ipc.SendMessage(msg);
    }
    
    bool ProcessIncomingMessages() {
        std::string msg;
        while (ipc.ReceiveMessage(msg)) {
            JsonParser parser(msg);
            if (parser.ParseObject()) {
                HandleMessage(parser);
            } else {
                std::cerr << "GAP: Failed to parse message" << std::endl;
            }
        }
        return true;
    }
    
private:
    void HandleMessage(const JsonParser& msg) {
        std::string type = msg.GetString("type");
        
        if (type == "hello") {
            HandleHello(msg);
        } else if (type == "intent") {
            HandleIntent(msg);
        }
    }
    
    void HandleHello(const JsonParser& msg) {
        // Check if password is required and validate if provided
        std::string provided_password = msg.GetString("password");
        
        // For now, we'll accept any password or no password
        // In the future, this could validate against game password
        std::cout << "GAP: Agent connecting";
        if (!provided_password.empty()) {
            std::cout << " with password: " << provided_password;
        }
        std::cout << std::endl;
        
        JsonBuilder response;
        response.BeginObject()
            .AddString("type", "hello")
            .AddString("version", "0.2.0")
            .AddInt("tick_rate", 30)
            .AddInt("state_divisor", 2)
            .AddString("game_mode", "single_player")
            .AddRaw("capabilities", "[\"move\",\"attack\",\"use_item\"]")
            .EndObject();
        SendMessage(response.ToString());
    }
    
    void HandleIntent(const JsonParser& msg) {
        intent_processor.QueueIntent(msg);
    }
};

GapCore& GapCore::Instance() {
    static GapCore instance;
    return instance;
}

bool GapCore::Initialize() {
    if (enabled_) {
        return true;
    }
    
    try {
        impl_ = std::make_unique<Impl>();
        if (!impl_->ipc.Initialize()) {
            std::cerr << "GAP: Failed to initialize IPC" << std::endl;
            impl_.reset();
            return false;
        }
        
        enabled_ = true;
        std::cout << "GAP: Initialized successfully" << std::endl;
        return true;
    } catch (const std::exception& e) {
        std::cerr << "GAP: Initialization failed: " << e.what() << std::endl;
        return false;
    }
}

void GapCore::Shutdown() {
    if (impl_) {
        impl_->ipc.Shutdown();
        impl_.reset();
    }
    enabled_ = false;
}

void GapCore::OnGameTick(uint32_t tick) {
    if (!enabled_ || !impl_) return;
    
    impl_->ProcessIncomingMessages();
    
    if (tick - last_state_tick_ >= state_divisor_) {
        std::string state = impl_->state_extractor.ExtractState(tick, tick_rate_);
        impl_->SendMessage(state);
        last_state_tick_ = tick;
    }
}

void GapCore::ProcessIntents(uint32_t tick) {
    if (!enabled_ || !impl_) return;
    
    impl_->intent_processor.ProcessPendingIntents(tick);
}

bool GapCore::SendMessage(const std::string& message) {
    if (!enabled_ || !impl_) return false;
    
    return impl_->SendMessage(message);
}

} // namespace devilution::gap