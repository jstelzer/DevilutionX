# GAP LLM Integration Tools

This directory contains tools for connecting Large Language Models (LLMs) to DevilutionX via the GAP protocol.

## 🤖 MCP Server (LLM Agent)

The `mcp_server.py` bridges the GAP protocol directly to Ollama, allowing LLMs to play Diablo with natural language decision-making.

### Prerequisites

1. **Build DevilutionX with GAP**: `cmake -DENABLE_GAP=ON` and compile
2. **Install Ollama**: Download from [ollama.ai](https://ollama.ai) 
3. **Install Python dependencies**:
   ```bash
   pip install aiohttp
   ```

### Usage

1. **Start DevilutionX** with a character loaded (preferably in dungeon for testing)

2. **Start Ollama** with your preferred model:
   ```bash
   ollama serve
   ollama pull llama3.2  # or your preferred model
   ```

3. **Run the MCP Server**:
   ```bash
   # Basic usage
   python3 mcp_server.py --password "your_password"
   
   # With personality
   python3 mcp_server.py --personality aggressive --password "your_password"
   
   # With custom model
   python3 mcp_server.py --model llama3.1 --personality cautious
   ```

### Available Options

```bash
--socket, -s        GAP socket path (default: /tmp/devilutionx-gap.sock)
--ollama-url        Ollama API URL (default: http://localhost:11434) 
--model, -m         Ollama model (default: llama3.2)
--personality       AI personality: balanced, cautious, aggressive, greedy
--password, -p      Password for multiplayer games
--verbose, -v       Enable debug logging
```

### Personalities

- **balanced** (default): Standard Diablo gameplay
- **cautious**: Prioritizes survival, retreats early, avoids risks  
- **aggressive**: Seeks combat, takes risks, fights multiple enemies
- **greedy**: Focuses on loot collection, efficient monster clearing

## 📋 Protocol Architecture

```
┌─────────────┐    GAP JSON     ┌─────────────┐    HTTP API    ┌─────────────┐
│   Diablo    │◄───────────────►│ MCP Server  │◄──────────────►│   Ollama    │
│   (GAP)     │                 │ (Proxy)     │                │   (LLM)     │
└─────────────┘                 └─────────────┘                └─────────────┘
```

- **Direct JSON**: No translation overhead - raw GAP state → LLM → GAP intents
- **Protocol-aware prompts**: LLM understands GAP specification via documentation
- **Structured decision-making**: LLM outputs valid GAP intent JSON directly

## 🧠 How It Works

1. **Game publishes state** in GAP JSON format (player, monsters, items, vision)
2. **MCP server** builds prompt with protocol docs + personality + current state
3. **LLM analyzes** the tactical situation and generates appropriate response
4. **Intent parsing** extracts valid GAP intent JSON from LLM response  
5. **Game executes** the LLM's decision (move, attack, etc.)

## 🎮 Example Session

```
Game State: Player at [45,50], Skeleton at [47,52], Health Potion at [44,49]
LLM Decision: {"type": "intent", "action": "attack", "params": {"x": 42, "y": -1}}
Game Action: Character attacks the skeleton
```

## 🐍 Python Testing Agents

- `test_gap_agent.py` - Basic movement patterns (existing)
- `combat_gap_agent.py` - Tactical combat AI with retreat logic (existing)
- `mcp_server.py` - LLM-powered agent via Ollama (new)

## 🔧 Development

### Adding New Personalities

Create `prompts/your_personality.txt` with behavior modifications:

```
## PERSONALITY: YOUR_NAME

**Core Principle**: Your guiding philosophy

### Behavior Modifications:
- Specific rule changes
- Decision priority adjustments  
- Risk tolerance modifications

### Decision Priorities:
1. Most important factor
2. Secondary consideration
3. etc.
```

Then use with: `--personality your_personality`

### Debugging

- Use `--verbose` for detailed logging
- Check Ollama logs: `ollama logs`
- Monitor GAP messages in DevilutionX console output

## ⚠️ Limitations

- Requires Ollama running locally 
- LLM response time: 200-2000ms depending on model/hardware
- Currently supports move and attack intents only (spells TODO)
- No inventory management yet (item pickup TODO)

## 🎯 Next Steps

1. Add spell casting support to GAP protocol
2. Implement item pickup/use intents  
3. Memory system for dungeon exploration
4. Multi-agent coordination for multiplayer