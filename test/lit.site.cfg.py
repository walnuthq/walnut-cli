import sys
import os

config.walnut_cli_dir = "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli"
config.walnut_cli = "walnut-cli"
config.rpc_url = "http://localhost:8545"
config.chain_id = "1"
config.private_key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
config.test_contracts = {
    "contract_address": "0xec67cf0755c0a5aad6c4a4235fdfa35c1efea6a9",
    "deploy_tx": "0x3d04a674ded882aa58d8a801f5cb2cddc385d8b33b37a617da0b1445cfd50724",
    "test_tx": "0xa825796b97068f485d83036a5d50b347d444600b6bbb9f519daf66902516325f",
    "ethdebug_dir": "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli/examples/debug"
}
config.solc_path = "/Users/djtodorovic/projects/crypto/SOLIDITY/OPTIMISM/solidity/build/solc/solc"

# Load the main config
lit_config.load_config(config, "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli/test/lit.cfg.py")
