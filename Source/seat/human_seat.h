#pragma once

#ifdef ENABLE_GAP

#include "seat/seat.h"

namespace devilution {

/**
 * @brief Human player seat that wraps existing input processing
 * 
 * HumanSeat is a thin wrapper around the existing input system to
 * provide the same behavior through the new Seat abstraction.
 * This allows us to test the seat infrastructure while maintaining
 * perfect compatibility with existing gameplay.
 */
class HumanSeat : public Seat {
public:
	explicit HumanSeat(int player_index);
	~HumanSeat() override = default;

	// Seat interface
	int GetPlayerIndex() const override { return player_index_; }
	bool IsActive() const override;
	void GatherIntents(std::vector<Intent>& out, uint64_t tick) override;
	void PostProcess(uint64_t tick) override;
	bool CanControlUI() const override { return true; }
	const char* GetTypeName() const override { return "Human"; }
	
	// HumanSeat-specific methods
	bool ShouldExitEarly() const;

private:
	int player_index_;
	uint64_t last_input_tick_;
	
	// Input processing helpers
	void ProcessKeyboardMouse(std::vector<Intent>& out, uint64_t tick);
	void ProcessGamepad(std::vector<Intent>& out, uint64_t tick);
	
	// Intent generation from existing input functions
	void GenerateMovementIntents(std::vector<Intent>& out, uint64_t tick);
	void GenerateActionIntents(std::vector<Intent>& out, uint64_t tick);
	void GenerateInventoryIntents(std::vector<Intent>& out, uint64_t tick);
	void GenerateChatIntents(std::vector<Intent>& out, uint64_t tick);
};

} // namespace devilution

#endif // ENABLE_GAP