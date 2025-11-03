#ifdef ENABLE_GAP

#include "seat/seat.h"
#include "seat/human_seat.h"
#include "utils/log.hpp"
#include "player.h"
#include "engine/point.hpp"
#include "inv.h"
#include <iostream>

// For existing command execution - reuse Phase 1 network fixes
#include "gap/gap_network.h"
#include "gap/gap_chat.h"

namespace devilution {

void SeatManager::RegisterSeat(std::unique_ptr<Seat> seat) {
	if (!seat) {
		return;
	}

	int player_index = seat->GetPlayerIndex();
	if (player_index < 0 || player_index >= 4) {
		LogError("Invalid player index {} for seat registration", player_index);
		return;
	}

	seats_[player_index] = std::move(seat);
	LogVerbose("Registered {} seat for player {}", seats_[player_index]->GetTypeName(), player_index);
}

void SeatManager::UnregisterSeat(int player_index) {
	if (player_index < 0 || player_index >= 4) {
		return;
	}

	if (seats_[player_index]) {
		LogVerbose("Unregistered {} seat for player {}", seats_[player_index]->GetTypeName(), player_index);
		seats_[player_index].reset();
	}
}

bool SeatManager::ProcessAllIntents(uint64_t tick) {
	// Check for early exit conditions from human seats (mirrors ProcessInput logic)
	for (int i = 0; i < 4; ++i) {
		if (seats_[i] && seats_[i]->IsActive() && seats_[i]->CanControlUI()) {
			// Check if this is a HumanSeat and should exit early
			if (auto* humanSeat = dynamic_cast<HumanSeat*>(seats_[i].get())) {
				if (humanSeat->ShouldExitEarly()) {
					return false;  // Exit early like ProcessInput does
				}
			}
		}
	}

	// Gather and execute intents from each active seat
	for (int i = 0; i < 4; ++i) {
		if (seats_[i] && seats_[i]->IsActive()) {
			std::vector<Intent> seat_intents;
			seats_[i]->GatherIntents(seat_intents, tick);

			// Rate limiting check
			if (seat_intents.size() > Seat::MAX_INTENTS_PER_TICK) {
				LogWarn("Seat {} exceeded intent limit ({} intents), truncating",
					i, seat_intents.size());
				seat_intents.resize(Seat::MAX_INTENTS_PER_TICK);
			}

			// Execute intents for THIS seat only
			for (const auto& intent : seat_intents) {
				if (intent.timestamp == tick) {
					std::cerr << "SeatManager: About to ExecuteIntent for player " << i << " type=" << static_cast<int>(intent.type) << std::endl;
					ExecuteIntent(intent, i, tick);
					std::cerr << "SeatManager: ExecuteIntent completed for player " << i << std::endl;
				}
			}
		}
	}

	// Post-process cleanup
	for (int i = 0; i < 4; ++i) {
		if (seats_[i] && seats_[i]->IsActive()) {
			seats_[i]->PostProcess(tick);
		}
	}
	
	// Return true to continue game logic (mirrors ProcessInput behavior)
	return true;
}

Seat* SeatManager::GetSeat(int player_index) const {
	if (player_index < 0 || player_index >= 4) {
		return nullptr;
	}
	return seats_[player_index].get();
}

bool SeatManager::HasActiveSeats() const {
	for (int i = 0; i < 4; ++i) {
		if (seats_[i] && seats_[i]->IsActive()) {
			return true;
		}
	}
	return false;
}

void SeatManager::Clear() {
	for (int i = 0; i < 4; ++i) {
		seats_[i].reset();
	}
}

void SeatManager::ExecuteIntent(const Intent& intent, int player_index, uint64_t tick) {
	// Sanity check - ensure player exists
	if (player_index < 0 || player_index >= MAX_PLRS) {
		return;
	}

	switch (intent.type) {
		case Intent::Type::Move:
			ExecuteMoveIntent(intent, player_index);
			break;
		case Intent::Type::Attack:
			ExecuteAttackIntent(intent, player_index);
			break;
		case Intent::Type::Interact:
			ExecuteInteractIntent(intent, player_index);
			break;
		case Intent::Type::UseItem:
			ExecuteItemIntent(intent, player_index);
			break;
		case Intent::Type::Cast:
			ExecuteCastIntent(intent, player_index);
			break;
		case Intent::Type::Chat:
			ExecuteChatIntent(intent, player_index);
			break;
	}
}

void SeatManager::ExecuteMoveIntent(const Intent& intent, int player_index) {
	// Route to existing movement system
	Point target = { intent.data.x, intent.data.y };
	
	if (player_index == MyPlayerId) {
		// Human player - use existing movement functions
		// This mirrors what ProcessInput -> RepeatPlayerAction -> ... does
		// TODO: Call the actual movement functions that ProcessInput would call
		// For now, log the intent (Phase 2.2 transitional implementation)
		LogVerbose("HumanSeat: ExecuteMoveIntent to ({},{}) for player {}", 
			target.x, target.y, player_index);
	} else {
		// Companion player - use Phase 1 direct execution
#ifdef ENABLE_GAP
		std::cerr << "SeatManager: About to call ExecuteDirectMove for player " << player_index << std::endl;
		gap::ExecuteDirectMove(player_index, target);
		std::cerr << "SeatManager: ExecuteDirectMove returned for player " << player_index << std::endl;
#endif
	}
	std::cerr << "SeatManager: ExecuteMoveIntent completed for player " << player_index << std::endl;
}

void SeatManager::ExecuteAttackIntent(const Intent& intent, int player_index) {
	// STUB: Route to existing attack system
	
#ifdef ENABLE_GAP
	if (player_index == MyPlayerId) {
		// Human player - use existing input processing
		LogVerbose("STUB: ExecuteAttackIntent for human player {}", player_index);
	} else {
		// Companion player - use Phase 1 direct execution
		if (intent.data.param1 > 0) {
			// Attack monster by ID
			std::cerr << "SeatManager: Attacking monster ID " << intent.data.param1 << std::endl;
			gap::ExecuteDirectAttack(player_index, intent.data.param1);
		} else if (intent.data.x > 0 || intent.data.y > 0) {
			// Attack position - need to find monster at position and attack by ID
			std::cerr << "SeatManager: Position-based attack at (" << intent.data.x << "," << intent.data.y << ")" << std::endl;
			// Call the position-based attack from gap_network
			gap::ExecutePositionAttack(player_index, intent.data.x, intent.data.y);
		} else {
			std::cerr << "SeatManager: Invalid attack intent - no target" << std::endl;
		}
	}
#endif
}

void SeatManager::ExecuteInteractIntent(const Intent& intent, int player_index) {
#ifdef ENABLE_GAP
	if (player_index != MyPlayerId) {
		// Companion interaction - check if this is item pickup (param1 set) or object interaction (position only)
		if (intent.data.param1 > 0) {
			// Item pickup - param1 contains item_id
			LogVerbose("SeatManager: ExecuteInteractIntent - Item pickup {} for player {}",
				intent.data.param1, player_index);
			gap::ExecuteDirectPickup(player_index, intent.data.param1);
		} else {
			// Object interaction - use position
			LogVerbose("SeatManager: ExecuteInteractIntent - Object interaction at ({},{}) for player {}",
				intent.data.x, intent.data.y, player_index);
			Point target = { intent.data.x, intent.data.y };
			gap::ExecuteDirectInteract(player_index, target);
		}
		return;
	}
#endif

	// STUB for human player
	LogVerbose("STUB: ExecuteInteractIntent for player {} at ({},{})",
		player_index, intent.data.x, intent.data.y);
}

void SeatManager::ExecuteItemIntent(const Intent& intent, int player_index) {
	// Sanity check
	if (player_index < 0 || player_index >= MAX_PLRS) {
		return;
	}

	Player& player = Players[player_index];

	// intent.data.param1 contains the belt slot number (0-7)
	int belt_slot = intent.data.param1;

	// Validate belt slot
	if (belt_slot < 0 || belt_slot >= MaxBeltItems) {
		LogError("ExecuteItemIntent: Invalid belt slot {} for player {}", belt_slot, player_index);
		return;
	}

	// Convert belt slot to inventory index
	// INVITEM_BELT_FIRST = 47, so slot 0 = 47, slot 1 = 48, etc.
	int inv_index = INVITEM_BELT_FIRST + belt_slot;

	LogVerbose("ExecuteItemIntent: Player {} using belt slot {} (inv index {})",
		player_index, belt_slot, inv_index);

	// Call the game's UseInvItem function
	// This handles all logic: consuming item, applying effects, network sync, etc.
	bool success = UseInvItem(player, inv_index);

	if (success) {
		// Avoid division by zero if player stats are uninitialized
		int hp_pct = (player._pMaxHP > 0) ? (player._pHitPoints * 100) / player._pMaxHP : 0;
		LogVerbose("ExecuteItemIntent: Successfully used belt item, HP={}%", hp_pct);
	} else {
		LogWarn("ExecuteItemIntent: UseInvItem returned false for player {} slot {}",
			player_index, belt_slot);
	}
}

void SeatManager::ExecuteCastIntent(const Intent& intent, int player_index) {
	// STUB: Route to existing spell casting system  
	LogVerbose("STUB: ExecuteCastIntent for player {} spell {} at ({},{})", 
		player_index, intent.data.param1, intent.data.x, intent.data.y);
	
	// TODO: Wire to existing spell casting functions
}

void SeatManager::ExecuteChatIntent(const Intent& intent, int player_index) {
	// Route to GAP chat system
	if (!intent.data.text.empty()) {
		GAPChatHandler::getInstance().SendAIResponse(intent.data.text);
		LogVerbose("ExecuteChatIntent for player {}: '{}'",
			player_index, intent.data.text.c_str());
	}
}

} // namespace devilution

#endif // ENABLE_GAP