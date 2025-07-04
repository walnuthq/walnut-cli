#!/bin/bash
# Deploy a Solidity contract using cast (Foundry) and prepare for debugging

set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
WALNUT_DIR="$(dirname "$SCRIPT_DIR")"

# Load configuration if exists
if [ -f "$WALNUT_DIR/walnut.config.local" ]; then
    source "$WALNUT_DIR/walnut.config.local"
elif [ -f "$WALNUT_DIR/walnut.config" ]; then
    source "$WALNUT_DIR/walnut.config"
fi

# Default configuration (can be overridden by config file or environment)
RPC_URL="${RPC_URL:-http://localhost:8545}"
PRIVATE_KEY="${PRIVATE_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"
DEBUG_DIR="${DEBUG_DIR:-debug}"
SOLX_PATH="${SOLX_PATH:-}"
SOLC_PATH="${SOLC_PATH:-}"
COMPILER_TYPE="auto"  # auto, solc, or solx

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Parse arguments
CONTRACT_NAME=""
CONTRACT_FILE=""

usage() {
    echo "Usage: $0 [OPTIONS] <contract_name> <contract_file>"
    echo ""
    echo "Arguments:"
    echo "  contract_name     Name of the contract to deploy (e.g., 'Counter')"
    echo "  contract_file     Path to the Solidity file (e.g., 'src/Counter.sol')"
    echo ""
    echo "Options:"
    echo "  --solc=PATH       Path to solc binary (for ethdebug format)"
    echo "  --solx=PATH       Path to solx binary (for DWARF format)"
    echo "  --compiler=TYPE   Force compiler type: 'solc' or 'solx' (default: auto-detect)"
    echo "  --rpc=URL         RPC URL (default: http://localhost:8545)"
    echo "  --private-key=KEY Private key for deployment"
    echo "  --debug-dir=DIR   Debug output directory (default: debug)"
    echo "  -h, --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Using solc with ethdebug (recommended):"
    echo "  $0 Counter src/Counter.sol"
    echo "  $0 --solc=/path/to/solc Counter src/Counter.sol"
    echo ""
    echo "  # Using solx with DWARF (experimental):"
    echo "  $0 --solx=/path/to/solx Counter src/Counter.sol"
    echo ""
    echo "  # Force specific compiler:"
    echo "  $0 --compiler=solc Counter src/Counter.sol"
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --solc=*)
            SOLC_PATH="${1#*=}"
            shift
            ;;
        --solx=*)
            SOLX_PATH="${1#*=}"
            shift
            ;;
        --compiler=*)
            COMPILER_TYPE="${1#*=}"
            shift
            ;;
        --rpc=*)
            RPC_URL="${1#*=}"
            shift
            ;;
        --private-key=*)
            PRIVATE_KEY="${1#*=}"
            shift
            ;;
        --debug-dir=*)
            DEBUG_DIR="${1#*=}"
            shift
            ;;
        -h|--help)
            usage
            ;;
        --*)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
        *)
            if [ -z "$CONTRACT_NAME" ]; then
                CONTRACT_NAME="$1"
            elif [ -z "$CONTRACT_FILE" ]; then
                CONTRACT_FILE="$1"
            else
                echo -e "${RED}Too many arguments${NC}"
                usage
            fi
            shift
            ;;
    esac
done

# Validate arguments
if [ -z "$CONTRACT_NAME" ] || [ -z "$CONTRACT_FILE" ]; then
    echo -e "${RED}Error: Contract name and file are required${NC}"
    usage
fi

# Check if contract file exists
if [ ! -f "$CONTRACT_FILE" ]; then
    echo -e "${RED}Error: Contract file '$CONTRACT_FILE' does not exist${NC}"
    echo -e "${YELLOW}Did you swap the contract name and file arguments?${NC}"
    echo -e "${YELLOW}Correct usage: $0 [OPTIONS] <contract_name> <contract_file>${NC}"
    exit 1
fi

# Determine which compiler to use
if [ "$COMPILER_TYPE" = "auto" ]; then
    # Auto-detect: prefer solc if available and no solx path specified
    if [ -n "$SOLC_PATH" ]; then
        COMPILER_TYPE="solc"
    elif [ -n "$SOLX_PATH" ]; then
        COMPILER_TYPE="solx"
    elif command -v solc &> /dev/null; then
        COMPILER_TYPE="solc"
    else
        # Default to solc if nothing else is specified
        COMPILER_TYPE="solc"
    fi
fi

