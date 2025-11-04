#!/usr/bin/env bash

# Default to rogue if no argument provided
CLASS="${1:-rogue}"

case "${CLASS}" in
    rogue)
        echo "Starting DevilutionX with Rogue companion (multi_1.sv)..."
        ./devilutionx --companion-save multi_1.sv --companion-slot 1 2>&1 | tee server.log
        ;;
    sorcerer|sorc|mage)
        echo "Starting DevilutionX with Sorcerer companion (multi_2.sv)..."
        ./devilutionx --companion-save multi_2.sv --companion-slot 1 2>&1 | tee server.log
        ;;
    warrior|war)
        echo "Starting DevilutionX with Warrior companion (multi_0.sv)..."
        ./devilutionx --companion-save multi_0.sv --companion-slot 1 2>&1 | tee server.log
        ;;
    *)
        echo "Error: Unknown class '${CLASS}'"
        echo "Usage: $0 [rogue|warrior|sorcerer]"
        echo "  rogue     - Use multi_1.sv (default)"
        echo "  warrior   - Use multi_0.sv"
        echo "  sorcerer  - Use multi_2.sv"
        exit 1
        ;;
esac
