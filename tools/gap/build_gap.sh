#!/bin/bash
# Build script for DevilutionX with GAP enabled

echo "Building DevilutionX with GAP (Game Agent Protocol) support..."
echo

# Create build directory if it doesn't exist
mkdir -p build
cd build

# Configure with GAP enabled
echo "Configuring with GAP enabled..."
#cmake -DENABLE_GAP=ON -DCMAKE_BUILD_TYPE=Debug -DASAN=OFF -DUBSAN=OFF -DCMAKE_INSTALL_PREFIX="$HOME/.local/devilutionx" ..
cmake -DENABLE_GAP=ON -DCMAKE_BUILD_TYPE=Release -DASAN=OFF -DUBSAN=OFF -DCMAKE_INSTALL_PREFIX="$HOME/.local/devilutionx" ..

if [ $? -ne 0 ]; then
    echo "Configuration failed!"
    exit 1
fi

# Build
echo
echo "Building..."
# Use macOS-compatible core count detection
if command -v nproc >/dev/null 2>&1; then
    make -j$(nproc)
else
    make -j$(sysctl -n hw.ncpu)
fi

if [ $? -ne 0 ]; then
    echo "Build failed!"
    exit 1
fi

echo
echo "Build successful!"
echo
echo "To test GAP:"
echo "1. Run the game: ./build/devilutionx"
echo "2. Start or load a game (preferably in town)"
echo "3. In another terminal, run: python3 test_gap_agent.py"
echo
echo "The agent will connect to the game and move your character around."
