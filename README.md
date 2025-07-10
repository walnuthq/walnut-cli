# Walnut EVM Debugger

A transaction-based debugger for Solidity smart contracts.

<img width="1417" alt="internal-calls" src="https://github.com/user-attachments/assets/3f795fcd-6db0-4ad8-a9e0-3466b2f4a39c" />

## Features

1. Transaction tracing
2. Transaction simulation

**Requirements**: Solidity compiler 0.8.29+ (for ETHDebug support)

## Installation

### Virtual Env (Recommended)

We recommend using a virtual enviroment.

```bash
python3 -m venv MyEnv
source MyEnv/bin/activate
pip install -r requirements.txt
```

### Method 1: Install from Source (Recommended)

```bash
git clone https://github.com/walnuthq/walnut-cli.git
cd walnut-cli
pip install -e .
```

### Method 2: Install from PyPI

NOTE: This needs polishing.

```bash
pip install walnut-cli
```

### Prerequisites

1. **Solidity compiler** (0.8.29+ required for ETHDebug support):
   ```bash
   # Install via package manager or download from https://github.com/ethereum/solidity/releases
   brew install solidity  # macOS
   # or
   sudo apt-get install solc  # Ubuntu
   
   # Verify version (must be 0.8.29 or higher)
   solc --version
   ```

2. **Foundry**: For contract deployment and Anvil node
   ```bash
   curl -L https://foundry.paradigm.xyz | bash
   foundryup
   ```

### Setup

After installation, run the setup script to configure your environment:
```bash
walnut-setup  # If installed via pip
# or
./setup-walnut.sh  # If running from source
```

