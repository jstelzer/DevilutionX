/**
 * @file gap_chat.cpp
 *
 * Implementation of GAP AI chat integration for MCP agent communication.
 */
#include "gap_chat.h"

#ifdef ENABLE_GAP

#include <algorithm>
#include <sstream>
#include <vector>
#include <ctime>
#include <iostream>

#include "plrmsg.h"
#include "DiabloUI/ui_flags.hpp"
#include "utils/str_cat.hpp"
#include "gap_core.h"
#include "gap_json.h"
#include "gap_state.h"  // For GAP_USE_DSL macro

namespace devilution {

namespace {

// Split string by whitespace
std::vector<std::string> SplitString(std::string_view str) {
    std::vector<std::string> result;
    std::string str_copy{str};
    std::istringstream iss{str_copy};
    std::string token;
    while (iss >> token) {
        result.push_back(token);
    }
    return result;
}

// Check if string starts with prefix (case insensitive)
bool StartsWith(std::string_view str, std::string_view prefix) {
    if (str.length() < prefix.length()) return false;
    return std::equal(prefix.begin(), prefix.end(), str.begin(),
                     [](char a, char b) { return std::tolower(a) == std::tolower(b); });
}

} // anonymous namespace

GAPChatHandler& GAPChatHandler::getInstance() {
    static GAPChatHandler instance;
    return instance;
}

bool GAPChatHandler::ProcessChatMessage(std::string_view message) {
    if (!enabled) {
        std::cout << "GAP: Chat handler disabled, ignoring message: '" << message << "'" << std::endl;
        return false;
    }
    
    // Ignore AI messages to prevent the AI from responding to itself
    if (StartsWith(message, "[GAP AI]")) {
        std::cout << "GAP: Ignoring AI message to prevent response loop: '" << message << "'" << std::endl;
        return false;
    }
    
    std::cout << "GAP: Processing chat message: '" << message << "'" << std::endl;
    
    // Log all player messages for GAP state tracking
    AddMessage(message, "player");
    
    // GAP commands start with "!ai" or "!gap"
    bool isGAPCommand = StartsWith(message, "!ai") || StartsWith(message, "!gap");
    if (!isGAPCommand) {
        std::cout << "GAP: Not a GAP command, sending as chat message to AI" << std::endl;
        // Send immediate chat message for AI awareness (non-GAP commands are for conversation)
        SendGAPChatMessage(message, "player");
        return false;  // Let normal chat messages go through to multiplayer
    }
    
    std::cout << "GAP: Detected GAP command, processing..." << std::endl;
    
    // Parse command
    auto parts = SplitString(message);
    if (parts.empty()) return false;
    
    std::string command = parts.size() > 1 ? parts[1] : "help";
    std::transform(command.begin(), command.end(), command.begin(), ::tolower);
    
    // Build arguments string
    std::string args;
    if (parts.size() > 2) {
        for (size_t i = 2; i < parts.size(); ++i) {
            if (i > 2) args += " ";
            args += parts[i];
        }
    }
    
    // Dispatch commands
    if (command == "status") {
        HandleStatusCommand();
    } else if (command == "debug") {
        HandleDebugCommand(args);
    } else if (command == "config") {
        HandleConfigCommand(args);
    } else if (command == "stop") {
        HandleStopCommand();
    } else if (command == "start") {
        HandleStartCommand();
    } else if (command == "mode") {
        HandleSetModeCommand(args);
    } else if (command == "exec" || command == "execute") {
        HandleExecuteCommand(args);
    } else if (command == "help" || command == "?") {
        HandleHelpCommand();
    } else {
        SendAIResponse(StrCat("Unknown command: ", command, ". Type '!ai help' for available commands."), true);
    }
    
    return true;
}

void GAPChatHandler::SendAIResponse(std::string_view response, bool isError) {
    std::string fullMessage = StrCat("[GAP AI] ", response);
    UiFlags color = isError ? UiFlags::ColorRed : UiFlags::ColorBlue;
    EventPlrMsg(fullMessage, color);
    
    // Log AI responses for GAP state tracking
    AddMessage(fullMessage, "ai");
}

void GAPChatHandler::SetEnabled(bool enabled) {
    this->enabled = enabled;
    if (enabled) {
        SendAIResponse("Chat integration enabled. Type '!ai help' for commands.");
    } else {
        SendAIResponse("Chat integration disabled.");
    }
}

bool GAPChatHandler::IsEnabled() const {
    return enabled;
}

void GAPChatHandler::AddMessage(std::string_view text, std::string_view from) {
    GAPChatMessage msg;
    msg.text = std::string(text);
    msg.from = std::string(from);
    msg.timestamp = static_cast<uint32_t>(time(nullptr) * 1000); // milliseconds
    
    chatHistory.push_back(msg);
    
    std::cout << "GAP: Chat message added - From: '" << from << "', Text: '" << text << "'" << std::endl;
    
    // Keep only recent messages
    if (chatHistory.size() > MAX_CHAT_HISTORY) {
        chatHistory.erase(chatHistory.begin(), chatHistory.begin() + (chatHistory.size() - MAX_CHAT_HISTORY));
    }
}

std::vector<GAPChatMessage> GAPChatHandler::GetRecentMessages(size_t maxMessages) const {
    std::vector<GAPChatMessage> recent;
    
    // Only return messages from last 30 seconds (30000 milliseconds)
    uint32_t currentTime = static_cast<uint32_t>(time(nullptr) * 1000);
    uint32_t cutoffTime = currentTime - 30000;  // 30 seconds ago
    
    // Start from the end and work backwards to get most recent messages first
    for (int i = static_cast<int>(chatHistory.size()) - 1; i >= 0 && recent.size() < maxMessages; i--) {
        const auto& msg = chatHistory[i];
        if (msg.timestamp >= cutoffTime) {
            recent.insert(recent.begin(), msg);  // Insert at beginning to maintain chronological order
        } else {
            break;  // Older messages, stop looking
        }
    }
    
    return recent;
}

void GAPChatHandler::HandleStatusCommand() {
    SendAIResponse("GAP AI Status: Active and ready for commands");
}

void GAPChatHandler::HandleDebugCommand(std::string_view args) {
    if (args.empty()) {
        SendAIResponse("Debug info: GAP AI chat integration active");
        return;
    }
    
    SendAIResponse(StrCat("Debug command: ", args, " (not yet implemented)"));
}

void GAPChatHandler::HandleConfigCommand(std::string_view args) {
    if (args.empty()) {
        SendAIResponse("Config: enabled=" + std::string(enabled ? "true" : "false"));
        return;
    }
    
    auto parts = SplitString(args);
    if (parts.size() < 2) {
        SendAIResponse("Usage: !ai config <key> <value>", true);
        return;
    }
    
    std::string key = parts[0];
    std::string value = parts[1];
    
    if (key == "enabled") {
        bool newEnabled = (value == "true" || value == "1" || value == "on");
        SetEnabled(newEnabled);
    } else {
        SendAIResponse(StrCat("Unknown config key: ", key), true);
    }
}

void GAPChatHandler::HandleStopCommand() {
    SendAIResponse("AI pause requested (feature not yet implemented)");
}

void GAPChatHandler::HandleStartCommand() {
    SendAIResponse("AI resume requested (feature not yet implemented)");
}

void GAPChatHandler::HandleHelpCommand() {
    SendAIResponse("=== GAP AI Chat Commands ===");
    SendAIResponse("!ai status - Show current AI status");
    SendAIResponse("!ai debug [args] - Debug information");
    SendAIResponse("!ai config <key> <value> - Configure AI settings");
    SendAIResponse("!ai stop/start - Pause/resume AI (planned)");
    SendAIResponse("!ai mode <mode> - Set AI behavior mode (planned)");
    SendAIResponse("!ai exec <command> - Execute AI command (planned)");
    SendAIResponse("!ai help - Show this help");
}

void GAPChatHandler::HandleSetModeCommand(std::string_view mode) {
    if (mode.empty()) {
        SendAIResponse("Available modes: combat, exploration, idle (not yet implemented)");
        return;
    }
    
    SendAIResponse(StrCat("Mode set request: ", mode, " (feature not yet implemented)"));
}

void GAPChatHandler::HandleExecuteCommand(std::string_view command) {
    if (command.empty()) {
        SendAIResponse("Usage: !ai exec <action> [params] (feature not yet implemented)", true);
        return;
    }
    
    SendAIResponse(StrCat("Execute command: ", command, " (feature not yet implemented)"));
}

void GAPChatHandler::SendGAPChatMessage(std::string_view text, std::string_view from) {
    auto& gapCore = gap::GapCore::Instance();
    if (!gapCore.IsEnabled()) {
        std::cout << "GAP: Core not enabled, cannot send chat message" << std::endl;
        return;
    }

#if GAP_USE_DSL
    // DSL mode: Send compact chat notification
    std::string message = StrCat("CHAT ", from, ": ", text);
    std::cout << "GAP DSL: Sending chat: " << message << std::endl;
    gapCore.SendMessage(message);
#else
    // JSON mode: Create chat message JSON
    gap::JsonBuilder chatMessage;
    chatMessage.BeginObject()
        .AddString("type", "chat")
        .AddString("text", std::string(text))
        .AddString("from", std::string(from))
        .AddUInt("timestamp", static_cast<uint32_t>(time(nullptr) * 1000))
        .EndObject();

    std::string message = chatMessage.ToString();
    std::cout << "GAP: Sending chat message: " << message << std::endl;
    gapCore.SendMessage(message);
#endif
}

// Global function for integration with existing chat system
bool ProcessGAPChatCommand(std::string_view message) {
    return GAPChatHandler::getInstance().ProcessChatMessage(message);
}

} // namespace devilution

#endif // ENABLE_GAP