import sys
import os

config.walnut_cli_dir = "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli"
config.walnut_cli = "walnut-cli"
config.rpc_url = "http://localhost:8547"
config.chain_id = "412346"
config.private_key = "0xb6b15c8cb491557369f3c7d2c287b053eb229daa9c22138887752191c9520659"
config.test_contracts = {
    "contract_address": "",
    "deploy_tx": "",
    "test_tx": "0x8a387193d19ae8ff6d15b32b7abec4144601d98da8c2af1eebd9cf4061c033a7",
    "ethdebug_dir": "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli/examples/debug/ethdebug_output"
}
config.solc_path = "/Users/djtodorovic/projects/crypto/SOLIDITY/OPTIMISM/solidity/build/solc/solc"

# Load the main config
lit_config.load_config(config, "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli/test/lit.cfg.py")
