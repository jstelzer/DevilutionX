#pragma once

#ifdef ENABLE_GAP

#include "seat/seat.h"
#include <queue>
#include <chrono>

namespace devilution {

/**
 * @brief AI companion seat that processes GAP protocol intents
 * 
 * CompanionSeat receives intents from the GAP protocol (LLM/AI agents)
 * and provides them through the unified Seat interface. It includes
 * rate limiting, survival reflexes, and safety measures to prevent
 * spam or dangerous AI behavior.
 */
class CompanionSeat : public Seat {
public:
	explicit CompanionSeat(int player_index);
	~CompanionSeat() override = default;

	// Seat interface
	int GetPlayerIndex() const override { return player_index_; }
	bool IsActive() const override;
	void GatherIntents(std::vector<Intent>& out, uint64_t tick) override;
	void PostProcess(uint64_t tick) override;
	bool CanControlUI() const override { return false; } // AI never controls UI
	const char* GetTypeName() const override { return "Companion"; }

	// CompanionSeat-specific methods
	void EnqueueIntent(const Intent& intent);
	void ClearQueue();
	bool IsOverloaded() const;
	
	// Safety and survival methods
	void EnableSurvivalReflexes(bool enable) { survival_reflexes_enabled_ = enable; }
	void SetRateLimits(int max_per_tick, int max_per_second);

private:
	int player_index_;
	uint64_t last_tick_;
	
	// Intent queue with rate limiting
	std::queue<Intent> intent_queue_;
	static constexpr size_t MAX_QUEUE_SIZE = 50;
	
	// Rate limiting
	int max_intents_per_tick_ = 3;        // Reduced from base class default
	int max_intents_per_second_ = 8;      // Conservative rate limiting
	std::vector<uint64_t> recent_ticks_;  // Track recent activity
	
	// Survival reflexes
	bool survival_reflexes_enabled_ = true;
	uint64_t last_health_check_ = 0;
	uint64_t last_emergency_action_ = 0;
	
	// Safety measures
	bool ShouldApplyRateLimit(uint64_t tick) const;
	bool ShouldApplySurvivalOverride(uint64_t tick);
	void ApplyEmergencyHealing(std::vector<Intent>& out, uint64_t tick);
	void ApplyEmergencyRetreat(std::vector<Intent>& out, uint64_t tick);
	
	// Intent processing helpers
	void ProcessQueuedIntents(std::vector<Intent>& out, uint64_t tick);
	void FilterDangerousIntents(std::vector<Intent>& intents);
	void PrioritizeIntents(std::vector<Intent>& intents);
	
	// Utility methods
	void CleanupOldTicks(uint64_t current_tick);
	int CountRecentIntents(uint64_t current_tick, int window_ticks) const;
};

} // namespace devilution

#endif // ENABLE_GAP