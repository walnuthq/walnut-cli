#!/usr/bin/env python3
"""
Main entry point for walnut-cli
"""

import sys
import os
import argparse
import json
from pathlib import Path

from .transaction_tracer import TransactionTracer, SourceMapper
from .evm_repl import EVMDebugger
from .multi_contract_ethdebug_parser import MultiContractETHDebugParser


def find_debug_file(contract_addr: str) -> str:
    """Try to find debug file for a contract."""
    debug_dir = Path("debug")
    if debug_dir.exists():
        # Look for deployment.json
        deployment_file = debug_dir / "deployment.json"
        if deployment_file.exists():
            with open(deployment_file) as f:
                deployment = json.load(f)
                if deployment.get('address', '').lower() == contract_addr.lower():
                    # Find matching .zasm file
                    for zasm_file in debug_dir.glob("*.runtime.zasm"):
                        return str(zasm_file)
    
    # Look for any .zasm file
    for zasm_file in Path(".").glob("**/*.runtime.zasm"):
        return str(zasm_file)
    
    return None


def trace_command(args):
    """Execute the trace command."""
    
    # Create tracer
    tracer = TransactionTracer(args.rpc)
    
    # Trace transaction
    print(f"Loading transaction {args.tx_hash}...")
    trace = tracer.trace_transaction(args.tx_hash)
    
    # Try to find debug file if not provided
    debug_file = getattr(args, 'debug_info_from_zasm_file', None)
    if not debug_file:
        # For deployment transactions, check deployment.json
        if not trace.to_addr:  # Deployment transaction
            debug_dir = Path("debug")
            if not debug_dir.exists():
                debug_dir = Path(".")
            deployment_file = debug_dir / "deployment.json"
            if deployment_file.exists():
                with open(deployment_file) as f:
                    deployment = json.load(f)
                    if deployment.get('transaction', '').lower() == args.tx_hash.lower():
                        # Find matching .zasm file
                        for zasm_file in debug_dir.glob("*.zasm"):
                            debug_file = str(zasm_file)
                            print(f"Found debug file for deployment: {debug_file}")
                            break
        else:
            debug_file = find_debug_file(trace.to_addr)
            if debug_file:
                print(f"Found debug file: {debug_file}")
    
    # Load debug info (but skip the output if going into interactive mode)
    source_map = {}
    
    # Check if multi-contract mode is enabled or multiple directories provided
    if args.multi_contract or (args.ethdebug_dir and len(args.ethdebug_dir) > 1) or args.contracts:
        # Multi-contract mode
        multi_parser = MultiContractETHDebugParser()
        
        # Load from contracts mapping file if provided
        if args.contracts:
            multi_parser.load_from_mapping_file(args.contracts)
        
        # Load from ethdebug directories
        if args.ethdebug_dir:
            for ethdebug_spec in args.ethdebug_dir:
                # Parse address:path format
                if ':' in ethdebug_spec:
                    address, path = ethdebug_spec.split(':', 1)
                    multi_parser.load_contract(address, path)
                else:
                    # Try to load from deployment.json in the directory
                    deployment_file = Path(ethdebug_spec) / "deployment.json"
                    if deployment_file.exists():
                        multi_parser.load_from_deployment(deployment_file)
                    else:
                        print(f"Warning: No deployment.json found in {ethdebug_spec}, skipping...")
        
        # Set the multi-contract parser on the tracer
        tracer.multi_contract_parser = multi_parser
        
        # Try to set primary contract based on transaction
        if trace.to_addr:
            primary_contract = multi_parser.get_contract_at_address(trace.to_addr)
            if primary_contract:
                tracer.ethdebug_parser = primary_contract.parser
                tracer.ethdebug_info = primary_contract.ethdebug_info
                source_map = primary_contract.parser.get_source_mapping()
                
                # Load ABI for primary contract
                abi_path = primary_contract.debug_dir / f"{primary_contract.name}.abi"
                if abi_path.exists():
                    tracer.load_abi(str(abi_path))
    
    elif args.ethdebug_dir and len(args.ethdebug_dir) == 1:
        # Single contract mode (backward compatibility)
        ethdebug_dir = args.ethdebug_dir[0]
        if args.interactive:
            # Suppress output for interactive mode
            import io
            import contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                source_map = tracer.load_ethdebug_info(ethdebug_dir)
        else:
            source_map = tracer.load_ethdebug_info(ethdebug_dir)
        # Try to load ABI from ethdebug directory
        if tracer.ethdebug_info:
            abi_path = os.path.join(ethdebug_dir, f"{tracer.ethdebug_info.contract_name}.abi")
            if os.path.exists(abi_path):
                tracer.load_abi(abi_path)
        else:
            # Try to find any ABI file in the directory
            for abi_file in Path(ethdebug_dir).glob("*.abi"):
                tracer.load_abi(str(abi_file))
                break
    elif debug_file:
        # Load debug info from zasm format
        source_map = tracer.load_debug_info(debug_file)
        # Try to find ABI in same directory
        debug_dir = os.path.dirname(debug_file)
        for abi_file in Path(debug_dir).glob("*.abi"):
            tracer.load_abi(str(abi_file))
            break
    
    # Print trace based on mode (but skip if going into interactive mode)
    if not args.interactive:
        if args.raw:
            # Show detailed instruction trace
            tracer.print_trace(trace, source_map, args.max_steps)
        else:
            # Show pretty function call trace
            function_calls = tracer.analyze_function_calls(trace)
            tracer.print_function_trace(trace, function_calls)
    else:
        # Just analyze function calls for interactive mode
        function_calls = tracer.analyze_function_calls(trace)
    
    # Start interactive debugger if requested
    if args.interactive:
        print("\nStarting interactive debugger...")
        
        debugger = EVMDebugger(
            contract_address=trace.to_addr,
            debug_file=debug_file,
            rpc_url=args.rpc,
            ethdebug_dir=args.ethdebug_dir[0] if args.ethdebug_dir else None,
            multi_contract_parser=getattr(tracer, 'multi_contract_parser', None)
        )
        
        # Pre-load the trace and function analysis
        debugger.current_trace = trace
        debugger.current_step = 0
        debugger.function_trace = function_calls
        
        # Start at first function after dispatcher
        if len(function_calls) > 1:
            debugger.current_step = function_calls[1].entry_step
            debugger.current_function = function_calls[1]
        
        # Start REPL
        try:
            debugger.cmdloop()
        except KeyboardInterrupt:
            print("\nInterrupted")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description='Walnut CLI - Ethereum transaction analysis tool')
    parser.add_argument('--version', '-v', action='version', version='%(prog)s 0.1.0')
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    subparsers.required = True
    
    # Create the 'trace' subcommand
    trace_parser = subparsers.add_parser('trace', help='Trace and debug an Ethereum transaction')
    trace_parser.add_argument('tx_hash', help='Transaction hash to trace')
    # trace_parser.add_argument('--debug-info-from-zasm-file', '-d', help='Load debug info from .zasm file (solx/evm-dwarf format)')
    trace_parser.add_argument('--ethdebug-dir', '-e', action='append', help='ETHDebug directory containing ethdebug.json and contract debug files. Can be specified multiple times for multi-contract debugging. Format: [address:]path or just path')
    trace_parser.add_argument('--contracts', '-c', help='JSON file mapping contract addresses to debug directories')
    trace_parser.add_argument('--multi-contract', action='store_true', help='Enable multi-contract debugging mode')
    trace_parser.add_argument('--rpc', '-r', default='http://localhost:8545', help='RPC URL')
    trace_parser.add_argument('--max-steps', '-m', type=int, default=50, help='Maximum steps to show (use 0 or -1 for all steps)')
    trace_parser.add_argument('--interactive', '-i', action='store_true', help='Start interactive debugger')
    trace_parser.add_argument('--raw', action='store_true', help='Show raw instruction trace instead of function call trace')
    
    args = parser.parse_args()
    
    # Handle commands
    if args.command == 'trace':
        return trace_command(args)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
