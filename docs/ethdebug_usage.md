# ETHDebug Support in Walnut CLI

## Overview

Walnut CLI now supports the ETHDebug format for enhanced debugging capabilities. ETHDebug provides standardized debugging information that maps low-level EVM bytecode execution to high-level Solidity code concepts, including precise variable and parameter locations.

## Requirements

- Solidity compiler version 0.8.29 or later
- `--via-ir` compilation flag enabled

## Quick Start

### 1. Compile with ETHDebug

Use the new deployment script:

```bash
./scripts/deploy-contract-ethdebug.sh Counter examples/Counter.sol
```

Or use the Python compilation tool:

```bash
python -m walnut_cli.compile_ethdebug examples/TestContract.sol
```

### 2. Debug with ETHDebug

After deployment, trace transactions with ETHDebug support:

```bash
./walnut-cli.py <transaction_hash> --ethdebug-dir build/debug/ethdebug
```

## Features

### Enhanced Compilation Pipeline

The new compiler configuration module (`compiler_config.py`) provides:

- Automatic Solidity version verification
- ETHDebug compilation with optimized settings
- Dual compilation support (production + debug builds)
- Configuration management via `walnut.config.yaml`

### Extended Parser Capabilities

The ETHDebug parser now supports:

- Variable location tracking (stack, memory, storage)
- Variable scope and lifetime information
- Type information for proper value decoding
- Enhanced source mapping with variable context

### Variable Location Data Structures

```python
@dataclass
class VariableLocation:
    name: str
    type: str
    location_type: str  # "stack", "memory", "storage"
    offset: int
    pc_range: Tuple[int, int]  # (start_pc, end_pc)
```

## Configuration

Create or update `walnut.config.yaml`:

```yaml
debug:
  ethdebug:
    enabled: true
    path: "./build/debug/ethdebug"
    fallback_to_heuristics: true
    compile_options:
      via_ir: true
      optimizer: true
      optimizer_runs: 200
```

## Command Line Tools

### deploy-contract-ethdebug.sh

Enhanced deployment script with ETHDebug support:

```bash
# Basic usage
./scripts/deploy-contract-ethdebug.sh Counter src/Counter.sol

# With dual compilation
./scripts/deploy-contract-ethdebug.sh --dual-compile Counter src/Counter.sol

# Custom Solidity path
./scripts/deploy-contract-ethdebug.sh --solc=/path/to/solc Counter src/Counter.sol
```

### compile_ethdebug.py

Standalone compilation tool:

```bash
# Compile with ETHDebug
python -m walnut_cli.compile_ethdebug contract.sol

# Verify Solidity version
python -m walnut_cli.compile_ethdebug --verify-version contract.sol

# Dual compilation
python -m walnut_cli.compile_ethdebug --dual-compile contract.sol

# JSON output
python -m walnut_cli.compile_ethdebug --json contract.sol
```

## API Usage

### Compiling with ETHDebug

```python
from walnut_cli.compiler_config import CompilerConfig

config = CompilerConfig()
result = config.compile_with_ethdebug("MyContract.sol")

if result['success']:
    print(f"ETHDebug files: {result['files']}")
```

### Parsing ETHDebug Information

```python
from walnut_cli.ethdebug_parser import ETHDebugParser

parser = ETHDebugParser()
debug_info = parser.load_ethdebug_files("./build/debug/ethdebug")

# Get variables at a specific PC
variables = debug_info.get_variables_at_pc(142)
for var in variables:
    print(f"{var.name}: {var.type} @ {var.location_type}[{var.offset}]")
```

### Getting Variable Values

```python
# Format variables with actual values from execution state
var_display = parser.format_variables_debug(
    pc=142,
    stack=step.stack,
    memory=step.memory,
    storage=step.storage
)
print(var_display)
```

## Output Example

With ETHDebug support, debugging output now includes variable information:

```
Step 142 | PC: 0x8e | DUP2 | Gas: 47823
Stack: [0] 0x0123..., [1] 42, [2] 0xabcd...
Local Variables:
  - amount: 0x2a (uint256) @ stack[1]
  - recipient: 0xabcd... (address) @ stack[2]
Source: contracts/Token.sol:45:16
```

## Troubleshooting

### Solidity Version Error

If you see "Solidity X.X.X does not support ETHDebug format":
- Upgrade to Solidity 0.8.29 or later
- Install via: `npm install -g solc@latest`

### Missing ETHDebug Files

If ETHDebug files are not generated:
- Ensure `--via-ir` flag is enabled
- Check compilation logs in `debug/compile.log`
- Verify the output directory has write permissions

### Variable Information Not Available

Current ETHDebug specification is evolving. Variable location data may not be available for all contracts. The parser will gracefully handle missing data and fall back to standard debugging information.

## Future Enhancements

As the ETHDebug format specification evolves, we plan to add:
- Complex type decoding (structs, arrays)
- Return value tracking
- Cross-contract call variable tracking
- Memory and storage visualization
- Integration with source-level breakpoints