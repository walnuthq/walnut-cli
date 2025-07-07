# Walnut EVM Debugger

A transaction-based debugger for Solidity smart contracts.

<img width="1417" alt="internal-calls" src="https://github.com/user-attachments/assets/3f795fcd-6db0-4ad8-a9e0-3466b2f4a39c" />

## Features

1. Transaction tracing

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

#### For ETHDebug format (Recommended):

1. **Standard Solidity compiler** (0.8.13+):
   ```bash
   # Install via package manager or download from https://github.com/ethereum/solidity/releases
   brew install solidity  # macOS
   # or
   sudo apt-get install solc  # Ubuntu
   ```

#### For contract deployment:

2. **Foundry**: For contract deployment and interaction
   ```bash
   curl -L https://foundry.paradigm.xyz | bash
   foundryup
   ```

### Setup

After installation, run the setup script to configure external tools (only needed for DWARF format):
```bash
walnut-setup  # If installed via pip
# or
./setup-walnut.sh  # If running from source
```

This will:
- Find or ask for the path to solx (experimental DWARF format only)
- Find or ask for the path to evm-dwarf (experimental DWARF format only)
- Configure RPC endpoint and private key
- Create `walnut.config.local` with your settings

**Note**: If you're only using ETHDebug format (recommended), you can skip this step and use the tool directly.

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

# Private key for deployments
PRIVATE_KEY="0x..."

# Debug output directory
DEBUG_DIR="debug"
```

## Usage

NOTE: There is an experimental support for `solx` compiler. The defualt for now should be `solc`.

### 1. Run node

```
$ docker run -it --rm --name nitro-dev -p 8547:8547 offchainlabs/nitro-node:v3.5.3-rc.3-653b078 --dev --http.addr 0.0.0.0 --http.api=net,web3,eth,arb,arbdebug,debug
```

TODO: Try with OP node!

### 2. Deploy a Contract

Deploy a Solidity contract with debug information:

#### Using solc with ETHDebug (Recommended):

```bash
# Auto-detects solc and uses ethdebug format
./scripts/deploy-contract.sh Counter src/Counter.sol

# Explicitly use solc
./scripts/deploy-contract.sh --compiler=solc Counter src/Counter.sol

# With custom settings
./scripts/deploy-contract.sh \
  --compiler=solc \
  --rpc=http://localhost:8545 \
  --debug-dir=my-debug \
  Counter src/Counter.sol
```

This will:
- Compile with `solc --via-ir --debug-info ethdebug --ethdebug`
- Deploy to the blockchain
- Save ethdebug JSON files to `./debug/ethdebug_output/`
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

#### Method 1: Trace

```bash
./walnut-cli.py 0x123... --ethdebug-dir ./debug/ethdebug_output
```

This shows a high-level function call trace with gas usage and source mappings.

#### Method 2: Interactive REPL

TBD

## Debug Information Formats

### ETHDebug Format

This approach is to use the standard ethdebug format from the Solidity compiler:

1. **Generate ethdebug information**:
   ```bash
   solc --via-ir --debug-info ethdebug --ethdebug -o /tmp/ethdebug-output MyContract.sol
   ```
   This generates:
   - `ethdebug.json` - Compilation metadata
   - `MyContract_ethdebug.json` - Constructor/creation debug info
   - `MyContract_ethdebug-runtime.json` - Runtime debug info

2. **Trace transactions with ethdebug**:
   ```bash
   ./walnut-cli.py 0x123...abc --ethdebug-dir /tmp/ethdebug-output
   ```

### Other formats

TBD (e.g. DWARF, and LLVM Debug Info Metadata)

## Debugging Workflow

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
   # With solc (ethdebug format - recommended)
   ./scripts/deploy-contract.sh Counter src/Counter.sol
   
   # Output:
   # Using solc compiler with ethdebug format (recommended)
   # Transaction: 0x123...
   # Contract deployed at: 0xabc...
   # ETHDebug files created in: debug/ethdebug_output   
   ```

3. **Interact and get transaction hash**:
   ```bash
   ./scripts/interact-contract.sh set 42
   # Returns: Transaction: 0x123...
   ```

4. **Debug the transaction**:
   ```bash
   ./walnut-cli.py 0x123... --ethdebug-dir ./debug/ethdebug_output
   # Shows function call trace with proper function names
   ```

## Example Output

```
walnut-cli.py 0x2832a995d3e50c85599e7aa0343e93aa77460d6069466be4b81dbc1ea21a3994 --ethdebug-dir tmp/ethdebug_output --rpc http://localhost:8547
Loading transaction 0x2832a995d3e50c85599e7aa0343e93aa77460d6069466be4b81dbc1ea21a3994...
Loaded 1833 PC mappings from ethdebug
Contract: TestContract
Environment: runtime

Function Call Trace: 0x2832a995d3e50c85599e7aa0343e93aa77460d6069466be4b81dbc1ea21a3994
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
$ ./walnut-cli.py 0x123...abc --ethdebug-dir /tmp/ethdebug-output --raw

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

It expects RPC at `http://localhost:8547` and uses `0xb6b15c8cb491557369f3c7d2c287b053eb229daa9c22138887752191c9520659` key by default.
Also, it uses LLVM's `lit` and `FileCheck` tools, so please install it.

## License

Walnut is licensed under the Business Source License 1.1 (BSL). You may use, self-host, and modify Walnut for non-commercial purposes.

To use Walnut in a commercial product or service (e.g. as a SaaS offering), you must obtain a commercial license.

📄 [Full license text](./LICENSE.md)  
📬 Contact: hi@walnut.dev
