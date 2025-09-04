# GAP AI Chat Integration

**Real-time MCP agent communication via in-game chat** 

Now you can communicate with your MCP agent directly through Diablo's chat system! This includes both traditional commands AND natural LLM-powered conversation - your AI companion can chat with you while adventuring together!

## 🎉 NEW: Natural LLM Conversation

Beyond traditional commands, you can now have **natural conversations** with your AI companion:

```
Player: "How are you doing?"
AI: "I'm doing well, thanks for asking! Ready to explore the dungeon together!"

Player: "Do you see any monsters nearby?"  
AI: "No monsters in sight right now - looks like a safe area to chat!"

Player: "Let's head to the cathedral"
AI: "Sounds good! I'll follow your lead and watch for enemies."
```

**How it works:**
- Type any message in game chat (no special prefix needed)
- LLM sees your message and generates contextual responses  
- AI responds based on current game situation and conversation history
- Perfect for companion-mode gameplay where AI is your adventuring buddy!

**Features:**
- ✅ **Context-aware responses** - AI understands current game situation
- ✅ **Personalized conversation** - LLM generates unique responses to your specific questions
- ✅ **Graceful fallbacks** - System prioritizes chat responses when combat intents fail
- ✅ **Real-time processing** - No delays, immediate conversation flow
- ✅ **Message chunking** - Long responses automatically split for readability

## Quick Start

### For Natural LLM Conversation:
1. **Enable GAP mode**: Compile DevilutionX with `-DENABLE_GAP=ON`
2. **Start MCP server**: `python3 tools/gap/mcp_server.py --password foo`
3. **Start the game** with GAP enabled
4. **Open chat** (Enter key in-game) 
5. **Say anything**: "Hello!" or "How are you?" - the LLM will respond!

### For Traditional Commands:
4. **Type `!ai help`** to see available commands

## Available Commands

### Basic Commands
- **`!ai help`** - Show all available commands
- **`!ai status`** - Display current AI status and state
- **`!ai debug`** - Show debug information

### Configuration
- **`!ai config`** - Show current configuration
- **`!ai config enabled true/false`** - Enable/disable chat integration

### Control (Planned Features)
- **`!ai stop`** - Pause AI agent
- **`!ai start`** - Resume AI agent  
- **`!ai mode <combat/exploration/idle>`** - Set AI behavior mode
- **`!ai exec <command>`** - Execute direct AI commands

## Example Usage

```
Player: !ai help
[GAP AI] === GAP AI Chat Commands ===
[GAP AI] !ai status - Show current AI status
[GAP AI] !ai debug [args] - Debug information
[GAP AI] !ai config <key> <value> - Configure AI settings
[GAP AI] !ai help - Show this help

Player: !ai status
[GAP AI] GAP AI Status: Active and ready for commands

Player: !ai config enabled false
[GAP AI] Chat integration disabled.
```

## Features

### ✅ **Currently Working**
- **🆕 Natural LLM conversation** - Full bidirectional chat with context awareness
- **🆕 Intelligent responses** - LLM generates personalized replies to any message
- **🆕 Combat-aware chat** - AI responds appropriately based on current situation
- **Command parsing** - Recognizes `!ai` and `!gap` prefixes
- **Help system** - Built-in command documentation
- **Status reporting** - Basic AI status information
- **Configuration** - Enable/disable chat integration
- **Error handling** - Clear error messages for invalid commands
- **Color coding** - Blue for normal responses, red for errors

### 🚧 **Planned Features** 
- **Enhanced state display** - More detailed HP, position, enemy count via chat commands
- **Mode switching** - Toggle between combat/exploration/idle behaviors via `!ai mode`
- **Debug visualization** - Show pathfinding, decision trees, performance metrics
- **Agent pause/resume** - Stop/start the AI via `!ai stop/start` commands

## Technical Details

### Integration Points
- **Chat input hook**: Intercepts chat messages before network transmission
- **Command processing**: Parses `!ai` prefixed commands with arguments
- **Response system**: Uses DevilutionX's `EventPlrMsg()` for in-game display
- **Singleton pattern**: Single chat handler instance across game sessions

### Architecture
```
Game Chat → ProcessGAPChatCommand() → GAPChatHandler → AI Response
                                        ↓
                                    Command Dispatch
                                        ↓
                              [status|debug|config|help]
```

### Code Structure
- **`gap_chat.h`** - Interface definitions and command declarations
- **`gap_chat.cpp`** - Implementation of chat parsing and command handling  
- **`control.cpp`** - Integration hook in existing chat system
- **CMake integration** - Builds only when `ENABLE_GAP=ON`

## Development

### Adding New Commands

1. **Add handler method** to `GAPChatHandler` class
2. **Register command** in `ProcessChatMessage()` dispatch
3. **Implement functionality** in handler method
4. **Update help text** in `HandleHelpCommand()`

Example:
```cpp
void GAPChatHandler::HandleMyCommand(std::string_view args) {
    SendAIResponse("My command executed with: " + std::string(args));
}
```

### Integration with GAP State
To access current game state for advanced commands:
```cpp
#include "gap/gap_state.h"

void HandleAdvancedStatus() {
    auto state = ExtractCurrentState();
    // Process state data...
    SendAIResponse("Advanced status info");  
}
```

### Testing
- **Compile**: `make -j8` in build directory
- **Run game**: Start DevilutionX with GAP enabled
- **Test commands**: Use chat to verify command parsing and responses
- **Debug**: Check console output for any parsing errors

## Benefits for MCP Development

1. **Real-time monitoring** - See AI state without leaving the game
2. **Quick debugging** - Test commands and see immediate feedback
3. **Interactive control** - Dynamically adjust AI behavior during gameplay
4. **Development efficiency** - No need for external debugging tools
5. **User experience** - Natural integration with game interface

## Future Possibilities

- **Voice integration** - Combine with speech-to-text for voice commands
- **Multiplayer coordination** - AI agents communicate via chat
- **Scripting support** - Load and execute AI behavior scripts
- **Performance visualization** - Real-time graphs and metrics overlay
- **Learning feedback** - Rate AI decisions to improve behavior

---

This chat integration transforms the MCP agent from a background process into an interactive companion that you can communicate with naturally during gameplay! Combined with the new companion mode approach, your AI buddy becomes a true adventuring partner. 🎮🤖

## Companion Mode Integration

Perfect for the new **Local Character** companion approach:

- **Lead and chat**: You navigate, AI follows and provides conversational companionship
- **Tactical coordination**: "Watch out, archers ahead!" - AI responds and adapts
- **Character flexibility**: Switch which saved character the AI controls mid-game
- **Natural cooperation**: Human handles exploration, AI handles combat support and conversation

The bidirectional chat system makes AI companions feel like real adventuring partners rather than silent bots!