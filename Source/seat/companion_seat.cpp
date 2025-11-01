#ifdef ENABLE_GAP

#include "seat/companion_seat.h"
#include "player.h"
#include "utils/log.hpp"
#include <cmath>

// For survival reflexes - check player health, nearby monsters
#include "monster.h"

namespace devilution {

CompanionSeat::CompanionSeat(int player_index) 
	: player_index_(player_index), last_tick_(0) {
	LogVerbose("Created CompanionSeat for player {}", player_index_);
	recent_ticks_.reserve(100); // Pre-allocate for performance
}

bool CompanionSeat::IsActive() const {
	// Companion seat is active if the player slot is valid and in use
	return player_index_ >= 0 && player_index_ < MAX_PLRS && 
	       Players[player_index_].plractive;
}

void CompanionSeat::GatherIntents(std::vector<Intent>& out, uint64_t tick) {
	if (!IsActive()) {
		return;
	}
	
	last_tick_ = tick;
	CleanupOldTicks(tick);
	
	// Apply survival reflexes first (highest priority)
	if (survival_reflexes_enabled_ && ShouldApplySurvivalOverride(tick)) {
		return; // Survival override handled, skip other intents this tick
	}
	
	// Process queued intents from GAP protocol
	ProcessQueuedIntents(out, tick);
	
	// Apply safety filters
	FilterDangerousIntents(out);
	PrioritizeIntents(out);
	
	// Apply rate limiting (this may reduce the output)
	if (ShouldApplyRateLimit(tick)) {
		LogWarn("CompanionSeat: Rate limiting applied for player {}", player_index_);
		out.clear(); // Drop all intents this tick
		return;
	}
	
	// Track processed intents for rate limiting
	if (!out.empty()) {
		recent_ticks_.push_back(tick);
		LogVerbose("CompanionSeat: Processed {} intents for player {} at tick {}", 
			out.size(), player_index_, tick);
	}
}

void CompanionSeat::PostProcess(uint64_t tick) {
	// Cleanup after intent execution
	// This is called after SeatManager executes all intents
}

void CompanionSeat::EnqueueIntent(const Intent& intent) {
	// Add intent to queue from GAP protocol
	if (intent_queue_.size() >= MAX_QUEUE_SIZE) {
		LogWarn("CompanionSeat: Intent queue full for player {}, dropping oldest", player_index_);
		intent_queue_.pop(); // Drop oldest intent
	}
	
	intent_queue_.push(intent);
	LogVerbose("CompanionSeat: Enqueued {} intent for player {} (queue size: {})", 
		static_cast<int>(intent.type), player_index_, intent_queue_.size());
}

void CompanionSeat::ClearQueue() {
	while (!intent_queue_.empty()) {
		intent_queue_.pop();
	}
	LogVerbose("CompanionSeat: Cleared intent queue for player {}", player_index_);
}

bool CompanionSeat::IsOverloaded() const {
	return intent_queue_.size() > (MAX_QUEUE_SIZE * 0.8); // 80% full threshold
}

void CompanionSeat::SetRateLimits(int max_per_tick, int max_per_second) {
	max_intents_per_tick_ = std::max(1, std::min(max_per_tick, MAX_INTENTS_PER_TICK));
	max_intents_per_second_ = std::max(1, std::min(max_per_second, MAX_INTENTS_PER_SECOND));
	LogVerbose("CompanionSeat: Updated rate limits for player {} to {}/tick, {}/second", 
		player_index_, max_intents_per_tick_, max_intents_per_second_);
}

bool CompanionSeat::ShouldApplyRateLimit(uint64_t tick) const {
	// Check intents per tick limit
	int intents_this_tick = CountRecentIntents(tick, 1);
	if (intents_this_tick > max_intents_per_tick_) {
		return true;
	}
	
	// Check intents per second limit (assume 30 ticks per second)
	int intents_this_second = CountRecentIntents(tick, 30);
	if (intents_this_second > max_intents_per_second_) {
		return true;
	}
	
	return false;
}

bool CompanionSeat::ShouldApplySurvivalOverride(uint64_t tick) {
	// DISABLED: Survival reflexes now handled by Python orchestrator
	// This old safety code was blocking proper healing commands from the agent
	// The Python orchestrator has sophisticated multi-agent coordination
	// that handles emergency healing, retreat, and tactical decisions

	// Always return false to not block intents
	return false;
}

void CompanionSeat::ProcessQueuedIntents(std::vector<Intent>& out, uint64_t tick) {
	// Process up to max_intents_per_tick_ from the queue
	int processed = 0;
	while (!intent_queue_.empty() && processed < max_intents_per_tick_) {
		Intent intent = intent_queue_.front();
		intent_queue_.pop();
		
		// Update intent timestamp to current tick
		intent.timestamp = tick;
		out.push_back(intent);
		processed++;
	}
}

void CompanionSeat::FilterDangerousIntents(std::vector<Intent>& intents) {
	// Remove or modify potentially dangerous intents
	// For now, all intents are considered safe
	// TODO: Add specific safety checks (e.g., don't attack other players)
}

void CompanionSeat::PrioritizeIntents(std::vector<Intent>& intents) {
	// Sort intents by priority (survival > combat > movement > other)
	std::sort(intents.begin(), intents.end(), [](const Intent& a, const Intent& b) {
		// Priority order: UseItem > Attack > Move > Interact > Cast > Chat
		static const int priorities[] = { 3, 2, 1, 0, 4, 5 }; // Maps to Intent::Type enum
		int priorityA = (static_cast<int>(a.type) < 6) ? priorities[static_cast<int>(a.type)] : 6;
		int priorityB = (static_cast<int>(b.type) < 6) ? priorities[static_cast<int>(b.type)] : 6;
		return priorityA > priorityB; // Higher priority first
	});
}

void CompanionSeat::CleanupOldTicks(uint64_t current_tick) {
	// Remove ticks older than 2 seconds (60 ticks at 30fps)
	const uint64_t cleanup_threshold = 60;
	recent_ticks_.erase(
		std::remove_if(recent_ticks_.begin(), recent_ticks_.end(),
			[current_tick, cleanup_threshold](uint64_t tick) {
				return (current_tick - tick) > cleanup_threshold;
			}),
		recent_ticks_.end()
	);
}

int CompanionSeat::CountRecentIntents(uint64_t current_tick, int window_ticks) const {
	int count = 0;
	for (uint64_t tick : recent_ticks_) {
		if ((current_tick - tick) <= static_cast<uint64_t>(window_ticks)) {
			count++;
		}
	}
	return count;
}

} // namespace devilution

#endif // ENABLE_GAP