# Find the appropriate compiler
if [ "$COMPILER_TYPE" = "solc" ]; then
    # Find solc
    if [ -z "$SOLC_PATH" ]; then
        if command -v solc &> /dev/null; then
            SOLC_PATH="solc"
        else
            echo -e "${RED}Error: solc not found${NC}"
            echo "Please install solc or specify the path with --solc=/path/to/solc"
            exit 1
        fi
    fi
    
    if [ ! -x "$SOLC_PATH" ] && ! command -v "$SOLC_PATH" &> /dev/null; then
        echo -e "${RED}Error: solc not executable at $SOLC_PATH${NC}"
        exit 1
    fi
    
    echo -e "${BLUE}Using solc compiler with ethdebug format (recommended)${NC}"
    echo -e "Compiler: ${SOLC_PATH}"
else
    # Find solx
    if [ -z "$SOLX_PATH" ]; then
        # Try to find solx in PATH
        if command -v solx &> /dev/null; then
            SOLX_PATH="solx"
        else
            # Try common locations
            for path in \
                "/Users/djtodorovic/projects/crypto/SOLIDITY/solx/target/debug/solx" \
                "/Users/djtodorovic/projects/crypto/SOLIDITY/solx/target/release/solx" \
                "./solx/target/debug/solx" \
                "./solx/target/release/solx"; do
                if [ -x "$path" ]; then
                    SOLX_PATH="$path"
                    echo -e "${BLUE}Found solx at: $SOLX_PATH${NC}"
                    break
                fi
            done
        fi
    fi
    
    if [ -z "$SOLX_PATH" ] || [ ! -x "$SOLX_PATH" ]; then
        echo -e "${RED}Error: solx not found${NC}"
        echo "Please specify the path to solx with --solx=/path/to/solx"
        echo "Or use standard solc compiler (recommended)"
        exit 1
    fi
    
    echo -e "${BLUE}Using solx compiler with DWARF format (experimental)${NC}"
    echo -e "Compiler: ${SOLX_PATH}"
fi

echo -e "${BLUE}Deploying ${CONTRACT_NAME} contract...${NC}"

# Create debug directory
mkdir -p "$DEBUG_DIR"

