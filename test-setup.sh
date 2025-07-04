#!/bin/bash
# Test Walnut EVM Debugger setup

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo -e "${BLUE}Testing Walnut EVM Debugger Setup${NC}"
echo "=================================="
echo

# Load configuration
CONFIG_FILE=""
if [ -f "$SCRIPT_DIR/walnut.config.local" ]; then
    CONFIG_FILE="$SCRIPT_DIR/walnut.config.local"
    source "$CONFIG_FILE"
    echo -e "${GREEN}✓ Found configuration: walnut.config.local${NC}"
elif [ -f "$SCRIPT_DIR/walnut.config" ]; then
    CONFIG_FILE="$SCRIPT_DIR/walnut.config"
    source "$CONFIG_FILE"
    echo -e "${GREEN}✓ Found configuration: walnut.config${NC}"
else
    echo -e "${RED}✗ No configuration file found${NC}"
    echo "  Run ./setup-walnut.sh to create one"
    exit 1
fi

echo

# Test solx
echo -n "Testing solx... "
if [ -n "$SOLX_PATH" ] && [ -x "$SOLX_PATH" ]; then
    if "$SOLX_PATH" --version > /dev/null 2>&1; then
        VERSION=$("$SOLX_PATH" --version 2>&1 | head -1)
        echo -e "${GREEN}✓ OK${NC} ($VERSION)"
    else
        echo -e "${RED}✗ Failed to run${NC}"
    fi
else
    echo -e "${RED}✗ Not found or not executable${NC}"
    echo "  Path: $SOLX_PATH"
fi

# Test evm-dwarf (formerly evm-debug)
echo -n "Testing evm-dwarf... "
if [ -n "$EVM_DEBUG_PATH" ] && [ -x "$EVM_DEBUG_PATH" ]; then
    if "$EVM_DEBUG_PATH" --help > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
    else
        echo -e "${RED}✗ Failed to run${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Not configured${NC} (optional)"
fi

# Test RPC connection
echo -n "Testing RPC connection to $RPC_URL... "
if curl -s -X POST -H "Content-Type: application/json" \
    --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
    "$RPC_URL" > /dev/null 2>&1; then
    BLOCK=$(curl -s -X POST -H "Content-Type: application/json" \
        --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
        "$RPC_URL" | grep -o '"result":"[^"]*"' | cut -d'"' -f4)
    echo -e "${GREEN}✓ OK${NC} (block: $BLOCK)"
else
    echo -e "${YELLOW}⚠ Failed${NC} (node may be offline)"
fi

# Test Python dependencies
echo -n "Testing Python dependencies... "
if python3 -c "import web3, eth_utils" 2>/dev/null; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${YELLOW}⚠ Missing${NC}"
    echo "  Install with: pip install -r requirements.txt"
fi

# Test cast (Foundry)
echo -n "Testing cast (Foundry)... "
if command -v cast &> /dev/null; then
    CAST_VERSION=$(cast --version 2>&1 | head -1)
    echo -e "${GREEN}✓ OK${NC} ($CAST_VERSION)"
else
    echo -e "${RED}✗ Not found${NC}"
    echo "  Install Foundry: https://getfoundry.sh"
fi

echo
echo -e "${BLUE}Configuration Summary:${NC}"
echo "  SOLX_PATH=$SOLX_PATH"
echo "  EVM_DEBUG_PATH=$EVM_DEBUG_PATH"
echo "  RPC_URL=$RPC_URL"
echo "  DEBUG_DIR=$DEBUG_DIR"

echo
echo -e "${BLUE}Next steps:${NC}"
echo "1. Deploy a contract:"
echo "   ./scripts/deploy-contract.sh Counter src/Counter.sol"
echo
echo "2. Interact with contract:"
echo "   ./scripts/interact-contract.sh set 42"
echo
echo "3. Debug a transaction:"
echo "   ./walnut-cli.py <tx_hash> --interactive"