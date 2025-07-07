import sys
import os

config.walnut_cli_dir = "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli"
config.walnut_cli = "walnut-cli"
config.rpc_url = "http://localhost:8545"
config.chain_id = "1"
config.private_key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
config.test_contracts = {
    "contract_address": "0x82e8f00d62fa200af7cfcc8f072ae0525e1a43fb",
    "deploy_tx": "0x88d57d015aac930d30c1412b867878697b9de8e2ff277388248413a1365a4c00",
    "test_tx": "0x1cb46641460fbb71e576a6bb03c80f43e4b27811d640234139aefbd6c424fc0a",
    "ethdebug_dir": "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli/examples/debug"
}
config.solc_path = "/Users/djtodorovic/projects/crypto/SOLIDITY/OPTIMISM/solidity/build/solc/solc"

# Load the main config
lit_config.load_config(config, "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli/test/lit.cfg.py")
