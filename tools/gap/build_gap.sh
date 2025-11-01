#!/bin/bash
# Build script for DevilutionX with GAP enabled (DSL mode)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=================================="
echo "Building DevilutionX with GAP"
echo "DSL Mode (Compact Protocol)"
echo "=================================="
echo

# Create build directory if it doesn't exist
cd "$PROJECT_ROOT"
mkdir -p build
cd build

# Configure with GAP enabled
echo "📝 Configuring with GAP enabled..."
cmake -DENABLE_GAP=ON \
      -DCMAKE_BUILD_TYPE=Release \
      -DASAN=OFF \
      -DUBSAN=OFF \
      ..

echo
echo "🔨 Building..."
# Use platform-compatible core count detection
if command -v nproc >/dev/null 2>&1; then
    CORES=$(nproc)
elif command -v sysctl >/dev/null 2>&1; then
    CORES=$(sysctl -n hw.ncpu)
else
    CORES=4
fi

make -j$CORES

echo
echo "=================================="
echo "✅ Build successful!"
echo "=================================="
echo
echo "DSL Mode: Enabled (GAP_USE_DSL=1 in Source/gap/gap_state.h)"
echo "Binary: ./build/devilutionx"
echo
echo "Next steps:"
echo "  1. Test socket:     cd tools/gap && python3 test_socket.py"
echo "  2. Run full agent:  cd tools/gap && ./run_agent.sh"
echo
echo "See READY-TO-TEST.md for complete instructions"
echo
