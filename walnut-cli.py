#!/usr/bin/env python3
"""
Trace and debug an Ethereum transaction

Usage: walnut-cli.py <tx_hash> [options]

Options:
  --ethdebug-dir <dir>                Load ethdebug format from directory
  --rpc <url>                         RPC endpoint (default: http://localhost:8545)
"""

import sys
import os
import argparse
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from walnut_cli.transaction_tracer import TransactionTracer, SourceMapper


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


def main():
    parser = argparse.ArgumentParser(description='Trace and debug an Ethereum transaction')
    parser.add_argument('tx_hash', help='Transaction hash to trace')
    # parser.add_argument('--debug-info-from-zasm-file', '-d', help='Load debug info from .zasm file (solx/evm-dwarf format)')
    parser.add_argument('--ethdebug-dir', '-e', help='ETHDebug directory containing ethdebug.json and contract debug files')
    parser.add_argument('--rpc', '-r', default='http://localhost:8545', help='RPC URL')
    parser.add_argument('--max-steps', '-m', type=int, default=50, help='Maximum steps to show (use 0 or -1 for all steps)')
    parser.add_argument('--interactive', '-i', action='store_true', help='Start interactive debugger')
    parser.add_argument('--raw', action='store_true', help='Show raw instruction trace instead of function call trace')
    
    args = parser.parse_args()
    
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
    if args.ethdebug_dir:
        # Load ethdebug format
        if args.interactive:
            # Suppress output for interactive mode
            import io
            import contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                source_map = tracer.load_ethdebug_info(args.ethdebug_dir)
        else:
            source_map = tracer.load_ethdebug_info(args.ethdebug_dir)
        # Try to load ABI from ethdebug directory
        if tracer.ethdebug_info:
            abi_path = os.path.join(args.ethdebug_dir, f"{tracer.ethdebug_info.contract_name}.abi")
            if os.path.exists(abi_path):
                tracer.load_abi(abi_path)
        else:
            # Try to find any ABI file in the directory
            for abi_file in Path(args.ethdebug_dir).glob("*.abi"):
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
        from walnut_cli.evm_repl import EVMDebugger
        
        debugger = EVMDebugger(
            contract_address=trace.to_addr,
            debug_file=debug_file,
            rpc_url=args.rpc,
            ethdebug_dir=args.ethdebug_dir
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


if __name__ == '__main__':
    sys.exit(main())