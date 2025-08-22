> ⚠️ SolDB is currently in **public beta** – not yet recommended for production use. Expect bugs, missing features, and breaking changes.

# SolDB EVM Debugger

A CLI debugger for the EVM and Solidity.

![screenshot](reverted_transaction.png)

## Features

1. Full transaction traces with internal calls
2. Decoded arguments and results
3. Transaction simulation
4. Suport for custom RPC including local node (Anvil) or hosted

## Requirements

- **Python 3.7+** - For SolDB
- **Foundry** - For contract development and Anvil node
- **Solidity compiler** - Version 0.8.29+ with ETHDebug support

## Installation Guide

**Install Solidity:**
```bash
# macOS
brew install solidity
# Ubuntu
sudo apt-get install solc
# Or download from https://github.com/ethereum/solidity/releases

# Verify version (must be 0.8.29 or higher)
solc --version
```

**Install Foundry:**
```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

**Install SolDB:**
```bash
pip install git+https://github.com/walnuthq/soldb.git
```
**NOTE**: Since we are still in BETA, the PyPI package is not available at the moment.



## Usage

**NOTE**: SolDB is primarily intended for local debugging. While Anvil (local node) is recommended for development, SolDB supports any RPC endpoint - local or public. The examples use `http://localhost:8545` (Anvil's default).

### 1. Run Anvil node with tracing enabled

Start a local node with step tracing enabled for debugging.

```bash
# Minimum required: Enable step tracing
$ anvil --steps-tracing

# With chain forking (recommended for testing on real network state)
$ anvil --fork-url <url> --steps-tracing
```

**NOTE**: The `--steps-tracing` flag is required for SolDB to get execution traces.

### 2. Compile contract

Generate ETHDebug information by compiling your Solidity contract.

```bash
# Compile with ETHDebug support
solc --via-ir --debug-info ethdebug --ethdebug --ethdebug-runtime --bin --abi --overwrite -o /tmp/ethdebug-output examples/Counter.sol
```

This will:
- Compile contract with ETHDebug support: `solc --via-ir --debug-info ethdebug --ethdebug --ethdebug-runtime`
- Save ETHDebug JSON files to `/tmp/ethdebug-output`

### 3. Debug transaction

**NOTE**: You need a transaction hash (`tx_hash`) to debug. You can get this by deploying a contract and calling contract functions using any method you prefer (Foundry, Hardhat, etc.).

Analyze transaction execution with full source-level debugging.

```bash
# Basic transaction debugging
soldb trace <tx_hash> --rpc http://localhost:8545

# Multi-Contract debugging - Auto-detect contracts from multiple debug directories
soldb trace <tx_hash> \
    --ethdebug-dir ./debug_controller \
    --ethdebug-dir ./debug_counter \
    --rpc http://localhost:8545

# Or, use a single debug directory with multiple contracts
soldb trace <tx_hash> --ethdebug-dir /tmp/ethdebug-output/ --rpc http://localhost:8545

# Or, use contract mapping file for complex multi-contract scenarios. Create contracts.json:
# 
# {
#   "contracts": [
#     {
#       "address": "0x44c4caf8f075607deadf02dc7bf7f0166a209d64",
#       "name": "Controller",
#       "debug_dir": "./debug_controller"
#     },
#     {
#       "address": "0x82e8f00d62fa200af7cfcc8f072ae0525e1a43fb",
#       "name": "Counter",
#       "debug_dir": "./debug_counter"
#     }
#   ]
# }
# Then use: 
soldb trace <tx_hash> --contracts contracts.json --rpc http://localhost:8545

# Show raw execution trace
soldb trace <tx_hash> --raw --rpc http://localhost:8545

# Output in JSON format
soldb trace <tx_hash> --json --rpc http://localhost:8545
```

### 4. Simulate transaction

Test contract functions without sending transactions on chain.

```bash
# Simple function call
soldb simulate <contract_address> "increment(uint256)" 10 \
    --from <sender_address> \
    --ethdebug-dir /tmp/ethdebug-output \
    --rpc http://localhost:8545

# Function with struct arguments
soldb simulate <contract_address> "submitPerson((string,uint256))" '("Alice", 30)' \
    --ethdebug-dir /tmp/ethdebug-output \
    --from <sender_address> \
    --rpc http://localhost:8545

# Nested struct/tuple argument
soldb simulate \
  <contract_address> \
  "submitCompany((string,(string,uint256)))" \
  '("Acme Corp", ("Bob", 42))' \
  --ethdebug-dir /tmp/ethdebug-output \
  --rpc http://localhost:8545

# Simulate with raw data
soldb simulate --raw-data \
0x785bd74f000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000000941636d6520436f727000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000002a0000000000000000000000000000000000000000000000000000000000000003426f620000000000000000000000000000000000000000000000000000000000 \
  <contract_address> \
  --ethdebug-dir /tmp/ethdebug-output \
  --from <sender_address> \
  --rpc http://localhost:8545 
```

## Debug Information Format

