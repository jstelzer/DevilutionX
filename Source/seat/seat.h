#pragma once

#ifdef ENABLE_GAP

#include <vector>
#include <memory>
#include <cstdint>

namespace devilution {

// Forward declarations - avoid conflicts, use int coordinates
template<class CoordT>
class PointOf;

/**
 * @brief Intent represents a desired game action from any input source
 * 
 * Intents are the unified abstraction between input sources (human, AI)
 * and game actions (movement, combat, inventory, etc.)
 */
struct Intent {
	enum class Type {
		Move,      // Move to position
		Attack,    // Attack target (monster ID or position)
		Interact,  // Interact with object
		UseItem,   // Use inventory item
		Cast,      // Cast spell
		Chat       // Send chat message
	};

	Type type;
	uint64_t timestamp;  // Game tick when intent was created
	
	// Intent parameters (union-like approach)
	struct {
		int x, y;           // Position or target coordinates
		int param1, param2; // Additional parameters (item ID, spell ID, etc.)
		std::string text;   // For chat messages
	} data;

	// Default constructor
	Intent() : type(Type::Move), timestamp(0) {
		data.x = 0;
		data.y = 0;
		data.param1 = 0;
		data.param2 = 0;
	}

	Intent(Type t, uint64_t tick, int x = 0, int y = 0, int p1 = 0, int p2 = 0) 
		: type(t), timestamp(tick) {
		data.x = x;
		data.y = y;
		data.param1 = p1;
		data.param2 = p2;
	}

	Intent(Type t, uint64_t tick, const std::string& message)
		: type(t), timestamp(tick) {
		data.x = 0;
		data.y = 0;
		data.param1 = 0;
		data.param2 = 0;
		data.text = message;
	}
};

/**
 * @brief Base class for all input sources (human, AI companion, etc.)
 * 
 * A Seat represents a control interface for a player slot. It gathers
 * intents from its input source and provides them to the game engine
 * for execution.
 */
class Seat {
public:
	virtual ~Seat() = default;

	/**
	 * @brief Get the player index this seat controls
	 * @return Player index (0-3 for multiplayer slots)
	 */
	virtual int GetPlayerIndex() const = 0;

	/**
	 * @brief Check if this seat is active and should process input
	 * @return true if seat should be polled for intents
	 */
	virtual bool IsActive() const = 0;

	/**
	 * @brief Gather intents from input source for this game tick
	 * @param out Vector to append intents to
	 * @param tick Current game tick
	 */
	virtual void GatherIntents(std::vector<Intent>& out, uint64_t tick) = 0;

	/**
	 * @brief Called after intents are processed - cleanup/state update
	 * @param tick Current game tick
	 */
	virtual void PostProcess(uint64_t tick) {}

	/**
	 * @brief Check if this seat can steal UI focus (human seats only)
	 * @return true if seat can control UI focus, false for AI seats
	 */
	virtual bool CanControlUI() const = 0;

	/**
	 * @brief Get seat type name for debugging
	 * @return Human-readable seat type name
	 */
	virtual const char* GetTypeName() const = 0;

	// Rate limiting constants (public for SeatManager access)
	static constexpr int MAX_INTENTS_PER_TICK = 5;
	static constexpr int MAX_INTENTS_PER_SECOND = 10;

protected:
	// Rate limiting helpers
	
	bool ShouldRateLimit(uint64_t tick, int intent_count) const {
		// Simple rate limiting - more sophisticated logic in derived classes
		return intent_count > MAX_INTENTS_PER_TICK;
	}
};

/**
 * @brief Manages all seats and coordinates intent processing
 * 
 * The SeatManager is responsible for polling all active seats,
 * collecting their intents, and executing them through the
 * existing game command system.
 */
class SeatManager {
public:
	static SeatManager& Instance() {
		static SeatManager instance;
		return instance;
	}

	/**
	 * @brief Register a seat for a player slot
	 * @param seat Smart pointer to seat implementation
	 */
	void RegisterSeat(std::unique_ptr<Seat> seat);

	/**
	 * @brief Remove seat for a player slot
	 * @param player_index Player slot to clear
	 */
	void UnregisterSeat(int player_index);

	/**
	 * @brief Process all seat intents for this game tick
	 * @param tick Current game tick
	 * @return true if game logic should continue, false if should exit early (mirrors ProcessInput)
	 */
	bool ProcessAllIntents(uint64_t tick);

	/**
	 * @brief Get seat for specific player (for debugging/queries)
	 * @param player_index Player slot
	 * @return Seat pointer or nullptr if no seat registered
	 */
	Seat* GetSeat(int player_index) const;

	/**
	 * @brief Check if any seat is active
	 * @return true if at least one seat is registered and active
	 */
	bool HasActiveSeats() const;

	/**
	 * @brief Clear all seats (for cleanup)
	 */
	void Clear();

private:
	SeatManager() = default;
	~SeatManager() = default;

	// Non-copyable, non-movable singleton
	SeatManager(const SeatManager&) = delete;
	SeatManager& operator=(const SeatManager&) = delete;

	std::unique_ptr<Seat> seats_[4]; // One seat per player slot
	
	// Intent processing helpers
	void ExecuteIntent(const Intent& intent, int player_index, uint64_t tick);
	void ExecuteMoveIntent(const Intent& intent, int player_index);
	void ExecuteAttackIntent(const Intent& intent, int player_index);
	void ExecuteInteractIntent(const Intent& intent, int player_index);
	void ExecuteItemIntent(const Intent& intent, int player_index);
	void ExecuteCastIntent(const Intent& intent, int player_index);
	void ExecuteChatIntent(const Intent& intent, int player_index);
};

} // namespace devilution

#endif // ENABLE_GAP