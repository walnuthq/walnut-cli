#!/usr/bin/env python3
"""
Command-line tool for compiling Solidity contracts with ETHDebug support.
Can be used standalone or integrated into the walnut-cli workflow.
"""

import argparse
import sys
import json
from pathlib import Path
from typing import Optional

from .compiler_config import CompilerConfig, CompilationError, dual_compile


def main():
    parser = argparse.ArgumentParser(
        description="Compile Solidity contracts with ETHDebug support"
    )
    
    parser.add_argument(
        "contract_file",
        help="Path to the Solidity contract file"
    )
    
    parser.add_argument(
        "--solc", "--solc-path",
        default="solc",
        help="Path to the solc binary (default: solc)"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        default="./build/debug/ethdebug",
        help="Output directory for ETHDebug files (default: ./build/debug/ethdebug)"
    )
    
    parser.add_argument(
        "--dual-compile",
        action="store_true",
        help="Create both optimized production and debug builds"
    )
    
    parser.add_argument(
        "--production-dir",
        default="./build/contracts",
        help="Output directory for production build (default: ./build/contracts)"
    )
    
    parser.add_argument(
        "--verify-version",
        action="store_true",
        help="Verify solc version supports ETHDebug and exit"
    )
    
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Save configuration to walnut.config.yaml"
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    
    args = parser.parse_args()
    
    # Create compiler configuration
    config = CompilerConfig(
        solc_path=args.solc,
        debug_output_dir=args.output_dir,
        build_dir=args.production_dir
    )
    
    # Verify version if requested
    if args.verify_version:
        version_info = config.verify_solc_version()
        if args.json:
            print(json.dumps(version_info, indent=2))
        else:
            if version_info["supported"]:
                print(f"✓ Solidity {version_info['version']} supports ETHDebug")
            else:
                print(f"✗ {version_info['error']}")
        sys.exit(0 if version_info["supported"] else 1)
    
    # Verify contract file exists
    if not Path(args.contract_file).exists():
        print(f"Error: Contract file '{args.contract_file}' not found", file=sys.stderr)
        sys.exit(1)
    
    # Save configuration if requested
    if args.save_config:
        try:
            config.save_to_walnut_config()
            if not args.json:
                print("✓ Configuration saved to walnut.config.yaml")
        except Exception as e:
            print(f"Error saving configuration: {e}", file=sys.stderr)
            sys.exit(1)
    
    try:
        if args.dual_compile:
            # Perform dual compilation
            results = dual_compile(args.contract_file, config)
            
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                # Production build status
                if results["production"]["success"]:
                    print(f"✓ Production build created in {results['production']['output_dir']}")
                else:
                    print(f"✗ Production build failed: {results['production'].get('error', 'Unknown error')}")
                
                # Debug build status
                if results["debug"]["success"]:
                    print(f"✓ ETHDebug build created in {results['debug']['output_dir']}")
                    
                    # List generated files
                    if results["debug"]["files"]["ethdebug"]:
                        print("  - ethdebug.json")
                    
                    for contract_name, files in results["debug"]["files"]["contracts"].items():
                        print(f"\n  Contract: {contract_name}")
                        if files["bytecode"]:
                            print(f"    - {contract_name}.bin")
                        if files["abi"]:
                            print(f"    - {contract_name}.abi")
                        if files["ethdebug"]:
                            print(f"    - {contract_name}_ethdebug.json")
                        if files["ethdebug_runtime"]:
                            print(f"    - {contract_name}_ethdebug-runtime.json")
                else:
                    print(f"✗ ETHDebug build failed: {results['debug'].get('error', 'Unknown error')}")
                    sys.exit(1)
        
        else:
            # ETHDebug compilation only
            result = config.compile_with_ethdebug(args.contract_file)
            
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"✓ ETHDebug compilation successful")
                print(f"Output directory: {result['output_dir']}")
                
                # List generated files
                if result["files"]["ethdebug"]:
                    print("\nGenerated files:")
                    print("  - ethdebug.json")
                
                for contract_name, files in result["files"]["contracts"].items():
                    print(f"\n  Contract: {contract_name}")
                    if files["bytecode"]:
                        print(f"    - {contract_name}.bin")
                    if files["abi"]:
                        print(f"    - {contract_name}.abi")
                    if files["ethdebug"]:
                        print(f"    - {contract_name}_ethdebug.json")
                    if files["ethdebug_runtime"]:
                        print(f"    - {contract_name}_ethdebug-runtime.json")
                
                # Show any warnings
                if result["stderr"]:
                    print("\nCompiler warnings:")
                    print(result["stderr"])
    
    except CompilationError as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, indent=2))
        else:
            print(f"Compilation failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()