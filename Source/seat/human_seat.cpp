#ifdef ENABLE_GAP

#include "seat/human_seat.h"
#include "diablo.h"
#include "player.h"
#include "engine/point.hpp"
#include "controls/plrctrls.h"
#include "controls/game_controls.h"
#include "cursor.h"
#include "track.h"
#include "gmenu.h"
#include "stores.h"
#include "utils/log.hpp"

// Forward declarations for functions we need
bool IsPlayerInStore();

// External variables are declared in the included headers

namespace devilution {

HumanSeat::HumanSeat(int player_index) 
	: player_index_(player_index), last_input_tick_(0) {
	LogVerbose("Created HumanSeat for player {}", player_index_);
}

bool HumanSeat::IsActive() const {
	// Human seat is active if this is the local player's slot
	return player_index_ == MyPlayerId;
}

void HumanSeat::GatherIntents(std::vector<Intent>& out, uint64_t tick) {
	if (!IsActive()) {
		return;
	}
	
	// Check pause state (mirrors ProcessInput logic)
	if (PauseMode == 2) {
		return;
	}

	// Skip if menu is active in single player (mirrors ProcessInput logic)
	if (!gbIsMultiplayer && gmenu_is_active()) {
		return;
	}

	// Skip if menu active or timeout cursor (mirrors ProcessInput logic)
	if (gmenu_is_active() || sgnTimeoutCurs != CURSOR_NONE) {
		return;
	}
	
	// Phase 2.2: Generate intents from current input state
	GenerateMovementIntents(out, tick);
	GenerateActionIntents(out, tick);
	// TODO: Add other intent types later
	// GenerateInventoryIntents(out, tick);
	// GenerateChatIntents(out, tick);
	
	if (tick != last_input_tick_) {
		if (!out.empty()) {
			LogVerbose("HumanSeat: Generated {} intents for tick {} (player {})", 
				out.size(), tick, player_index_);
		}
		last_input_tick_ = tick;
	}
}

void HumanSeat::PostProcess(uint64_t tick) {
	// STUB: Nothing needed for post-processing yet
	// This will be used later for cleanup after intent execution
}

void HumanSeat::ProcessKeyboardMouse(std::vector<Intent>& out, uint64_t tick) {
	// STUB: Will convert keyboard/mouse input to intents
	// This replaces the existing input polling in ProcessInput()
}

void HumanSeat::ProcessGamepad(std::vector<Intent>& out, uint64_t tick) {
	// STUB: Will convert gamepad input to intents  
	// This replaces the existing plrctrls_every_frame() logic
}

void HumanSeat::GenerateMovementIntents(std::vector<Intent>& out, uint64_t tick) {
	// This mirrors the cursor movement logic from CheckCursMove() and click-to-move
	
	// Check if we have pending movement action (held mouse or controller)
	bool hasMovementInput = (sgbMouseDown != CLICK_NONE) || (ControllerActionHeld != GameActionType_NONE);
	
	if (!hasMovementInput) {
		return;
	}
	
	// Check if we should repeat the last player action (mirrors RepeatPlayerAction)
	if (pcurs == CURSOR_HAND && LastPlayerAction != PlayerActionType::None && 
	    !IsPlayerInStore() && MyPlayer->destAction == ACTION_NONE) {
		
		// Generate movement intent based on current cursor position
		// This captures the same logic that ProcessInput -> RepeatPlayerAction does
		// TODO: Convert screen coordinates to tile coordinates properly
		Point targetPos = MousePosition;
		
		// Create movement intent
		Intent moveIntent(Intent::Type::Move, tick, targetPos.x, targetPos.y);
		out.push_back(moveIntent);
		
		LogVerbose("HumanSeat: Generated Move intent to ({},{}) from cursor position", 
			targetPos.x, targetPos.y);
	}
}

void HumanSeat::GenerateActionIntents(std::vector<Intent>& out, uint64_t tick) {
	// This mirrors the click action logic from mouse/controller handlers
	
	// Check if we have an attack or interact action pending
	if (LastPlayerAction == PlayerActionType::Attack || 
	    LastPlayerAction == PlayerActionType::AttackMonsterTarget ||
	    LastPlayerAction == PlayerActionType::AttackPlayerTarget) {
		
		// TODO: Convert screen coordinates to tile coordinates properly
		Point targetPos = MousePosition;
		
		// Create attack intent
		Intent attackIntent(Intent::Type::Attack, tick, targetPos.x, targetPos.y);
		out.push_back(attackIntent);
		
		LogVerbose("HumanSeat: Generated Attack intent to ({},{}) from action {}", 
			targetPos.x, targetPos.y, static_cast<int>(LastPlayerAction));
			
	} else if (LastPlayerAction == PlayerActionType::OperateObject) {
		
		// TODO: Convert screen coordinates to tile coordinates properly
		Point targetPos = MousePosition;
		
		// Create interact intent
		Intent interactIntent(Intent::Type::Interact, tick, targetPos.x, targetPos.y);
		out.push_back(interactIntent);
		
		LogVerbose("HumanSeat: Generated Interact intent to ({},{}) from action", 
			targetPos.x, targetPos.y);
	}
}

void HumanSeat::GenerateInventoryIntents(std::vector<Intent>& out, uint64_t tick) {
	// STUB: Convert inventory input (hotkeys, belt use) to UseItem intents
}

void HumanSeat::GenerateChatIntents(std::vector<Intent>& out, uint64_t tick) {
	// STUB: Convert chat input (enter key, typed messages) to Chat intents
}

} // namespace devilution

#endif // ENABLE_GAP