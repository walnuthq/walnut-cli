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

# Test Solidity compiler
echo -n "Testing solc... "
if [ -n "$SOLC_PATH" ] && [ -x "$SOLC_PATH" ]; then
    if "$SOLC_PATH" --version > /dev/null 2>&1; then
        VERSION=$("$SOLC_PATH" --version | grep -oE 'Version: [0-9]+\.[0-9]+\.[0-9]+' | cut -d' ' -f2)
        echo -e "${GREEN}✓ OK${NC} (version $VERSION)"
    else
        echo -e "${RED}✗ Failed to run${NC}"
    fi
elif command -v solc &> /dev/null; then
    VERSION=$(solc --version | grep -oE 'Version: [0-9]+\.[0-9]+\.[0-9]+' | cut -d' ' -f2)
    echo -e "${GREEN}✓ OK${NC} (version $VERSION from PATH)"
else
    echo -e "${YELLOW}⚠ Not configured${NC}"
    echo "  You can specify a custom solc with --solc flag when deploying"
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
    echo -e "${YELLOW}⚠ Failed${NC}"
    echo "  Make sure Anvil is running: anvil --fork-url <RPC> --steps-tracing"
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
echo "  SOLC_PATH=${SOLC_PATH:-"(will use system solc)"}"
echo "  RPC_URL=$RPC_URL"
echo "  DEBUG_DIR=$DEBUG_DIR"

echo
echo -e "${BLUE}Next steps:${NC}"
echo "1. Start Anvil with tracing:"
echo "   anvil --fork-url <YOUR_RPC> --steps-tracing"
echo
echo "2. Deploy a contract:"
echo "   ./scripts/deploy-contract.sh TestContract examples/TestContract.sol"
echo
echo "3. Interact with contract:"
echo "   ./scripts/interact-contract.sh increment 5"
echo
echo "4. Debug a transaction:"
echo "   ./walnut-cli.py <tx_hash>"