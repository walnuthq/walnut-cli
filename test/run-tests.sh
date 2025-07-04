#!/bin/bash
# Run walnut-cli tests

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Parse command line arguments
for arg in "$@"; do
    case $arg in
        SOLC_PATH=*)
            SOLC_PATH="${arg#*=}"
            shift
            ;;
        *)
            # Unknown option
            ;;
    esac
done

# Configuration
RPC_URL="${RPC_URL:-http://localhost:8547}"
CHAIN_ID="${CHAIN_ID:-412346}"
PRIVATE_KEY="${PRIVATE_KEY:-0xb6b15c8cb491557369f3c7d2c287b053eb229daa9c22138887752191c9520659}"
SOLC_PATH="${SOLC_PATH:-solc}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Walnut CLI Test Suite ===${NC}"

# Check if test deployment exists
# First check the new ETHDebug location
if [ -f "${PROJECT_DIR}/examples/debug/ethdebug_output/deployment.json" ]; then
    DEPLOYMENT_JSON="${PROJECT_DIR}/examples/debug/ethdebug_output/deployment.json"
elif [ -f "${PROJECT_DIR}/examples/debug/deployment.json" ]; then
    DEPLOYMENT_JSON="${PROJECT_DIR}/examples/debug/deployment.json"
else
    echo -e "${YELLOW}No deployment found. Deploying TestContract...${NC}"
    # Deploy the contract automatically
    cd "${PROJECT_DIR}/examples"
    "${PROJECT_DIR}/scripts/deploy-contract.sh" --solc="${SOLC_PATH}" --rpc="${RPC_URL}" --private-key="${PRIVATE_KEY}" TestContract TestContract.sol --debug-dir=debug
    
    # Check again after deployment
    if [ -f "${PROJECT_DIR}/examples/debug/deployment.json" ]; then
        DEPLOYMENT_JSON="${PROJECT_DIR}/examples/debug/deployment.json"
    else
        echo -e "${RED}Deployment failed!${NC}"
        exit 1
    fi
fi

# Load deployment info
DEPLOYMENT_INFO=$(cat "$DEPLOYMENT_JSON")
# Try new format first (from ETHDebug deploy script)
CONTRACT_ADDRESS=$(echo "$DEPLOYMENT_INFO" | jq -r '.address // empty')
DEPLOY_TX=$(echo "$DEPLOYMENT_INFO" | jq -r '.transaction // empty')

# Fallback to old format if needed
if [ -z "$CONTRACT_ADDRESS" ]; then
    CONTRACT_ADDRESS=$(echo "$DEPLOYMENT_INFO" | grep -o '"contract_address": "[^"]*' | sed 's/"contract_address": "//')
fi
if [ -z "$DEPLOY_TX" ]; then
    DEPLOY_TX=$(echo "$DEPLOYMENT_INFO" | grep -o '"transaction_hash": "[^"]*' | sed 's/"transaction_hash": "//')
fi

# Use the test transaction provided by the user or create a new one
# If we have a deployment and no TEST_TX is provided, create a fresh increment transaction
if [ -z "$TEST_TX" ] && [ -n "$CONTRACT_ADDRESS" ]; then
    echo -e "${YELLOW}Creating fresh test transaction...${NC}"
    # Send an increment transaction and capture the TX hash
    TX_OUTPUT=$(cd "${PROJECT_DIR}/examples" && DEBUG_DIR=debug RPC_URL="${RPC_URL}" "${PROJECT_DIR}/scripts/interact-contract.sh" send "increment(uint256)" 4 2>&1)
    TEST_TX=$(echo "$TX_OUTPUT" | grep -o '0x[a-fA-F0-9]\{64\}' | head -1)
    if [ -z "$TEST_TX" ]; then
        echo -e "${RED}Failed to create test transaction${NC}"
        echo "$TX_OUTPUT"
        exit 1
    fi
    echo -e "${GREEN}Created test transaction: ${TEST_TX}${NC}"
else
    # Fallback to the old hardcoded transaction if nothing else works
    TEST_TX="${TEST_TX:-0x8a387193d19ae8ff6d15b32b7abec4144601d98da8c2af1eebd9cf4061c033a7}"
fi

echo "Using contract: ${CONTRACT_ADDRESS}"
echo "Using transaction: ${TEST_TX}"
echo ""

# Find walnut-cli
if command -v walnut-cli &> /dev/null; then
    WALNUT_CLI="walnut-cli"
elif [ -f "${PROJECT_DIR}/MyEnv/bin/walnut-cli" ]; then
    WALNUT_CLI="${PROJECT_DIR}/MyEnv/bin/walnut-cli"
else
    echo -e "${RED}Error: walnut-cli not found${NC}"
    echo "Install with: pip install -e ${PROJECT_DIR}"
    exit 1
fi

# Create lit config
cat > "${SCRIPT_DIR}/lit.site.cfg.py" << EOF
import sys
import os

config.walnut_cli_dir = "${PROJECT_DIR}"
config.walnut_cli = "${WALNUT_CLI}"
config.rpc_url = "${RPC_URL}"
config.chain_id = "${CHAIN_ID}"
config.private_key = "${PRIVATE_KEY}"
config.test_contracts = {
    "contract_address": "${CONTRACT_ADDRESS}",
    "deploy_tx": "${DEPLOY_TX}",
    "test_tx": "${TEST_TX}",
    "ethdebug_dir": "${PROJECT_DIR}/examples/debug"
}
config.solc_path = "${SOLC_PATH}"

# Load the main config
lit_config.load_config(config, "${SCRIPT_DIR}/lit.cfg.py")
EOF

# Check for lit
if ! command -v lit &> /dev/null; then
    # Try llvm-lit
    LLVM_LIT=""
    for path in "/usr/local/opt/llvm/bin/llvm-lit" "/opt/homebrew/opt/llvm/bin/llvm-lit" "/usr/bin/llvm-lit"; do
        if [ -f "$path" ]; then
            LLVM_LIT="$path"
            break
        fi
    done
    
    if [ -z "$LLVM_LIT" ]; then
        echo -e "${RED}Error: Neither 'lit' nor 'llvm-lit' found${NC}"
        echo "Install with: pip install lit"
        echo "Or install LLVM: brew install llvm"
        exit 1
    fi
    
    LIT_CMD="$LLVM_LIT"
else
    LIT_CMD="lit"
fi

# Run tests
echo -e "${YELLOW}Running tests...${NC}"
"$LIT_CMD" -v "${SCRIPT_DIR}"

echo -e "${GREEN}Test suite completed!${NC}"
