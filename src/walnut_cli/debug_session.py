import subprocess
import os
import re
import json
import shutil
from pathlib import Path
from web3 import Web3

from .evm_repl import EVMDebugger
from .colors import info, warning, error
from .compiler_config import CompilerConfig, CompilationError, dual_compile

class AutoDeployDebugger:
    """
    A class to automate compiling, deploying, and debugging a contract.
    Performs a dual compile for production deployment and debug symbols.
    """
    def __init__(self, contract_file: str, rpc_url: str = "http://localhost:8545", constructor_args: list = None):
        self.contract_path = Path(contract_file)
        if not self.contract_path.exists():
            raise FileNotFoundError(f"Contract file not found: {contract_file}")
        
        self.contract_name = self.contract_path.stem
        self.rpc_url = rpc_url
        self.constructor_args = constructor_args or []
        self.contract_address = None
        
        # Paths for artifacts will be set after compilation
        self.abi_path = None
        self.bin_path = None
        self.debug_dir = None
        
        # This config will be used by dual_compile
        self.compiler_config = CompilerConfig(
            debug_output_dir="./build/debug",
            build_dir="./build/contracts"
        )

    def compile_contract(self):
        """Performs a dual compile for both production and debug artifacts."""
        print(info("\n--- Compiling Contract ---"))

        # Clean previous build artifacts to ensure a fresh compile
        build_dir = Path("./build")
        if build_dir.exists():
            print(f"Cleaning previous build directory: {build_dir}")
            shutil.rmtree(build_dir)

        try:
            # Use dual_compile to get both production and debug builds
            results = dual_compile(str(self.contract_path), self.compiler_config)

            # Check production build for deployment artifacts
            prod_results = results.get("production", {})
            if not prod_results.get("success"):
                raise CompilationError(f"Production build failed: {prod_results.get('error', 'Unknown error')}")
            
            prod_output_dir = Path(prod_results["output_dir"])
            self.abi_path = prod_output_dir / f"{self.contract_name}.abi"
            self.bin_path = prod_output_dir / f"{self.contract_name}.bin"
            
            if not self.abi_path.exists() or not self.bin_path.exists():
                raise FileNotFoundError(f"Couldn't find ABI/BIN artifacts for deployment in {prod_output_dir}")
            
            print(f"✓ Production build created in {prod_output_dir}")

            # Check debug build for debugging artifacts
            debug_results = results.get("debug", {})
            if not debug_results.get("success"):
                raise CompilationError(f"Debug build failed: {debug_results.get('error', 'Unknown error')}")

            self.debug_dir = Path(debug_results["output_dir"])
            print(f"✓ Debug build created in {self.debug_dir}")

        except (CompilationError, FileNotFoundError) as e:
            print(error(f"Compilation failed: {e}"))
            raise
        except Exception as e:
            print(error(f"An unexpected error occurred during compilation: {e}"))
            raise

    def deploy_contract(self):
        """Deploys the (optimized) compiled contract using web3.py."""
        print(info("\n--- Deploying Contract ---"))
        if not self.abi_path or not self.bin_path:
            raise FileNotFoundError("Contract artifacts (ABI/BIN) not found. Please compile first.")

        try:
            w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not w3.is_connected():
                raise ConnectionError(f"Could not connect to RPC URL: {self.rpc_url}")

            with open(self.abi_path, 'r') as f:
                abi = json.load(f)
            with open(self.bin_path, 'r') as f:
                bytecode = f.read().strip()

            Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
            deployer = w3.eth.accounts[0]
            
            print(f"Deploying {self.contract_name} from account {deployer}")
            tx_hash = Contract.constructor(*self.constructor_args).transact({'from': deployer})
            
            tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            
            self.contract_address = tx_receipt.contractAddress
            print(f"✓ Successfully deployed {self.contract_name} to {self.contract_address}")

        except Exception as e:
            print(error(f"Deployment failed: {e}"))
            raise

    def run(self, function_name: str = None, function_args: list = None):
        """Runs the full compile, deploy, and debug workflow."""
        self.compile_contract()
        self.deploy_contract()