This will:
- Check for Solidity compiler with ETHDebug support (0.8.29+)
- Configure RPC endpoint (default: http://localhost:8545 for Anvil)
- Configure private key (default: Anvil's test account #0)
- Create `walnut.config.local` with your settings

Verify your setup:
```bash
./test-setup.sh   # Test configuration (if running from source)
```

## Configuration

Configuration is stored in `walnut.config.local` (gitignored). You can also:

- Override settings with environment variables
- Use command-line options for specific tools

### Configuration Options

```bash
# Ethereum RPC endpoint
RPC_URL="http://localhost:8545"

# Private key for deployments (default: Anvil's test account #0)
PRIVATE_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

# Debug output directory
DEBUG_DIR="debug"
```

## Usage

### 1. Run Anvil node with tracing enabled

```bash
# Run Anvil with step tracing enabled (required for debugging)
$ anvil --fork-url https://reth-ethereum.ithaca.xyz/rpc --optimism --steps-tracing
```

**Important**: The `--steps-tracing` flag is required for walnut-cli to get execution traces.

### 2. Deploy a Contract

Deploy a Solidity contract with debug information:

```bash
# Deploy TestContract example
./scripts/deploy-contract.sh TestContract examples/TestContract.sol

# Deploy your own contract
./scripts/deploy-contract.sh Counter src/Counter.sol

# With custom settings
./scripts/deploy-contract.sh \
  --solc=/path/to/custom/solc \
  --rpc=http://localhost:8545 \
  --debug-dir=my-debug \
  Counter src/Counter.sol
```

This will:
- Compile with ETHDebug support: `solc --via-ir --debug-info ethdebug --ethdebug`
- Deploy to the blockchain
- Save ETHDebug JSON files to `./debug/`
- Generate deployment info

### 2. Interact with Contract

Execute transactions and get transaction hashes for debugging:

```bash
# Get current value
./scripts/interact-contract.sh get

# Set a value
./scripts/interact-contract.sh set 42

# Increment
./scripts/interact-contract.sh inc 5

# Call arbitrary function
./scripts/interact-contract.sh call "myFunction(uint256,address)" 100 0x1234...
```
Or:

```
../scripts/interact-contract.sh send "complexCalculation(uint256,uint256)" 4 5
```

Each transaction returns a hash that can be debugged.

### 3. Debug a Transaction

```bash
# Debug with ETHDebug information
walnut-cli trace 0x123... --ethdebug-dir ./debug

# Or if walnut.config.yaml is configured correctly
walnut-cli trace 0x123...

# Show raw execution trace
walnut-cli trace 0x123... --raw
```

This shows a high-level function call trace with gas usage and source mappings.

### 4. Debug Multi-Contract Transactions

Walnut-cli supports debugging transactions that involve multiple contracts, providing seamless source-level debugging across contract boundaries.

#### Loading Multiple Contracts

**Option 1: Multiple debug directories**
```bash
# Auto-detect contracts from deployment.json files
walnut-cli trace 0x123... \
    --ethdebug-dir ./debug_controller \
    --ethdebug-dir ./debug_counter

# Specify address:path mapping
walnut-cli trace 0x123... \
    --ethdebug-dir 0x44c4...9d64:./debug_controller \
    --ethdebug-dir 0x82e8...43fb:./debug_counter
```

**Option 2: Contract mapping file**
```bash
# Create a mapping file
cat > contracts.json << EOF
{
  "contracts": [
    {
      "address": "0x44c4caf8f075607deadf02dc7bf7f0166a209d64",
      "name": "Controller",
      "debug_dir": "./debug_controller"
    },
    {
      "address": "0x82e8f00d62fa200af7cfcc8f072ae0525e1a43fb",
      "name": "Counter",
      "debug_dir": "./debug_counter"
    }
  ]
}
EOF

# Use the mapping file
walnut-cli trace 0x123... --contracts contracts.json
```

**Option 3: Enable multi-contract mode**
```bash
walnut-cli trace 0x123... --multi-contract --ethdebug-dir ./debug/
```

#### Multi-Contract Output

When debugging multi-contract transactions, you'll see enhanced output:

```
Function Call Trace: 0x123...
Loaded contracts:
  Controller (0x44c4caf8f075607deadf02dc7bf7f0166a209d64)
  Counter (0x82e8f00d62fa200af7cfcc8f072ae0525e1a43fb)
Gas used: 72000

Call Stack:
------------------------------------------------------------
#0 Controller::runtime_dispatcher [entry] gas: 72000 @ Controller.sol:1
  #1 Controller::callIncrement [internal] gas: 65000 @ Controller.sol:15
    #2 call_to_Counter (0x82e8...43fb) [CALL → Counter] gas: 50000
      #3 Counter::increment [internal] gas: 45000 @ Counter.sol:8
        #4 Counter::_updateValue [internal] gas: 20000 @ Counter.sol:20
------------------------------------------------------------
```


### 5. Simulate a Transaction

You can simulate a contract call (without sending a real transaction) using the `simulate` command. Supports all Solidity argument types, including structs/tuples.

#### Basic usage

```bash
./walnut-cli.py simulate <contract_address> <function_signature> [function_args ...] --from <sender_address> --ethdebug-dir <debug_dir> [--block <block_number>] [--tx-index <index>] [--rpc-url <rpc_url>]
```

#### Example: Simple increment function

```bash
./walnut-cli.py simulate \
    0x5FbDB2315678afecb367f032d93F642f64180aa3 "increment(uint256)" 10 \
    --from 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 \
    --block 1 \
    --ethdebug-dir ./debug \
    --rpc-url "http://localhost:8545"
```

#### Example: Function with address argument

```bash
./walnut-cli.py simulate \
  0xcf7ed3acca5a467e9e704c703e8d87f634fb0fc9 \
  "giveRightToVote(address)" \
  0x70997970C51812dc3A010C7d01b50e0d17dc79C8 \
  --from 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC \
  --ethdebug-dir ./debug_ballot
```

#### Example: Function with struct/tuple argument

```bash
./walnut-cli.py simulate \
  0x0165878a594ca255338adfa4d48449f69242eb8f \
  "submitPerson((string,uint256))" \
  '("Alice", 30)' \
  --ethdebug-dir ./debug_struct \
  --from 0x70997970C51812dc3A010C7d01b50e0d17dc79C8
```

#### Example: Nested struct/tuple argument

```bash
./walnut-cli.py simulate \
  0x0165878a594ca255338adfa4d48449f69242eb8f \
  "submitCompany((string,(string,uint256)))" \
  '("Acme Corp", ("Bob", 42))' \
  --ethdebug-dir ./debug_struct \
  --from 0x286AF310eA3303c80eBE9a66F6998B21Bd8c1c29
```

> **Note:**
> - Argument format is fully compatible with Foundry's `cast send` command (e.g. for structs: `'("Alice", 30)'`, for arrays: `'[("Alice", 30), ("Bob", 42)]'`).

## Debug Information Formats

### ETHDebug Format

This approach is to use the standard ethdebug format from the Solidity compiler (requires Solidity 0.8.29+):

1. **Generate ethdebug information**:
   ```bash
   # Requires solc 0.8.29 or higher
   solc --via-ir --debug-info ethdebug --ethdebug -o /tmp/ethdebug-output MyContract.sol
   ```
   This generates:
   - `ethdebug.json` - Compilation metadata
   - `MyContract_ethdebug.json` - Constructor/creation debug info
   - `MyContract_ethdebug-runtime.json` - Runtime debug info

2. **Trace transactions with ethdebug**:
   ```bash
   walnut-cli trace 0x123...abc --ethdebug-dir /tmp/ethdebug-output
   ```

### Other formats

Currently, walnut-cli supports the standard ETHDebug format. Additional formats may be added in the future.

### Using walnut-cli after installation

After running `pip install -e .`, you can use walnut-cli directly from anywhere:

```bash
# The commands are available globally
walnut-cli trace 0x123...
walnut trace 0x123...  # Short alias
walnut-setup          # Setup wizard
```

## Debugging Workflow

### Using Helper Scripts (Recommended)

1. **Write your contract**:
   ```solidity
   // src/Counter.sol
   contract Counter {
       uint256 public counter;
       
       function setNumber(uint256 newNumber) public {
           counter = newNumber;
       }
       
       function increment(uint256 amount) public {
           counter += amount;
       }
   }
   ```

2. **Deploy with debug info**:
   ```bash
   ./scripts/deploy-contract.sh Counter src/Counter.sol
   
   # Output:
   # Transaction: 0x123...
   # Contract deployed at: 0xabc...
   # ETHDebug files created in: debug/
   ```

3. **Interact and get transaction hash**:
   ```bash
   ./scripts/interact-contract.sh set 42
   # Returns: Transaction: 0x123...
   ```

4. **Debug the transaction**:
   ```bash
   walnut-cli trace 0x123... --ethdebug-dir ./debug
   # Shows function call trace with proper function names
   ```

### Manual Workflow (Without Scripts)

If you prefer to compile, deploy, and interact manually:

1. **Compile with ETHDebug support**:
   ```bash
   # Create debug directory
   mkdir -p debug
   
   # Compile with ETHDebug (requires solc 0.8.29+)
   solc --via-ir --debug-info ethdebug --ethdebug --ethdebug-runtime \
        --bin --abi --overwrite -o debug \
        examples/TestContract.sol
   ```

2. **Deploy using cast (Foundry)**:
   ```bash
   # Get the bytecode
   BYTECODE=$(cat debug/TestContract.bin)
   
   # Deploy (using Anvil's default account)
   cast send --rpc-url http://localhost:8545 \
             --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
             --create "0x$BYTECODE" \
             --json
   
   # Note the contractAddress from the output
   ```

3. **Interact with the contract**:
   ```bash
   # Call a function (e.g., increment with value 5)
   # Replace CONTRACT_ADDRESS with your deployed address
   cast send CONTRACT_ADDRESS "increment(uint256)" 5 \
        --rpc-url http://localhost:8545 \
        --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
        --json
   
   # Note the transactionHash from the output
   ```

4. **Debug the transaction**:
   ```bash
   # Use the transaction hash from step 3
   walnut-cli trace 0xYOUR_TX_HASH --ethdebug-dir ./debug
   ```

### Reading contract state (view functions):
```bash
# Read public variables or view functions
cast call CONTRACT_ADDRESS "counter()(uint256)" --rpc-url http://localhost:8545
```

## Example Output

```
walnut-cli trace 0x2832a995d3e50c85599e7aa0343e93aa77460d6069466be4b81dbc1ea21a3994 --ethdebug-dir debug --rpc http://localhost:8545
Loading transaction 0x2832a995d3e50c85599e7aa0343e93aa77460d6069466be4b81dbc1ea21a3994...
Loaded 1833 PC mappings from ethdebug
Contract: TestContract
Environment: runtime

Function Call Trace: 0x2832a995d3e50c85599e7aa0343e93aa77460d6069466be4b81dbc1ea21a3994
Contract: 0x5FbDB2315678afecb367f032d93F642f64180aa3
Gas used: 1225735

Call Stack:
------------------------------------------------------------
#0 TestContract::runtime_dispatcher gas: 382 @ TestContract.sol:8
  #1 increment [0x7cf5dab0] gas: 12141 @ TestContract.sol:23
     steps: 99-966
    #2 increment2 gas: 6322 @ TestContract.sol:39
       steps: 296-966
      #3 increment3 gas: 5303 @ TestContract.sol:52
         steps: 493-966
------------------------------------------------------------

Use --raw flag to see detailed instruction trace
```

The raw output:
```
$ walnut-cli trace 0x123...abc --ethdebug-dir debug --raw

Loaded 300 PC mappings from ethdebug
Contract: HelloWorld
Environment: runtime

Tracing transaction: 0x123...abc
Gas used: 21234

Execution trace (first 50 steps):
--------------------------------------------------------------------------------
Step | PC   | Op              | Gas     | Stack
--------------------------------------------------------------------------------
   0   0     PUSH1            1000000  [empty] <- HelloWorld.sol:4:1
   1   2     PUSH1            999997   [0] 0x80... <- HelloWorld.sol:4:1
   2   4     MSTORE           999994   [0] 0x80... [1] 0x40... <- HelloWorld.sol:4:1
   3   5     PUSH1            999991   [empty] <- HelloWorld.sol:4:1
   4   7     CALLDATASIZE     999989   [0] 0x04... <- HelloWorld.sol:4:1
   5   8     LT               999987   [0] 0x04... [1] 0x24 <- HelloWorld.sol:4:1
...
```

## Run tests

```bash
cd test
./run-tests.sh SOLC_PATH=/path/to/solc
```

It expects RPC at `http://localhost:8545` (Anvil default) and uses Anvil's test account private key by default.
Also, it uses LLVM's `lit` and `FileCheck` tools, so please install it.

## License

Walnut is licensed under the Business Source License 1.1 (BSL). You may use, self-host, and modify Walnut for non-commercial purposes.

To use Walnut in a commercial product or service (e.g. as a SaaS offering), you must obtain a commercial license.

📄 [Full license text](./LICENSE.md)  
📬 Contact: hi@walnut.dev