SolDB relies on the standard [ETHDebug format](https://ethdebug.github.io/format/spec/overview) from the Solidity compiler (requires Solidity 0.8.29+):

1. **Generate ETHDebug information**:
   ```bash
   # Requires solc 0.8.29 or higher
   solc --via-ir --debug-info ethdebug --ethdebug --ethdebug-runtime -o /tmp/ethdebug-output Counter.sol
   ```
   This generates:
   - `ethdebug.json` - Compilation metadata
   - `Counter_ethdebug.json` - Constructor/creation debug info
   - `Counter_ethdebug-runtime.json` - Runtime debug info

2. **Trace transactions with ETHDebug**:
   ```bash
   soldb trace 0x5c2...bef --ethdebug-dir /tmp/ethdebug-output --rpc http://localhost:8545
   ```

## Quick Start Example

If you want the full workflow (compile → deploy → interact → debug) in one place:

1. **Compile contract with ETHDebug support**:
   ```bash
   # Create /tmp/ethdebug-output directory
   mkdir -p /tmp/ethdebug-output
   
   # Compile with ETHDebug (requires solc 0.8.29+)
   solc --via-ir --debug-info ethdebug --ethdebug --ethdebug-runtime \
        --bin --abi --overwrite -o /tmp/ethdebug-output \
        examples/TestContract.sol
   ```
2. **Run Anvil node**:
   ```bash
   anvil --steps-tracking
   ```
3. **Deploy using cast (Foundry)**:
   ```bash
   # Get the bytecode
   BYTECODE=$(cat /tmp/ethdebug-output/TestContract.bin)
   
   # Deploy (using Anvil's default account)
   cast send --rpc http://localhost:8545 \
             --private-key $PRIVATE_KEY \
             --create "$(cat /tmp/ethdebug-output/TestContract.bin)" \
             --json
   ```

4. **Interact and get transaction hash:**
   ```bash
   cast send <contract_address> "myFunction(uint256)" 42 \
            --rpc http://localhost:8545 \
            --private-key $PRIVATE_KEY
   ```

5. **Debug transaction:**
   ```bash
   soldb trace <tx_hash> --ethdebug-dir /tmp/ethdebug-output --rpc http://localhost:8545
   ```

## Example Output

### Function Call Trace

```
Function Call Trace: 0x2832a995d3e50c85599e7aa0343e93aa77460d6069466be4b81dbc1ea21a3994
Contract: TestContract
Gas used: 50835
Status: SUCCESS

Call Stack:
------------------------------------------------------------
#0 TestContract::runtime_dispatcher [entry] gas: 29631 @ TestContract.sol:1
  #1 increment [0x7cf5dab0] [external] gas: 29241 @ TestContract.sol:23
     steps: 99-966
     amount: 23
    #2 increment2 [internal] gas: 6322 @ TestContract.sol:39
       steps: 296-966
       amount: 23
      #3 increment3 [internal] gas: 5172 @ TestContract.sol:54
         steps: 529-966
         amount: 0
------------------------------------------------------------

Use --raw flag to see detailed instruction trace
```

The raw output:
```
$ soldb trace 0x123...abc --ethdebug-dir debug --raw

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

The output of reverted transaction

```
soldb trace 0x9b0a8e0776cea556b7bb0c7946bf917ebaf5cb403ed3179e84c44c188c694db3 --ethdebug-dir debug_order --ethdebug-dir debug_payment --ethdebug-dir debug_logger --ethdebug-dir debug_shipping_manager --ethdebug-dir debug_tax_calculator --rpc http://localhost:8545
Loading transaction 0x9b0a8e0776cea556b7bb0c7946bf917ebaf5cb403ed3179e84c44c188c694db3...

Function Call Trace: 0x9b0a8e0776cea556b7bb0c7946bf917ebaf5cb403ed3179e84c44c188c694db3
Loaded contracts:
  OrderProcessor (0x59A714559B46c823d87986b5c5B7C630e2f5668d)
  PaymentProcessor (0xf776FF56e2400e31f3070c1ac70Ab80433B01823)
  Logger (0xdcDd1dd0ff17043f8bCD1AC9E5Be20BBEd4FAc0A)
  ShippingManager (0xbE734aD6434E16f6bE04706005faED6fD38eb2B2)
  TaxCalculator (0x6a85ebf0Eba5307943bDF27D02d198Bc64e9ffEd)
Gas used: 38039
Status: REVERTED
Error: Order value must be positive

Call Stack:
------------------------------------------------------------
#0 OrderProcessor::runtime_dispatcher [entry] gas: 15851 @ OrderProcessor.sol:1
    #1 CALL → Logger::log(string) [0x41304fac] [CALL] → Logger gas: 3937
       steps: 397-658
       message: Starting order processing
    #2 CALL → TaxCalculator::calculateTax(uint256,string) [0x55ec8a03] [CALL] → TaxCalculator gas: 4600 !!!
       steps: 965-1241
       value: 0
       orderType: physical
------------------------------------------------------------

Use --raw flag to see detailed instruction trace
```

## Run tests

### Prerequisites

Tests expect RPC at `http://localhost:8545` (Anvil default) and use Anvil's test account private key. Also, it uses LLVM's `lit` and `FileCheck` tools, so before running tests, you need to install LLVM tools:

```bash
# macOS
brew install llvm

# Ubuntu
sudo apt-get install llvm-dev
```

### Running tests

```bash
cd test
./run-tests.sh SOLC_PATH=/path/to/solc
```

**NOTE**: Make sure Anvil is running with tracing enabled before running tests:
```bash
anvil --steps-tracing
```

## Advanced Setup

### Install from Source

For development or contributing to SolDB:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/walnuthq/soldb.git
   cd soldb
   ```
2. **Set up a Python virtual environment:**
   ```bash
   python3 -m venv MyEnv
   source MyEnv/bin/activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install SolDB in editable mode:**
   ```bash
   pip install -e .
   ```

## License

## License

SolDB is licensed under the GNU General Public License v3.0 (GPL-3.0), the same license used by Solidity and other Ethereum Foundation projects.

📄 [Full license text](./LICENSE.md)  
📬 Contact: hi@walnut.dev
