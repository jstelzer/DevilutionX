#ifdef ENABLE_GAP

#include "seat/seat.h"
#include "utils/log.hpp"
#include "player.h"
#include "engine/point.hpp"

// For existing command execution - reuse Phase 1 network fixes
#include "gap/gap_network.h"

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

void SeatManager::ProcessAllIntents(uint64_t tick) {
	std::vector<Intent> all_intents;
	
	// Gather intents from all active seats
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
			
			// Add player context and append to master list
			for (auto& intent : seat_intents) {
				all_intents.push_back(std::move(intent));
			}
		}
	}

	// Execute all intents
	for (int i = 0; i < 4; ++i) {
		if (!seats_[i] || !seats_[i]->IsActive()) continue;
		
		for (const auto& intent : all_intents) {
			// Only process intents for this seat's player
			if (intent.timestamp == tick) {
				ExecuteIntent(intent, i, tick);
			}
		}
	}

	// Post-process cleanup
	for (int i = 0; i < 4; ++i) {
		if (seats_[i] && seats_[i]->IsActive()) {
			seats_[i]->PostProcess(tick);
		}
	}
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
	// STUB: Route to existing movement system
	// For Phase 2.1, we'll just call existing functions
	// This maintains exact behavior while adding the abstraction layer
	
	Point target = { intent.data.x, intent.data.y };
	
	// Reuse Phase 1 network command routing
#ifdef ENABLE_GAP
	if (player_index == MyPlayerId) {
		// Human player - use existing input processing
		// TODO: Wire to existing ProcessInput() logic
		LogVerbose("STUB: ExecuteMoveIntent for human player {} to ({},{})", 
			player_index, target.x, target.y);
	} else {
		// Companion player - use Phase 1 direct execution
		gap::ExecuteDirectMove(player_index, target);
	}
#endif
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
			gap::ExecuteDirectAttack(player_index, intent.data.param1);
		} else {
			// Attack position - use same function with monster_id = 0 for position-based attacks
			gap::ExecuteDirectAttack(player_index, 0);
		}
	}
#endif
}

void SeatManager::ExecuteInteractIntent(const Intent& intent, int player_index) {
	// STUB: Route to existing interaction system
	LogVerbose("STUB: ExecuteInteractIntent for player {} at ({},{})", 
		player_index, intent.data.x, intent.data.y);

#ifdef ENABLE_GAP
	if (player_index != MyPlayerId) {
		// Companion interaction
		Point target = { intent.data.x, intent.data.y };
		gap::ExecuteDirectInteract(player_index, target);
	}
#endif
}

void SeatManager::ExecuteItemIntent(const Intent& intent, int player_index) {
	// STUB: Route to existing item usage system
	LogVerbose("STUB: ExecuteItemIntent for player {} item {}", 
		player_index, intent.data.param1);
	
	// TODO: Wire to existing item usage functions
}

void SeatManager::ExecuteCastIntent(const Intent& intent, int player_index) {
	// STUB: Route to existing spell casting system  
	LogVerbose("STUB: ExecuteCastIntent for player {} spell {} at ({},{})", 
		player_index, intent.data.param1, intent.data.x, intent.data.y);
	
	// TODO: Wire to existing spell casting functions
}

void SeatManager::ExecuteChatIntent(const Intent& intent, int player_index) {
	// STUB: Route to existing chat system
	LogVerbose("STUB: ExecuteChatIntent for player {}: '{}'", 
		player_index, intent.data.text);
	
	// TODO: Wire to existing chat functions
}

} // namespace devilution

#endif // ENABLE_GAP