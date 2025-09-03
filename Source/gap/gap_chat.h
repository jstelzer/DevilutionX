/**
 * @file gap_chat.h
 *
 * Interface for GAP AI chat integration - allows MCP agent communication via in-game chat.
 */
#pragma once

#include <string>
#include <string_view>
#include <functional>
#include <cstdint>
#include <vector>

namespace devilution {

/**
 * Chat Message for GAP state tracking
 */
struct GAPChatMessage {
    std::string text;
    std::string from;  // "player", "ai", "system"
    uint32_t timestamp;
};

/**
 * GAP Chat Command Handler - processes chat commands directed at the AI agent
 */
class GAPChatHandler {
public:
    static GAPChatHandler& getInstance();
    
    /**
     * Process a chat message and check if it's a GAP command
     * @param message The chat message to process
     * @return true if message was handled as GAP command, false otherwise
     */
    bool ProcessChatMessage(std::string_view message);
    
    /**
     * Send a response from the AI agent to the chat
     * @param response The AI's response message
     * @param isError If true, display in error color
     */
    void SendAIResponse(std::string_view response, bool isError = false);
    
    /**
     * Enable/disable GAP chat integration
     * @param enabled Whether chat integration should be active
     */
    void SetEnabled(bool enabled);
    
    /**
     * Check if GAP chat integration is enabled
     * @return true if chat integration is active
     */
    bool IsEnabled() const;
    
    /**
     * Add a message to the chat history (for GAP state tracking)
     * @param text The message text
     * @param from Who sent it ("player", "ai", "system")
     */
    void AddMessage(std::string_view text, std::string_view from);
    
    /**
     * Get recent chat messages for GAP state
     * @param maxMessages Maximum number of recent messages to return
     * @return Vector of recent chat messages
     */
    std::vector<GAPChatMessage> GetRecentMessages(size_t maxMessages = 10) const;
    
    /**
     * Send a chat message immediately via GAP (separate from state messages)
     * @param text The message text
     * @param from Who sent it ("player", "ai", "system")
     */
    void SendGAPChatMessage(std::string_view text, std::string_view from);

private:
    GAPChatHandler() = default;
    
    bool enabled = true;
    std::vector<GAPChatMessage> chatHistory;
    static constexpr size_t MAX_CHAT_HISTORY = 50;
    
    // Command handlers
    void HandleStatusCommand();
    void HandleDebugCommand(std::string_view args);
    void HandleConfigCommand(std::string_view args);
    void HandleStopCommand();
    void HandleStartCommand();
    void HandleHelpCommand();
    void HandleSetModeCommand(std::string_view mode);
    void HandleExecuteCommand(std::string_view command);
};

// Integration hook for existing chat system
bool ProcessGAPChatCommand(std::string_view message);

} // namespace devilution