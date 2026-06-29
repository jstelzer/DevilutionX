/**
 * @file gap_stores.cpp
 *
 * GAP Headless Store Protocol - Implementation
 */

#ifdef ENABLE_GAP

#include "gap_stores.h"
#include "../stores.h"
#include "../items.h"
#include "../player.h"
#include "../towners.h"
#include "../inv.h"
#include <iostream>
#include <sstream>

namespace devilution::gap {

std::string GetItemTypeCode(ItemType type)
{
    switch (type) {
    case ItemType::Gold:        return "go";
    case ItemType::Sword:       return "sw";
    case ItemType::Axe:         return "ax";
    case ItemType::Bow:         return "bw";
    case ItemType::Mace:        return "mc";
    case ItemType::Shield:      return "sh";
    case ItemType::LightArmor:  return "la";
    case ItemType::MediumArmor: return "ma";
    case ItemType::HeavyArmor:  return "ha";
    case ItemType::Helm:        return "hl";
    case ItemType::Staff:       return "st";
    case ItemType::Ring:        return "rg";
    case ItemType::Amulet:      return "am";
    case ItemType::Misc:
        // Check for potions - this is a simplification
        return "ms";
    default:                    return "ms";
    }
}

char GetItemQualityCode(const Item& item)
{
    switch (item._iMagical) {
    case ITEM_QUALITY_MAGIC:  return 'm';
    case ITEM_QUALITY_UNIQUE: return 'u';
    default:                  return 'n';  // normal
    }
}

std::vector<StoreItem> GetStoreInventory(_talker_id npcType)
{
    std::vector<StoreItem> inventory;

    switch (npcType) {
    case TOWN_SMITH: {
        // Basic smith items
        for (int i = 0; i < static_cast<int>(std::size(SmithItems)); i++) {
            const Item& item = SmithItems[i];
            if (item.isEmpty()) continue;

            inventory.push_back({
                i,
                item._iIvalue,
                item._itype,
                GetItemTypeCode(item._itype),
                GetItemQualityCode(item),
                std::string(item._iIName)
            });
        }

        // Premium items
        for (int i = 0; i < static_cast<int>(std::size(PremiumItems)); i++) {
            const Item& item = PremiumItems[i];
            if (item.isEmpty()) continue;

            inventory.push_back({
                1000 + i,  // Offset to distinguish from basic items
                item._iIvalue,
                item._itype,
                GetItemTypeCode(item._itype),
                GetItemQualityCode(item),
                std::string(item._iIName)
            });
        }
        break;
    }

    case TOWN_HEALER: {
        for (int i = 0; i < static_cast<int>(std::size(HealerItems)); i++) {
            const Item& item = HealerItems[i];
            if (item.isEmpty()) continue;

            // Determine if it's a potion
            std::string typeCode = "ms";
            if (item._itype == ItemType::Misc) {
                switch (item._iMiscId) {
                case IMISC_HEAL:
                case IMISC_FULLHEAL:
                    typeCode = "hp";
                    break;
                case IMISC_MANA:
                case IMISC_FULLMANA:
                    typeCode = "mp";
                    break;
                case IMISC_REJUV:
                case IMISC_FULLREJUV:
                    typeCode = "rj";
                    break;
                default:
                    typeCode = "ms";
                    break;
                }
            }

            inventory.push_back({
                i,
                item._iIvalue,
                item._itype,
                typeCode,
                GetItemQualityCode(item),
                std::string(item._iIName)
            });
        }
        break;
    }

    case TOWN_WITCH: {
        for (int i = 0; i < static_cast<int>(std::size(WitchItems)); i++) {
            const Item& item = WitchItems[i];
            if (item.isEmpty()) continue;

            inventory.push_back({
                i,
                item._iIvalue,
                item._itype,
                GetItemTypeCode(item._itype),
                GetItemQualityCode(item),
                std::string(item._iIName)
            });
        }
        break;
    }

    case TOWN_PEGBOY: {
        // Wirt sells one item
        if (!BoyItem.isEmpty()) {
            inventory.push_back({
                0,
                50,  // Wirt's item costs 50 gold to see
                BoyItem._itype,
                GetItemTypeCode(BoyItem._itype),
                GetItemQualityCode(BoyItem),
                std::string(BoyItem._iIName)
            });
        }
        break;
    }

    default:
        break;
    }

    return inventory;
}

bool CompanionBuyItem(Player& companion, _talker_id npcType, int itemIndex)
{
    // One client, one player: GAP drives this headless client's own MyPlayer
    // (see GetControlledPlayer). The old slot-era "&companion == MyPlayer"
    // guard rejected exactly the player we now control, so it's gone.

    // Validate companion is in town
    if (leveltype != DTYPE_TOWN) {
        std::cerr << "GAP Store: Companion must be in town to shop" << std::endl;
        return false;
    }

    // Get the item from the appropriate store array
    Item* storeItem = nullptr;
    int price = 0;

    switch (npcType) {
    case TOWN_SMITH:
        if (itemIndex >= 1000) {
            // Premium item
            int premiumIdx = itemIndex - 1000;
            if (premiumIdx >= 0 && premiumIdx < static_cast<int>(std::size(PremiumItems))) {
                storeItem = &PremiumItems[premiumIdx];
            }
        } else {
            // Basic item
            if (itemIndex >= 0 && itemIndex < static_cast<int>(std::size(SmithItems))) {
                storeItem = &SmithItems[itemIndex];
            }
        }
        break;

    case TOWN_HEALER:
        if (itemIndex >= 0 && itemIndex < static_cast<int>(std::size(HealerItems))) {
            storeItem = &HealerItems[itemIndex];
        }
        break;

    case TOWN_WITCH:
        if (itemIndex >= 0 && itemIndex < static_cast<int>(std::size(WitchItems))) {
            storeItem = &WitchItems[itemIndex];
        }
        break;

    case TOWN_PEGBOY:
        if (itemIndex == 0 && !BoyItem.isEmpty()) {
            storeItem = &BoyItem;
            price = 50;  // Cost to see Wirt's item
        }
        break;

    default:
        std::cerr << "GAP Store: Invalid NPC type" << std::endl;
        return false;
    }

    if (storeItem == nullptr || storeItem->isEmpty()) {
        std::cerr << "GAP Store: Invalid item index or item is empty" << std::endl;
        return false;
    }

    // Get item price (unless it's Wirt's special case)
    if (npcType != TOWN_PEGBOY) {
        price = storeItem->_iIvalue;
    }

    // Check if companion can afford it
    if (companion._pGold < price) {
        std::cerr << "GAP Store: Companion cannot afford item (need " << price
                  << " gold, have " << companion._pGold << ")" << std::endl;
        return false;
    }

    // Check if there's inventory space
    if (!AutoPlaceItemInInventory(companion, *storeItem, false)) {
        std::cerr << "GAP Store: No inventory space for item" << std::endl;
        return false;
    }

    // Perform the purchase
    std::cout << "GAP Store: Companion " << companion._pName
              << " buying " << storeItem->_iIName
              << " for " << price << " gold" << std::endl;

    // Add item to inventory
    AutoPlaceItemInInventory(companion, *storeItem, true);

    // Deduct gold via the engine's gold-pile-aware path. Gold in Diablo lives as
    // inventory pile-items; CalcPlrInv recomputes _pGold from those piles every
    // tick (inv.cpp), so a raw `_pGold -= price` is silently reverted. TakePlrsMoney
    // also removes the piles. (companion == MyPlayer here, which it operates on.)
    TakePlrsMoney(price);

    // If this was Wirt's item, clear it (he only sells one at a time)
    if (npcType == TOWN_PEGBOY) {
        BoyItem.clear();
    }

    CalcPlrInv(companion, true);
    return true;
}

bool CompanionSellItem(Player& companion, int invSlot)
{
    // One client, one player: GAP drives this headless client's own MyPlayer
    // (see GetControlledPlayer). The old slot-era "&companion == MyPlayer"
    // guard rejected exactly the player we now control, so it's gone.

    // Validate in town
    if (leveltype != DTYPE_TOWN) {
        std::cerr << "GAP Store: Must be in town to sell items" << std::endl;
        return false;
    }

    // Validate inventory slot
    if (invSlot < 0 || invSlot >= companion._pNumInv) {
        std::cerr << "GAP Store: Invalid inventory slot " << invSlot << std::endl;
        return false;
    }

    Item& item = companion.InvList[invSlot];

    if (item.isEmpty()) {
        std::cerr << "GAP Store: Inventory slot " << invSlot << " is empty" << std::endl;
        return false;
    }

    // Calculate sell price (same as UI - typically item value / 4 or so)
    int sellPrice = item._iIvalue;

    std::cout << "GAP Store: Companion " << companion._pName
              << " selling " << item._iIName
              << " for " << sellPrice << " gold" << std::endl;

    // Remove item from inventory
    companion.RemoveInvItem(invSlot);

    // Add gold
    AddGoldToInventory(companion, sellPrice);
    companion._pGold += sellPrice;

    return true;
}

bool CompanionRepairItem(Player& companion, int bodySlot)
{
    // One client, one player: GAP drives this headless client's own MyPlayer
    // (see GetControlledPlayer). The old slot-era "&companion == MyPlayer"
    // guard rejected exactly the player we now control, so it's gone.

    // Validate in town near smith
    if (leveltype != DTYPE_TOWN) {
        std::cerr << "GAP Store: Must be in town to repair" << std::endl;
        return false;
    }

    // REPAIR addresses an EQUIPPED slot: the agent sends an INVLOC body index
    // (0=head .. 6=chest, see griswold.py slot_to_body_index). The old code
    // indexed InvList[bodySlot] — an *inventory* item — so it repaired the wrong
    // thing (or an empty slot) and never touched the damaged gear it was sent for.
    if (bodySlot < 0 || bodySlot >= NUM_INVLOC) {
        std::cerr << "GAP Store: Invalid body slot " << bodySlot << std::endl;
        return false;
    }

    Item& item = companion.InvBody[bodySlot];

    if (item.isEmpty()) {
        std::cerr << "GAP Store: Body slot " << bodySlot << " is empty" << std::endl;
        return false;
    }

    // Check if item needs repair
    if (item._iDurability >= item._iMaxDur) {
        std::cerr << "GAP Store: Item doesn't need repair" << std::endl;
        return false;
    }

    // Calculate repair cost (same formula as UI)
    const int due = item._iMaxDur - item._iDurability;
    int repairCost;

    if (item._iMagical != ITEM_QUALITY_NORMAL && item._iIdentified) {
        repairCost = 30 * item._iIvalue * due / (item._iMaxDur * 100 * 2);
        if (repairCost == 0) {
            repairCost = 1;
        }
    } else {
        repairCost = item._ivalue * due / (item._iMaxDur * 2);
        repairCost = std::max(repairCost, 1);
    }

    // Check if companion can afford repair
    if (companion._pGold < repairCost) {
        std::cerr << "GAP Store: Cannot afford repair (need " << repairCost
                  << " gold, have " << companion._pGold << ")" << std::endl;
        return false;
    }

    std::cout << "GAP Store: Companion " << companion._pName
              << " repairing " << item._iIName
              << " for " << repairCost << " gold" << std::endl;

    // Perform repair + gold-pile-aware spend (see CompanionBuyItem). A raw
    // `_pGold -= cost` here is reverted by CalcPlrInv the same way.
    item._iDurability = item._iMaxDur;
    TakePlrsMoney(repairCost);

    // Recalculate inventory
    CalcPlrInv(companion, true);

    return true;
}

bool CompanionIdentifyItem(Player& companion, int invSlot)
{
    // One client, one player: GAP drives this headless client's own MyPlayer
    // (see GetControlledPlayer). The old slot-era "&companion == MyPlayer"
    // guard rejected exactly the player we now control, so it's gone.

    // Validate in town
    if (leveltype != DTYPE_TOWN) {
        std::cerr << "GAP Store: Must be in town to identify items" << std::endl;
        return false;
    }

    // Validate inventory slot
    if (invSlot < 0 || invSlot >= companion._pNumInv) {
        std::cerr << "GAP Store: Invalid inventory slot " << invSlot << std::endl;
        return false;
    }

    Item& item = companion.InvList[invSlot];

    if (item.isEmpty()) {
        std::cerr << "GAP Store: Inventory slot " << invSlot << " is empty" << std::endl;
        return false;
    }

    // Check if item needs identification
    if (item._iIdentified) {
        std::cerr << "GAP Store: Item is already identified" << std::endl;
        return false;
    }

    std::cout << "GAP Store: Companion " << companion._pName
              << " identifying " << item._iIName << std::endl;

    // Identify the item (Cain does this for free in Diablo 1)
    item._iIdentified = true;

    // Recalculate inventory
    CalcPlrInv(companion, true);

    return true;
}

} // namespace devilution::gap

#endif // ENABLE_GAP