# Compile the contract
if [ "$COMPILER_TYPE" = "solc" ]; then
    # Compile with solc for ethdebug
    echo -e "${BLUE}Compiling with solc for ethdebug format...${NC}"
    
    # Create a temporary output directory for solc
    SOLC_OUTPUT_DIR="$DEBUG_DIR/ethdebug_output"
    mkdir -p "$SOLC_OUTPUT_DIR"
    
    # Compile with ethdebug flags
    echo -e "${BLUE}Running: $SOLC_PATH --via-ir --debug-info ethdebug --ethdebug --ethdebug-runtime --bin --abi -o $SOLC_OUTPUT_DIR $CONTRACT_FILE${NC}"
    
    "$SOLC_PATH" \
        --via-ir \
        --debug-info ethdebug \
        --ethdebug \
        --ethdebug-runtime \
        --bin \
        --abi \
        -o "$SOLC_OUTPUT_DIR" \
        "$CONTRACT_FILE" 2>&1 | tee "$DEBUG_DIR/compile.log"
    
    # Check for errors
    COMPILE_EXIT_CODE=${PIPESTATUS[0]}
    if [ $COMPILE_EXIT_CODE -ne 0 ]; then
        echo -e "${RED}Compilation failed with exit code $COMPILE_EXIT_CODE${NC}"
        cat "$DEBUG_DIR/compile.log"
        exit 1
    fi
    
    # Check if compilation produced any output
    echo -e "${BLUE}Checking compilation output...${NC}"
    if [ -z "$(ls -A "$SOLC_OUTPUT_DIR" 2>/dev/null)" ]; then
        echo -e "${RED}Error: No output files generated by solc${NC}"
        echo -e "${YELLOW}Compilation log:${NC}"
        cat "$DEBUG_DIR/compile.log"
        exit 1
    fi
    
    # Find the generated files
    # First, let's see what files were generated
    echo -e "${BLUE}Generated files:${NC}"
    ls -la "$SOLC_OUTPUT_DIR"
    
    # Look for .bin files - solc names them based on the actual contract name in the file
    BIN_FILE=""
    FOUND_CONTRACTS=()
    
    # First, collect all .bin files
    for file in "$SOLC_OUTPUT_DIR"/*.bin; do
        if [ -f "$file" ]; then
            contract_name=$(basename "$file" .bin)
            FOUND_CONTRACTS+=("$contract_name")
            
            # If CONTRACT_NAME matches the filename exactly, use it
            if [[ "$contract_name" == "$CONTRACT_NAME" ]]; then
                BIN_FILE="$file"
                break
            fi
        fi
    done
    
    # If exact match not found, look for partial matches or use the first contract
    if [ -z "$BIN_FILE" ] && [ ${#FOUND_CONTRACTS[@]} -gt 0 ]; then
        echo -e "${YELLOW}Found contracts: ${FOUND_CONTRACTS[*]}${NC}"
        
        # Look for a contract that contains our CONTRACT_NAME
        for contract in "${FOUND_CONTRACTS[@]}"; do
            if [[ "$contract" == *"$CONTRACT_NAME"* ]] || [[ "$CONTRACT_NAME" == *"$contract"* ]]; then
                BIN_FILE="$SOLC_OUTPUT_DIR/${contract}.bin"
                CONTRACT_NAME="$contract"
                echo -e "${YELLOW}Using matching contract: ${CONTRACT_NAME}${NC}"
                break
            fi
        done
        
        # If still no match, use the first non-library contract
        if [ -z "$BIN_FILE" ]; then
            for contract in "${FOUND_CONTRACTS[@]}"; do
                # Skip obvious library contracts
                if [[ "$contract" != *"Library"* ]] && [[ "$contract" != *"Interface"* ]]; then
                    BIN_FILE="$SOLC_OUTPUT_DIR/${contract}.bin"
                    CONTRACT_NAME="$contract"
                    echo -e "${YELLOW}Using first non-library contract: ${CONTRACT_NAME}${NC}"
                    break
                fi
            done
        fi
        
        # Last resort: use the first contract
        if [ -z "$BIN_FILE" ]; then
            BIN_FILE="$SOLC_OUTPUT_DIR/${FOUND_CONTRACTS[0]}.bin"
            CONTRACT_NAME="${FOUND_CONTRACTS[0]}"
            echo -e "${YELLOW}Using first available contract: ${CONTRACT_NAME}${NC}"
        fi
    fi
    
    if [ -z "$BIN_FILE" ] || [ ! -f "$BIN_FILE" ]; then
        echo -e "${RED}Error: No binary file found in $SOLC_OUTPUT_DIR${NC}"
        exit 1
    fi
    
    # Now find the corresponding ABI file
    ABI_FILE="$SOLC_OUTPUT_DIR/${CONTRACT_NAME}.abi"
    
    echo -e "${BLUE}Using binary: $(basename "$BIN_FILE")${NC}"
    echo -e "${BLUE}Using ABI: $(basename "$ABI_FILE")${NC}"
    
    BYTECODE=$(cat "$BIN_FILE")
    ABI=$(cat "$ABI_FILE" 2>/dev/null || echo "[]")
    
    # Validate bytecode
    if [ -z "$BYTECODE" ] || [ "$BYTECODE" = "0x" ]; then
        echo -e "${RED}Error: Contract bytecode is empty${NC}"
        echo -e "${YELLOW}This might be an interface or abstract contract${NC}"
        exit 1
    fi
    
else
    # Compile with solx for DWARF debug info
    echo -e "${BLUE}Compiling with solx...${NC}"
    COMPILE_OUTPUT=$("$SOLX_PATH" \
        --bin \
        --abi \
        --debug-output-dir "$DEBUG_DIR" \
        "$CONTRACT_FILE" 2>&1)
    
    echo "$COMPILE_OUTPUT" | grep -E "Warning:|Error:" || true
    
    # Parse the output to extract contract name, binary, and ABI
    # Look for the contract header: ======= path/to/file.sol:ContractName =======
    CONTRACT_HEADER=$(echo "$COMPILE_OUTPUT" | grep -E "^======= .+:(.+) =======\$" | head -1)
    if [ -z "$CONTRACT_HEADER" ]; then
        echo -e "${RED}Error: Could not find contract in output${NC}"
        echo "$COMPILE_OUTPUT"
        exit 1
    fi
    
    # Extract actual contract name from header
    ACTUAL_CONTRACT_NAME=$(echo "$CONTRACT_HEADER" | sed -E 's/^=+ .+:(.+) =+$/\1/')
    echo -e "${BLUE}Found contract: ${ACTUAL_CONTRACT_NAME}${NC}"
    
    # Update CONTRACT_NAME if different
    if [ "$ACTUAL_CONTRACT_NAME" != "$CONTRACT_NAME" ]; then
        echo -e "${YELLOW}Note: Using actual contract name '${ACTUAL_CONTRACT_NAME}' instead of '${CONTRACT_NAME}'${NC}"
        CONTRACT_NAME="$ACTUAL_CONTRACT_NAME"
    fi
    
    # Extract bytecode from output
    BYTECODE=$(echo "$COMPILE_OUTPUT" | awk '/^Binary:/{getline; print}' | head -1)
    if [ -z "$BYTECODE" ]; then
        echo -e "${RED}Error: Could not extract bytecode${NC}"
        exit 1
    fi
    
    # Extract ABI from output
    ABI_START=$(echo "$COMPILE_OUTPUT" | grep -n "Contract JSON ABI:" | cut -d: -f1)
    if [ -n "$ABI_START" ]; then
        ABI=$(echo "$COMPILE_OUTPUT" | tail -n +$((ABI_START + 1)) | head -1)
    fi
fi

# At this point, BYTECODE and ABI should be set from either solc or solx compilation

# Save ABI and bytecode
echo "$ABI" > "$DEBUG_DIR/${CONTRACT_NAME}.abi"
echo "$BYTECODE" > "$DEBUG_DIR/${CONTRACT_NAME}.bin"

# Ensure bytecode has 0x prefix for cast
if [[ "$BYTECODE" != 0x* ]]; then
    BYTECODE="0x$BYTECODE"
fi

# Deploy with cast
echo -e "${BLUE}Deploying to chain...${NC}"
echo -e "${BLUE}Bytecode length: ${#BYTECODE} characters${NC}"

DEPLOY_OUTPUT=$(cast send \
    --rpc-url "$RPC_URL" \
    --private-key "$PRIVATE_KEY" \
    --create "$BYTECODE" \
    --json 2>/dev/null)

# Extract transaction hash and contract address
TX_HASH=$(echo "$DEPLOY_OUTPUT" | jq -r '.transactionHash')
CONTRACT_ADDR=$(echo "$DEPLOY_OUTPUT" | jq -r '.contractAddress')

echo -e "${GREEN}Transaction: $TX_HASH${NC}"
echo -e "${GREEN}Contract deployed at: $CONTRACT_ADDR${NC}"

# Save deployment info
cat > "$DEBUG_DIR/deployment.json" <<EOF
{
  "contract": "$CONTRACT_NAME",
  "address": "$CONTRACT_ADDR",
  "transaction": "$TX_HASH",
  "network": "$RPC_URL",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

# Extract debug info based on compiler
if [ "$COMPILER_TYPE" = "solx" ]; then
    # Extract debug ELF for DWARF format
    EVM_DWARF_CMD=""
    if [ -n "$EVM_DEBUG_PATH" ] && [ -x "$EVM_DEBUG_PATH" ]; then
        EVM_DWARF_CMD="$EVM_DEBUG_PATH"
    elif command -v evm-dwarf &> /dev/null; then
        EVM_DWARF_CMD="evm-dwarf"
    fi
    
    if [ -n "$EVM_DWARF_CMD" ]; then
        echo -e "${BLUE}Extracting DWARF debug info...${NC}"
        "$EVM_DWARF_CMD" \
            --input "$DEBUG_DIR/${CONTRACT_FILE}_${CONTRACT_NAME}.runtime.zasm" \
            --output "$DEBUG_DIR/${CONTRACT_NAME}.debug.elf"
        echo -e "${GREEN}Debug ELF created: $DEBUG_DIR/${CONTRACT_NAME}.debug.elf${NC}"
    else
        echo -e "${BLUE}Note: evm-dwarf not found, skipping debug ELF generation${NC}"
    fi
else
    # For solc/ethdebug, the debug files are already in the output directory
    echo -e "${GREEN}ETHDebug files created in: $SOLC_OUTPUT_DIR${NC}"
    echo -e "  - ethdebug.json"
    echo -e "  - ${CONTRACT_NAME}_ethdebug.json"
    echo -e "  - ${CONTRACT_NAME}_ethdebug-runtime.json"
fi

# Removed debug script generation - using walnut-cli.py directly

echo -e "\n${GREEN}Deployment complete!${NC}"

if [ "$COMPILER_TYPE" = "solc" ]; then
    echo -e "To trace: ${BLUE}$WALNUT_DIR/walnut-cli.py $TX_HASH --ethdebug-dir $SOLC_OUTPUT_DIR${NC}"
else
    echo -e "To trace: ${BLUE}$WALNUT_DIR/walnut-cli.py $TX_HASH --debug-info-from-zasm-file $DEBUG_DIR/${CONTRACT_FILE}_${CONTRACT_NAME}.runtime.zasm${NC}"
fi
