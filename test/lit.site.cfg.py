import sys
import os

config.walnut_cli_dir = "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli"
config.walnut_cli = "walnut-cli"
config.rpc_url = "http://localhost:8547"
config.chain_id = "412346"
config.private_key = "0xb6b15c8cb491557369f3c7d2c287b053eb229daa9c22138887752191c9520659"
config.test_contracts = {
    "contract_address": "0xb81d32e78506aade6b7823991e2474ddf33c0c3b",
    "deploy_tx": "0x9785d974c75b2aec7f1398a60640b7fa74dc7e4aff4e306cdb8c45e42e9402fc",
    "test_tx": "0xd5568c1294c66b74f172efc10016a1b932ba059e13ad636bc7885af0b2da6dae",
    "ethdebug_dir": "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli/examples/debug"
}
config.solc_path = "/Users/djtodorovic/projects/crypto/SOLIDITY/OPTIMISM/solidity/build/solc/solc"

# Load the main config
lit_config.load_config(config, "/Users/djtodorovic/projects/crypto/SOLIDITY/walnut-cli/test/lit.cfg.py")
