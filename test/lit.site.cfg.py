import sys
import os

config.walnut_cli_dir = "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli"
config.walnut_cli = "walnut-cli"
config.rpc_url = "http://localhost:8545"
config.chain_id = "1"
config.private_key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
config.test_contracts = {
    "contract_address": "0x2a08133a3355634e46e3ba8d6e15d5c35f0202e4",
    "deploy_tx": "0x219555b420eb6924aceef9633171ef0f10f3b8c5ad5582a9201d287bdb42a59a",
    "test_tx": "0x08aca7e46db0d619e5e08cea5d13ced62036b79d1da9228df56806ca3c4d913b",
    "ethdebug_dir": "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli/examples/debug"
}
config.solc_path = "/Users/djtodorovic/projects/crypto/SOLIDITY/OPTIMISM/solidity/build/solc/solc"

# Load the main config
lit_config.load_config(config, "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli/test/lit.cfg.py")
