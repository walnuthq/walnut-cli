"""
EVM REPL Debugger

Interactive REPL for debugging EVM transactions with source mapping.
"""

import cmd
import os
import json
from typing import Optional, Dict, List, Tuple
from .transaction_tracer import TransactionTracer, TransactionTrace, SourceMapper
from .dwarf_parser import load_dwarf_info, DwarfParser
from .colors import *

class EVMDebugger(cmd.Cmd):
    """Interactive EVM debugger REPL."""
    
    intro = f"""
{bold('Walnut EVM Debugger')} - Solidity Debugger
Type {info('help')} for commands. Use {info('run <tx_hash>')} to start debugging.
    """
    prompt = f'{cyan("(walnut-cli)")} '
    
    def __init__(self, contract_address: str = None, debug_file: str = None, 
                 rpc_url: str = "http://localhost:8545", ethdebug_dir: str = None):
        super().__init__()
        
        self.tracer = TransactionTracer(rpc_url)
        self.current_trace = None
        self.current_step = 0
        self.breakpoints = set()
        self.watch_expressions = []
        self.display_mode = "source"  # "source" or "asm"
        self.function_trace = []  # Function call trace
        
        # Load contract and debug info
        self.contract_address = contract_address
        self.debug_file = debug_file
        self.ethdebug_dir = ethdebug_dir
        self.source_map = {}
        self.source_mapper = None
        self.dwarf_info = None
        self.source_lines = {}  # filename -> lines
        self.current_function = None  # Current function context
        
        # Load ETHDebug info if available
        if ethdebug_dir:
            self.source_map = self.tracer.load_ethdebug_info(ethdebug_dir)
            # Load ABI from ethdebug directory
            if self.tracer.ethdebug_info:
                abi_path = os.path.join(ethdebug_dir, f"{self.tracer.ethdebug_info.contract_name}.abi")
                if os.path.exists(abi_path):
                    self.tracer.load_abi(abi_path)
            
        elif debug_file:
            self.source_map = self.tracer.load_debug_info(debug_file)
            
            # Try to load DWARF debug ELF
            debug_elf = debug_file.replace('.zasm', '.debug.elf')
            if not os.path.exists(debug_elf):
                # Try in same directory with different naming
                base_name = os.path.basename(debug_file).split('.')[0].split('_')[0]
                debug_elf = os.path.join(os.path.dirname(debug_file), f"{base_name}.debug.elf")
            
            if os.path.exists(debug_elf):
                print(f"Loading DWARF debug info from: {info(debug_elf)}")
                self.dwarf_info = load_dwarf_info(debug_elf)
                if self.dwarf_info:
                    print(f"Loaded {success(str(len(self.dwarf_info.functions)))} functions from DWARF")
        
        # Load source files
        self._load_source_files()
        
        if contract_address:
            print(f"Contract loaded: {address(contract_address)}")
        
        # Only print debug mappings message if we loaded them here (not passed from main)
        if self.source_map and not ethdebug_dir:
            print(f"Loaded {success(str(len(self.source_map)))} debug mappings")
    
    def _load_source_files(self):
        """Load all source files referenced in debug info."""
        if self.tracer.ethdebug_info:
            # Load from ETHDebug sources
            for source_id, source_path in self.tracer.ethdebug_info.sources.items():
                lines = self.tracer.ethdebug_parser.load_source_file(source_path)
                if lines:
                    self.source_lines[source_path] = lines
                    print(f"Loaded source: {info(os.path.basename(source_path))}")
        elif self.debug_file:
            # Extract source file from debug file name
            source_file = self.debug_file.split('_')[0]
            if os.path.exists(source_file):
                with open(source_file, 'r') as f:
                    self.source_lines[source_file] = f.readlines()
                print(f"Loaded source: {info(source_file)}")
    
    def do_run(self, tx_hash: str):
        """Run/load a transaction for debugging. Usage: run <tx_hash>"""
        if not tx_hash:
            print("Usage: run <tx_hash>")
            return
        
        print(f"Loading transaction {info(tx_hash)}...")
        try:
            self.current_trace = self.tracer.trace_transaction(tx_hash)
            self.current_step = 0
            
            # Analyze function calls
            self.function_trace = self.tracer.analyze_function_calls(self.current_trace)
            
            print(f"{success('Transaction loaded.')} {highlight(str(len(self.current_trace.steps)))} steps.")
            print(f"Type {info('continue')} to run, {info('next')} to step by source line, {info('nexti')} to step by instruction")
            
            # Start at the first function call after dispatcher
            if len(self.function_trace) > 1:
                self.current_step = self.function_trace[1].entry_step
                self.current_function = self.function_trace[1]
            
            self._show_current_state()
        except Exception as e:
            print(f"{error('Error loading transaction:')} {e}")
    
    def do_nexti(self, arg):
        """Step to next instruction (instruction-level). Aliases: ni, stepi, si"""
        if not self.current_trace:
            print("No transaction loaded. Use 'run <tx_hash>' first.")
            return
        
        if self.current_step >= len(self.current_trace.steps) - 1:
            print(info("Already at end of execution."))
            return
            
        self.current_step += 1
        self._update_current_function()
        self._show_current_state()
    
    def do_ni(self, arg):
        """Alias for nexti"""
        self.do_nexti(arg)
    
    def do_stepi(self, arg):
        """Alias for nexti"""
        self.do_nexti(arg)
    
    def do_si(self, arg):
        """Alias for nexti"""
        self.do_nexti(arg)
    
    def do_next(self, arg):
        """Step to next source line (source-level). Aliases: n, step, s"""
        if not self.current_trace:
            print("No transaction loaded. Use 'run <tx_hash>' first.")
            return
        
        if self.current_step >= len(self.current_trace.steps) - 1:
            print(info("Already at end of execution."))
            return
        
        if not self.source_map:
            print("No source mapping available. Use 'nexti' for instruction stepping.")
            self.do_nexti(arg)
            return
        
        # Get current source line
        current_line = self._get_source_line_for_step(self.current_step)
        if current_line is None:
            # No source mapping, fall back to instruction stepping
            self.do_nexti(arg)
            return
        
        # Step until we reach a different source line
        initial_step = self.current_step
        while self.current_step < len(self.current_trace.steps) - 1:
            self.current_step += 1
            new_line = self._get_source_line_for_step(self.current_step)
            
            if new_line is not None and new_line != current_line:
                # Reached a new source line
                self._update_current_function()
                self._show_current_state()
                return
        
        # Reached end without finding new source line
        print(info("Already at end of execution."))
        # Reset to where we were since we didn't find a new line
        self.current_step = len(self.current_trace.steps) - 1
        self._update_current_function()
    
    def do_n(self, arg):
        """Alias for next"""
        self.do_next(arg)
    
    def do_step(self, arg):
        """Alias for next"""
        self.do_next(arg)
    
    def do_s(self, arg):
        """Alias for next"""
        self.do_next(arg)
    
    def do_continue(self, arg):
        """Continue execution until breakpoint or end. Alias: c"""
        if not self.current_trace:
            print("No transaction loaded. Use 'run <tx_hash>' first.")
            return
        
        if self.current_step >= len(self.current_trace.steps) - 1:
            print(info("Already at end of execution."))
            return
        
        initial_step = self.current_step
        while self.current_step < len(self.current_trace.steps) - 1:
            self.current_step += 1
            step = self.current_trace.steps[self.current_step]
            
            # Check breakpoints
            if step.pc in self.breakpoints:
                print(f"\n{warning('Breakpoint hit')} at PC {pc_value(step.pc)}")
                self._show_current_state()
                return
            
            # Check for errors
            if step.error:
                print(f"\nExecution error: {step.error}")
                self._show_current_state()
                return
        
        print(info("Execution completed."))
        self._show_current_state()
    
    def do_c(self, arg):
        """Alias for continue"""
        self.do_continue(arg)
    
    def do_break(self, arg):
        """Set breakpoint. Usage: break <pc> or break <file>:<line>"""
        if not arg:
            # List breakpoints
            if self.breakpoints:
                print("Breakpoints:")
                for bp in sorted(self.breakpoints):
                    print(f"  PC {bp}")
            else:
                print("No breakpoints set.")
            return
        
        # Parse breakpoint
        if ':' in arg:
            # File:line format
            file_line = arg.split(':', 1)
            filename = file_line[0]
            try:
                line_num = int(file_line[1])
                # Find PC for this line
                pc_found = False
                for pc, (_, src_line) in self.source_map.items():
                    if src_line == line_num:
                        self.breakpoints.add(pc)
                        print(f"Breakpoint set at {filename}:{line_num} (PC {pc})")
                        pc_found = True
                        break
                
                if not pc_found:
                    print(f"No PC found for {filename}:{line_num}")
            except ValueError:
                print("Invalid line number")
        else:
            # PC format
            try:
                pc = int(arg, 0)  # Support hex with 0x prefix
                self.breakpoints.add(pc)
                print(f"Breakpoint set at PC {pc}")
            except ValueError:
                print("Invalid PC value")
    
    def do_clear(self, arg):
        """Clear breakpoint. Usage: clear <pc>"""
        if not arg:
            print("Usage: clear <pc>")
            return
        
        try:
            pc = int(arg, 0)
            if pc in self.breakpoints:
                self.breakpoints.remove(pc)
                print(f"Breakpoint cleared at PC {pc}")
            else:
                print(f"No breakpoint at PC {pc}")
        except ValueError:
            print("Invalid PC value")
    
    def do_list(self, arg):
        """List source code around current position. Alias: l"""
        if not self.current_trace or not self.source_lines:
            print("No source available.")
            return
        
        step = self.current_trace.steps[self.current_step]
        source_info = self.source_map.get(step.pc)
        
        if source_info:
            _, line_num = source_info
            # Show 5 lines before and after
            start = max(0, line_num - 5)
            end = min(len(self.source_lines), line_num + 5)
            
            for i in range(start, end):
                marker = "=>" if i + 1 == line_num else "  "
                print(f"{marker} {i+1:4d}: {self.source_lines[i].rstrip()}")
        else:
            print(f"No source mapping for PC {step.pc}")
    
    def do_l(self, arg):
        """Alias for list"""
        self.do_list(arg)
    
    def do_print(self, arg):
        """Print value from stack/memory/storage. Usage: print stack[0], print storage[0x0]"""
        if not self.current_trace:
            print("No transaction loaded.")
            return
        
        step = self.current_trace.steps[self.current_step]
        
        if not arg:
            print("Usage: print <expression>")
            print("Examples: print stack[0], print storage[0x0], print memory[0x40:0x60]")
            return
        
        try:
            if arg.startswith("stack[") and arg.endswith("]"):
                index = int(arg[6:-1])
                if 0 <= index < len(step.stack):
                    value = step.stack[index]
                    print(f"stack[{index}] = {value}")
                    # Try to interpret the value
                    if value.startswith("0x"):
                        int_val = int(value, 16)
                        if int_val < 10**9:
                            print(f"  = {int_val} (decimal)")
                else:
                    print(f"Stack index {index} out of range (stack size: {len(step.stack)})")
            
            elif arg.startswith("storage[") and arg.endswith("]"):
                key = arg[8:-1]
                if key.startswith("0x"):
                    key = key[2:]
                if step.storage and key in step.storage:
                    value = step.storage[key]
                    print(f"storage[0x{key}] = 0x{value}")
                else:
                    print(f"storage[0x{key}] = 0x0 (not set)")
            
            elif "memory[" in arg:
                # Parse memory range
                import re
                match = re.match(r'memory\[(0x[0-9a-fA-F]+):(0x[0-9a-fA-F]+)\]', arg)
                if match:
                    start = int(match.group(1), 16)
                    end = int(match.group(2), 16)
                    if step.memory:
                        mem_hex = step.memory[start*2:end*2]
                        print(f"memory[{match.group(1)}:{match.group(2)}] = 0x{mem_hex}")
                else:
                    print("Invalid memory range format. Use: memory[0x40:0x60]")
            
            else:
                print(f"Unknown expression: {arg}")
                
        except Exception as e:
            print(f"Error evaluating expression: {e}")
    
    def do_p(self, arg):
        """Alias for print"""
        self.do_print(arg)
    
    def do_info(self, arg):
        """Show information. Usage: info [registers|stack|memory|storage|gas]"""
        if not self.current_trace:
            print("No transaction loaded.")
            return
        
        step = self.current_trace.steps[self.current_step]
        
        if not arg or arg == "registers":
            print(f"PC: {step.pc}")
            print(f"Operation: {step.op}")
            print(f"Gas: {step.gas} (cost: {step.gas_cost})")
            print(f"Depth: {step.depth}")
        
        if not arg or arg == "stack":
            print(f"\nStack ({len(step.stack)} items):")
            for i, val in enumerate(step.stack[:10]):
                print(f"  [{i}] {val}")
            if len(step.stack) > 10:
                print(f"  ... {len(step.stack) - 10} more items")
        
        if arg == "memory" and step.memory:
            print("\nMemory (first 256 bytes):")
            for i in range(0, min(512, len(step.memory)), 64):
                mem_line = step.memory[i:i+64]
                print(f"  0x{i//2:04x}: {mem_line}")
        
        if arg == "storage" and step.storage:
            print("\nStorage (non-zero values):")
            for key, val in sorted(step.storage.items())[:10]:
                print(f"  [0x{key}] = 0x{val}")
            if len(step.storage) > 10:
                print(f"  ... {len(step.storage) - 10} more entries")
        
        if arg == "gas":
            print(f"\nGas used: {self.current_trace.gas_used}")
            print(f"Current gas: {step.gas}")
            print(f"Last operation cost: {step.gas_cost}")
    
    def do_disasm(self, arg):
        """Disassemble around current PC"""
        if not self.current_trace:
            print("No transaction loaded.")
            return
        
        # This would show disassembly with source mapping
        step = self.current_trace.steps[self.current_step]
        print(f"PC {step.pc}: {step.op}")
        
        # Show next few instructions if available
        for i in range(1, min(5, len(self.current_trace.steps) - self.current_step)):
            next_step = self.current_trace.steps[self.current_step + i]
            print(f"PC {next_step.pc}: {next_step.op}")
    
    def do_where(self, arg):
        """Show current position in call stack. Aliases: backtrace, bt"""
        if not self.function_trace:
            print("No function trace available.")
            return
        
        print(f"\n{bold('Call Stack:')}")
        print(dim("-" * 50))
        
        # Find active call stack based on current step
        active_calls = []
        for func in self.function_trace:
            if func.entry_step <= self.current_step <= (func.exit_step or len(self.current_trace.steps)):
                active_calls.append(func)
        
        # Display call stack
        for i, func in enumerate(active_calls):
            marker = "=>" if func == self.current_function else "  "
            indent = "  " * func.depth
            
            # Format function info
            func_info = f"{func.name}"
            if func.call_type:
                func_info += f" {dim(f'[{func.call_type}]')}"
            
            # Format location
            location = ""
            if func.source_line:
                if self.tracer.ethdebug_info:
                    location = f" at {info(f'line {func.source_line}')}"
                else:
                    location = f" at {info(f'line {func.source_line}')}"
            
            print(f"{marker} {indent}#{i} {cyan(func_info)}{location}")
            
            # Show parameters for current function
            if func == self.current_function and func.args:
                for param_name, param_value in func.args:
                    print(f"     {indent}{info(param_name)}: {cyan(str(param_value))}")
        
        print(dim("-" * 50))
    
    def do_backtrace(self, arg):
        """Alias for where"""
        self.do_where(arg)
    
    def do_bt(self, arg):
        """Alias for where"""
        self.do_where(arg)
    
    def do_watch(self, arg):
        """Add watch expression. Usage: watch <expression>"""
        if not arg:
            # List watches
            if self.watch_expressions:
                print("Watch expressions:")
                for i, expr in enumerate(self.watch_expressions):
                    print(f"  {i}: {expr}")
            else:
                print("No watch expressions.")
            return
        
        self.watch_expressions.append(arg)
        print(f"Watch expression added: {arg}")
    
    def do_exit(self, arg):
        """Exit the debugger"""
        print("Goodbye!")
        return True
    
    def do_mode(self, arg):
        """Switch display mode. Usage: mode [source|asm]"""
        if not arg:
            print(f"Current mode: {info(self.display_mode)}")
            return
        
        if arg.lower() in ['source', 'src']:
            self.display_mode = 'source'
            print(f"Switched to {success('source')} mode")
        elif arg.lower() in ['asm', 'assembly']:
            self.display_mode = 'asm'
            print(f"Switched to {success('assembly')} mode")
        else:
            print(f"Invalid mode. Use 'source' or 'asm'")
        
        # Redisplay current state in new mode
        if self.current_trace:
            self._show_current_state()
    
    def do_quit(self, arg):
        """Alias for exit"""
        return self.do_exit(arg)
    
    def do_EOF(self, arg):
        """Handle Ctrl-D"""
        print()
        return self.do_exit(arg)
    
    def _get_source_line_for_step(self, step_index: int) -> Optional[int]:
        """Get source line number for a given step."""
        if step_index >= len(self.current_trace.steps):
            return None
            
        step = self.current_trace.steps[step_index]
        
        if self.tracer.ethdebug_info:
            # Use ETHDebug info
            context = self.tracer.ethdebug_parser.get_source_context(step.pc, context_lines=0)
            if context:
                return context['line']
        elif self.source_map:
            # Use basic source map
            source_info = self.source_map.get(step.pc)
            if source_info:
                return source_info[1]
        
        return None
    
    def _update_current_function(self):
        """Update current function based on current step."""
        if not self.function_trace:
            return
            
        # Find which function we're in
        for func in self.function_trace:
            if func.entry_step <= self.current_step <= (func.exit_step or len(self.current_trace.steps)):
                self.current_function = func
                break
    
    def _show_current_state(self):
        """Display current execution state (source-oriented)."""
        if not self.current_trace or self.current_step >= len(self.current_trace.steps):
            return
        
        step = self.current_trace.steps[self.current_step]
        
        # Get source information
        source_file = None
        source_line_num = None
        source_content = None
        
        if self.tracer.ethdebug_info:
            context = self.tracer.ethdebug_parser.get_source_context(step.pc, context_lines=2)
            if context:
                source_file = os.path.basename(context['file'])
                source_line_num = context['line']
                source_content = context['content']
        elif self.source_map:
            source_info = self.source_map.get(step.pc)
            if source_info and self.source_lines:
                _, source_line_num = source_info
                # Find the source file
                for file_path, lines in self.source_lines.items():
                    if 0 < source_line_num <= len(lines):
                        source_file = os.path.basename(file_path)
                        source_content = lines[source_line_num - 1].strip()
                        break
        
        # Display based on mode
        if self.display_mode == "source" and source_file:
            # Source-level display
            print(f"\n{info(f'{source_file}:{source_line_num}')}", end="")
            if self.current_function:
                print(f" in {function_name(self.current_function.name)}", end="")
            print()
            
            # Show source context
            if source_content:
                print(f"{dim('=>')} {source_line(source_content)}")
            
            # Show parameters if at function entry
            if self.current_function and self.current_step == self.current_function.entry_step:
                if self.current_function.args:
                    print(f"{dim('Parameters:')}")
                    for param_name, param_value in self.current_function.args:
                        print(f"  {info(param_name)}: {cyan(str(param_value))}")
            
            # Minimal instruction info
            print(f"{dim('[')} {dim('Step')} {highlight(f'{self.current_step}')} | "
                  f"{dim('Gas:')} {gas_value(step.gas)} | "
                  f"{dim('PC:')} {pc_value(step.pc)} | "
                  f"{opcode(step.op)} {dim(']')}")
        else:
            # Assembly-level display (fallback or when in asm mode)
            print(f"\n{dim('Step')} {highlight(f'{self.current_step}/{len(self.current_trace.steps)-1}')}")
            
            # Function context
            func_name = ""
            if self.current_function:
                func_name = f" in {function_name(self.current_function.name)}"
            
            # Format the main execution line
            pc_str = pc_value(step.pc)
            op_str = opcode(f"{step.op:<16}")
            gas_str = gas_value(step.gas)
            stack_str = self._format_stack_colored(step)
            
            print(f"PC: {pc_str} | {op_str} | Gas: {gas_str} | {stack_str}{func_name}")
            
            # Show source if available
            if source_file and source_content:
                print(f"{dim('Source:')} {info(f'{source_file}:{source_line_num}')}")
                print(f"  {dim('=>')} {source_line(source_content)}")
        
        # Watch expressions
        for expr in self.watch_expressions:
            self.do_print(expr)
    
    def _format_stack_colored(self, step) -> str:
        """Format stack with colors."""
        if not step.stack:
            return dim("[empty]")
        
        items = []
        max_items = 3
        
        for i, val in enumerate(step.stack[:max_items]):
            items.append(stack_item(i, val))
        
        if len(step.stack) > max_items:
            items.append(dim(f"... +{len(step.stack) - max_items} more"))
        
        return " ".join(items)
    
    def emptyline(self):
        """Handle empty line (don't repeat last command)"""
        pass
    
    def default(self, line):
        """Handle unknown commands."""
        print(f"{error('Unknown command:')} '{line}'")
        print(f"Type {info('help')} to see available commands.")
    
    def do_help(self, arg):
        """Show help information."""
        if arg:
            # Show help for specific command
            cmd.Cmd.do_help(self, arg)
        else:
            # Show formatted help menu
            print(f"\n{bold('Walnut EVM Debugger Commands')}")
            print(dim("=" * 60))
            
            # Execution Control
            print(f"\n{cyan('Execution Control:')}")
            print(f"  {info('run')} <tx_hash>     - Load and debug a transaction")
            print(f"  {info('next')} (n/step/s)   - Step to next source line")
            print(f"  {info('nexti')} (ni/stepi)  - Step to next instruction")  
            print(f"  {info('continue')} (c)      - Continue execution")
            
            # Breakpoints
            print(f"\n{cyan('Breakpoints:')}")
            print(f"  {info('break')} <pc>        - Set breakpoint at PC")
            print(f"  {info('break')} <file>:<ln> - Set breakpoint at source line")
            print(f"  {info('clear')} <pc>        - Clear breakpoint")
            
            # Information Display
            print(f"\n{cyan('Information Display:')}")
            print(f"  {info('list')} (l)          - Show source code")
            print(f"  {info('print')} (p) <expr>  - Print value (stack[0], storage[0x0])")
            print(f"  {info('info')} <what>       - Show info (registers/stack/memory/storage/gas)")
            print(f"  {info('where')} (bt)        - Show call stack")
            print(f"  {info('disasm')}            - Show disassembly")
            
            # Display Settings
            print(f"\n{cyan('Display Settings:')}")
            print(f"  {info('mode')} <source|asm> - Switch display mode")
            print(f"  {info('watch')} <expr>      - Add watch expression")
            
            # Other
            print(f"\n{cyan('Other Commands:')}")
            print(f"  {info('help')} [command]    - Show help")
            print(f"  {info('exit')} (quit)       - Exit debugger")
            
            print(f"\n{dim('Use')} {info('help <command>')} {dim('for detailed help on a specific command.')}")
            print(dim("=" * 60) + "\n")


def main():
    """Main entry point for the EVM REPL debugger."""
    import argparse
    
    parser = argparse.ArgumentParser(description='EVM REPL Debugger')
    parser.add_argument('--contract', '-c', help='Contract address')
    parser.add_argument('--debug', '-d', help='Debug info file (.zasm)')
    parser.add_argument('--rpc', '-r', default='http://localhost:8545', help='RPC URL')
    parser.add_argument('--tx', '-t', help='Transaction hash to debug immediately')
    
    args = parser.parse_args()
    
    # Create debugger
    debugger = EVMDebugger(
        contract_address=args.contract,
        debug_file=args.debug,
        rpc_url=args.rpc
    )
    
    # Auto-load transaction if provided
    if args.tx:
        debugger.do_run(args.tx)
    
    # Start REPL
    try:
        debugger.cmdloop()
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 0


if __name__ == '__main__':
    main()
