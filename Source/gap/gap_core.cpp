#include "gap_core.h"
#include "gap_ipc.h"
#include "gap_state.h"
#include "gap_intent.h"
#include "gap_json.h"
#ifdef ENABLE_GAP
#include "gap_chat.h"
#include "../actor/actor_store.h"
#include "../seat/seat.h"
#include "../seat/companion_seat.h"
#endif
#include "../diablo.h"
#include "../player.h"
#include "../pfile.h"
#include "../multi.h"
#include "../storm/storm_net.hpp"
#include <iostream>

// External companion mode globals from diablo.cpp
extern std::string gGapCompanionSave;
extern int gGapCompanionSlot;

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
            // Check if this is a chat intent - handle globally, not as player action
            std::string action = msg.GetString("action");
            if (action == "chat") {
                HandleChatIntent(msg);
            } else {
                // All other intents are player-specific and go through normal routing
                HandleIntent(msg);
            }
        }
    }
    
    void HandleHello(const JsonParser& msg) {
        // Check if password is required and validate if provided
        std::string provided_password = msg.GetString("password");
        
        // Handle companion slot request
        int requested_slot = 0;
        if (msg.HasKey("control_player")) {
            requested_slot = msg.GetInt("control_player");
        } else if (gGapCompanionSlot >= 0) {
            requested_slot = gGapCompanionSlot;
        }
        
        // Validate slot range
        if (requested_slot < 0 || requested_slot > 3) {
            std::cout << "GAP: Invalid player slot " << requested_slot << ", using slot 0" << std::endl;
            requested_slot = 0;
        }
        
        // Set controlled player
        GapCore& core = GapCore::Instance();
        core.SetControlledPlayer(requested_slot);
        
        // Register CompanionSeat for the actual companion slot when companion connects
        if (requested_slot != MyPlayerId) {
#ifdef ENABLE_GAP
            auto& seatManager = devilution::SeatManager::Instance();
            
            // Unregister any existing seat for this slot
            seatManager.UnregisterSeat(requested_slot);
            
            // Register new CompanionSeat for the actual companion slot
            auto companionSeat = std::make_unique<devilution::CompanionSeat>(requested_slot);
            seatManager.RegisterSeat(std::move(companionSeat));
            std::cout << "GAP: Registered CompanionSeat for actual companion slot " << requested_slot << std::endl;
#endif
        }
        
        // Debug: Check companion loading conditions
        std::cout << "GAP: Debug - requested_slot=" << requested_slot << " MyPlayerId=" << MyPlayerId 
                  << " gGapCompanionSlot=" << gGapCompanionSlot << " gGapCompanionSave='" << gGapCompanionSave << "'" << std::endl;
        
        // Load companion character if specified and slot is not the main player
        if (requested_slot != MyPlayerId && gGapCompanionSlot >= 0 && !gGapCompanionSave.empty()) {
            std::cout << "GAP: Loading companion from " << gGapCompanionSave << " into slot " << requested_slot << std::endl;
            
            try {
                // Parse the companion save filename to get save number
                // Extract number from filenames like "multi_1.sv" -> 1
                size_t pos = gGapCompanionSave.rfind("multi_");
                if (pos == std::string::npos) {
                    pos = gGapCompanionSave.rfind("single_");
                }
                uint32_t companionSaveNum = 0;
                if (pos != std::string::npos) {
                    pos += (gGapCompanionSave.substr(pos, 6) == "multi_") ? 6 : 7;
                    size_t endPos = gGapCompanionSave.find('.', pos);
                    if (endPos == std::string::npos) endPos = gGapCompanionSave.length();
                    
                    std::string numberStr = gGapCompanionSave.substr(pos, endPos - pos);
                    try {
                        companionSaveNum = static_cast<uint32_t>(std::stoul(numberStr));
                    } catch (const std::exception&) {
                        std::cerr << "GAP: Failed to parse save number from: " << gGapCompanionSave << std::endl;
                        companionSaveNum = 0;
                    }
                } else {
                    std::cerr << "GAP: Invalid save filename format: " << gGapCompanionSave << std::endl;
                }
                
                // Load companion character into the requested slot
                pfile_read_player_from_save(companionSaveNum, Players[requested_slot]);
                
                // Mark the companion slot as active
                Players[requested_slot].plractive = true;
                
                // Mark as connected in multiplayer state - this is crucial for visibility!
                player_state[requested_slot] |= PS_CONNECTED;
                player_state[requested_slot] |= PS_ACTIVE;
                
                // Sync companion to current level - CRITICAL for rendering!
                Players[requested_slot].plrlevel = Players[MyPlayerId].plrlevel;
                Players[requested_slot].plrIsOnSetLevel = Players[MyPlayerId].plrIsOnSetLevel;
                
                // Set companion position to near the main player (offset by 2 tiles)
                Point mainPlayerPos = Players[MyPlayerId].position.tile;
                Point companionPos = mainPlayerPos;
                // Offset companion by 2 tiles south to avoid overlap
                companionPos.y = mainPlayerPos.y + 2;
                
                Players[requested_slot].position.tile = companionPos;
                Players[requested_slot].position.future = companionPos;
                Players[requested_slot].position.old = companionPos;
                
                // Initialize light radius for companion - CRITICAL for monster visibility!
                if (Players[requested_slot]._pLightRad <= 0) {
                    Players[requested_slot]._pLightRad = 10; // Default light radius
                    std::cout << "GAP: Setting companion light radius to " << Players[requested_slot]._pLightRad << std::endl;
                }
                
                // Positioned companion near player (reduced logging)
                
                std::cout << "GAP: Successfully loaded companion " << Players[requested_slot]._pName 
                          << " from save #" << companionSaveNum << " into slot " << requested_slot << std::endl;
                          
            } catch (const std::exception& e) {
                std::cerr << "GAP: Failed to load companion: " << e.what() << std::endl;
            }
        }
        
        // For now, we'll accept any password or no password
        // In the future, this could validate against game password
        std::cout << "GAP: Agent connecting to control player slot " << requested_slot;
        if (!provided_password.empty()) {
            std::cout << " with password: " << provided_password;
        }
        if (gGapCompanionSlot >= 0 && !gGapCompanionSave.empty()) {
            std::cout << " using companion save: " << gGapCompanionSave;
        }
        std::cout << std::endl;
        
        JsonBuilder response;
        response.BeginObject()
            .AddString("type", "hello")
            .AddString("version", "0.2.0")
            .AddInt("tick_rate", 30)
            .AddInt("state_divisor", 2)
            .AddString("game_mode", "multiplayer")  // Changed from single_player
            .AddInt("controlled_player", requested_slot)
            .AddRaw("capabilities", "[\"move\",\"attack\",\"use_item\",\"chat\"]")
            .EndObject();
        SendMessage(response.ToString());
    }
    
    void HandleIntent(const JsonParser& msg) {
        intent_processor.QueueIntent(msg);
    }
    
    void HandleChatIntent(const JsonParser& msg) {
        // Handle chat as global GAP protocol event - no player routing needed
        std::string params_str = msg.GetObjectString("params");
        JsonParser params(params_str);
        std::string message = params.GetString("kind"); // Chat message is stored in "kind" field
        
        if (!message.empty()) {
#ifdef ENABLE_GAP
            // Execute chat directly as global broadcast
            GAPChatHandler::getInstance().SendAIResponse(message);
            std::cout << "GAP: Executed global chat intent: " << message << std::endl;
#else
            std::cerr << "GAP: Chat intent requires ENABLE_GAP flag" << std::endl;
#endif
        } else {
            std::cerr << "GAP: Chat intent missing message in params.kind" << std::endl;
        }
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
        
        // Note: ActorStore initialization moved to first game tick to ensure
        // it happens after companion loading in HandleHello
        
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
    
#ifdef ENABLE_GAP
    // Shutdown Actor system (always safe to call)
    ActorStore::Instance().Shutdown();
    std::cout << "GAP: Actor system shutdown" << std::endl;
#endif
    
    enabled_ = false;
}

