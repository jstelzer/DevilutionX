/**
 * @file gap_stores.h
 *
 * GAP Headless Store Protocol - API for AI companions to buy/sell/repair without UI
 */
#pragma once

#ifdef ENABLE_GAP

#include <vector>
#include <string>
#include "../items.h"
#include "../towners.h"
#include "../player.h"

namespace devilution::gap {

/**
 * Represents a store item for DSL encoding and headless purchase
 */
struct StoreItem {
    int itemIndex;        // Index into store array (for purchase)
    int price;           // Gold cost
    ItemType type;       // Item type enum
    std::string typeCode; // DSL type code (sw, ax, hp, etc.)
    char quality;        // 'n'=normal, 'm'=magic, 'u'=unique
    std::string name;    // Item name for debugging
};

/**
 * Get store inventory for a specific NPC
 *
 * Returns all items currently available for purchase at this vendor.
 * Used for DSL state encoding (ST_sm=..., ST_hl=..., etc.)
 *
 * @param npcType TOWN_SMITH, TOWN_HEALER, TOWN_WITCH, TOWN_PEGBOY
 * @return Vector of purchasable items
 */
std::vector<StoreItem> GetStoreInventory(_talker_id npcType);

/**
 * Companion purchases item from vendor (headless - no UI)
 *
 * Backend flow:
 * 1. Validate companion near NPC (distance <= 2)
 * 2. Check companion has sufficient gold
 * 3. Check companion has inventory space
 * 4. Execute purchase (deduct gold, add item)
 *
 * @param companion Player reference (must be companion, not MyPlayer)
 * @param npcType Which vendor (TOWN_SMITH, TOWN_HEALER, etc.)
 * @param itemIndex Index into vendor's store array
 * @return true if purchase successful
 */
bool CompanionBuyItem(Player& companion, _talker_id npcType, int itemIndex);

/**
 * Companion sells item from inventory (headless)
 *
 * Calculates sell price using same formula as UI, removes item,
 * adds gold to companion.
 *
 * @param companion Player reference
 * @param invSlot Inventory slot index (0-based)
 * @return true if sale successful
 */
bool CompanionSellItem(Player& companion, int invSlot);

/**
 * Companion repairs equipped item at Smith (headless)
 *
 * Uses same repair cost calculation as UI.
 *
 * @param companion Player reference
 * @param invSlot Equipment slot to repair
 * @return true if repair successful
 */
bool CompanionRepairItem(Player& companion, int invSlot);

/**
 * Companion identifies item at Cain's (headless)
 *
 * @param companion Player reference
 * @param invSlot Inventory slot containing unidentified item
 * @return true if identification successful
 */
bool CompanionIdentifyItem(Player& companion, int invSlot);

/**
 * Get item type code for DSL encoding
 * Helper function to convert ItemType to 2-char code
 *
 * @param type ItemType enum
 * @return DSL code like "sw", "ax", "hp", etc.
 */
std::string GetItemTypeCode(ItemType type);

/**
 * Get item quality code for DSL encoding
 *
 * @param item Item reference
 * @return 'n' (normal), 'm' (magic), or 'u' (unique)
 */
char GetItemQualityCode(const Item& item);

} // namespace devilution::gap

#endif // ENABLE_GAP
