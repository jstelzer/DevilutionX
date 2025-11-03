#pragma once

#include "../engine/point.hpp"
#include "../msg.h"
#include <cstdint>

namespace devilution::gap {

// Network command routing fix for companion control
// These functions ensure commands execute on the correct player slot
// bypassing the normal network routing assumptions

void NetSendCmdLocForPlayer(int actual_player_id, bool bHiPri, _cmd_id bCmd, Point position);
void NetSendCmdParam1ForPlayer(int actual_player_id, bool bHiPri, _cmd_id bCmd, uint16_t wParam1);

// Direct execution functions that bypass network routing for local companions
bool ExecuteDirectMove(int player_id, Point target);
bool ExecuteDirectAttack(int player_id, int monster_id);
bool ExecutePositionAttack(int player_id, int target_x, int target_y);  // Find monster at position and attack
bool ExecuteDirectInteract(int player_id, Point position);
bool ExecuteDirectPickup(int player_id, int item_id);

} // namespace devilution::gap