// Note: SyncCompanionLevel() moved to event-driven system in player.cpp

void GapCore::OnGameTick(uint32_t tick) {
    if (!enabled_ || !impl_) return;
    
    // Note: Level sync is now event-driven via setLevel() hooks - no polling needed
    
#ifdef ENABLE_GAP
    // Initialize ActorStore on first tick (after companion loading)
    static bool actor_store_initialized = false;
    if (!actor_store_initialized) {
        ActorStore::Instance().Initialize();
        std::cout << "GAP: Actor system initialized after companion loading" << std::endl;
        actor_store_initialized = true;
    }
    
    // Refresh ActorStore to sync with current monster spawns/deaths
    // Only refresh periodically to avoid performance impact
    static uint32_t last_refresh_tick = 0;
    if (tick - last_refresh_tick >= 30) { // Refresh every 30 ticks (~1 second)
        ActorStore::Instance().Refresh();
        last_refresh_tick = tick;
    }
#endif
    
    impl_->ProcessIncomingMessages();
    
    if (tick - last_state_tick_ >= state_divisor_) {
        std::string state = impl_->state_extractor.ExtractState(tick, tick_rate_);
        impl_->SendMessage(state);
        last_state_tick_ = tick;
    }
}

void GapCore::ProcessIntents(uint32_t tick) {
    if (!enabled_ || !impl_) return;
    
    // Use seat-based intent processing if available, otherwise fall back to direct execution
    impl_->intent_processor.ProcessPendingIntentsViaSeat(tick);
}

bool GapCore::SendMessage(const std::string& message) {
    if (!enabled_ || !impl_) return false;
    
    return impl_->SendMessage(message);
}

} // namespace devilution::gap