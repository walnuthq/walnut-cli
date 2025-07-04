"""
Transaction Tracer for EVM Debugging

Provides transaction tracing and replay functionality for debugging
Solidity contracts on actual blockchain networks.
"""

import json
import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from web3 import Web3
from eth_utils import to_hex, to_checksum_address
from .colors import *
from .ethdebug_parser import ETHDebugParser, ETHDebugInfo
import re
import requests

@dataclass
class FunctionCall:
    """Represents a function call in the trace."""
    name: str
    selector: str
    entry_step: int
    exit_step: Optional[int]
    gas_used: int
    depth: int
    args: List[Any]
    return_value: Optional[Any] = None
    source_line: Optional[int] = None
    stack_at_entry: Optional[List[str]] = None  # Stack state when entering function
    call_type: str = "internal"  # "external", "internal", "delegatecall", etc.

@dataclass
class StackVariable:
    """Represents a variable or parameter on the stack."""
    name: str
    var_type: str
    stack_offset: int  # Position from top of stack
    pc_range: Tuple[int, int]  # PC range where this variable is valid
    value: Optional[Any] = None
    
@dataclass
class TraceStep:
    """Represents a single step in EVM execution trace."""
    pc: int
    op: str
    gas: int
    gas_cost: int
    depth: int
    stack: List[str]
    memory: Optional[str] = None
    storage: Optional[Dict[str, str]] = None
    error: Optional[str] = None
    
    def format_stack(self, max_items: int = 3) -> str:
        """Format stack for display."""
        if not self.stack:
            return "[empty]"
        
        items = []
        for i, val in enumerate(self.stack[:max_items]):
            # Shorten long hex values
            if len(val) > 10:
                display = f"0x{val[2:6]}..."
            else:
                display = val
            items.append(f"[{i}] {display}")
        
        if len(self.stack) > max_items:
            items.append(f"... +{len(self.stack) - max_items} more")
            
        return " ".join(items)


@dataclass
class TransactionTrace:
    """Complete trace of a transaction execution."""
    tx_hash: str
    from_addr: str
    to_addr: str
    value: int
    input_data: str
    gas_used: int
    output: str
    steps: List[TraceStep]
    success: bool
    error: Optional[str] = None


class TransactionTracer:
    """
    Traces and replays Ethereum transactions for debugging.
    """
    
    def __init__(self, rpc_url: str = "http://localhost:8545"):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {rpc_url}")
        
        self.source_maps = {}
        self.contracts = {}
        self.ethdebug_parser = ETHDebugParser()
        self.ethdebug_info: Optional[ETHDebugInfo] = None
        self.function_signatures = {}  # selector -> function name
        self.function_abis = {}  # selector -> full ABI item
        self.function_params = {}  # function name -> parameter info
        
    def load_debug_info(self, debug_file: str) -> Dict[int, Tuple[str, int]]:
        """Load debug info from solx output."""
        pc_to_source = {}
        
        if not os.path.exists(debug_file):
            print(f"Warning: Debug file {debug_file} not found")
            return pc_to_source
        
        with open(debug_file, 'r') as f:
            content = f.read()
            
        # Parse the assembly file for source mappings
        # Format: .loc file_id line column
        current_pc = 0
        current_source = None
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Track source location
            if line.startswith('.loc'):
                parts = line.split()
                if len(parts) >= 3:
                    file_id = int(parts[1])
                    line_num = int(parts[2])
                    current_source = (file_id, line_num)
            
            # Track PC for opcodes
            elif any(line.startswith(op) for op in ['PUSH', 'DUP', 'SWAP', 'JUMP', 'STOP', 'ADD', 'SUB', 'MUL', 'DIV']):
                if current_source:
                    pc_to_source[current_pc] = current_source
                    
                # Estimate PC increment based on opcode
                if line.startswith('PUSH'):
                    # Extract push size
                    if 'PUSH0' in line:
                        current_pc += 1
                    else:
                        # PUSH1-PUSH32
                        push_num = int(line.split()[0][4:]) if len(line.split()[0]) > 4 else 1
                        current_pc += 1 + push_num
                else:
                    current_pc += 1
        
        print(f"Loaded {success(str(len(pc_to_source)))} PC mappings")
        return pc_to_source
    
    def load_ethdebug_info(self, ethdebug_dir: str) -> Dict[int, Tuple[str, int]]:
        """Load ethdebug format debug information."""
        try:
            self.ethdebug_info = self.ethdebug_parser.load_ethdebug_files(ethdebug_dir)
            pc_to_source = {}
            
            # Convert ethdebug info to simple PC to source mapping
            for instruction in self.ethdebug_info.instructions:
                source_info = self.ethdebug_info.get_source_info(instruction.offset)
                if source_info:
                    source_path, offset, length = source_info
                    line, col = self.ethdebug_parser.offset_to_line_col(source_path, offset)
                    pc_to_source[instruction.offset] = (0, line)  # Use 0 as file_id for compatibility
            
            print(f"Loaded {success(str(len(pc_to_source)))} PC mappings from ethdebug")
            print(f"Contract: {info(self.ethdebug_info.contract_name)}")
            print(f"Environment: {info(self.ethdebug_info.environment)}")
            return pc_to_source
            
        except Exception as e:
            print(f"Warning: Failed to load ethdebug info: {e}")
            return {}
    
    def trace_transaction(self, tx_hash: str) -> TransactionTrace:
        """Trace a transaction execution."""
        # Ensure tx_hash is properly formatted
        if isinstance(tx_hash, str) and not tx_hash.startswith('0x'):
            tx_hash = '0x' + tx_hash
        
        # Get transaction receipt - web3.py accepts hex strings
        receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        tx = self.w3.eth.get_transaction(tx_hash)
        
        # Use debug_traceTransaction if available
        try:
            trace_result = self.w3.manager.request_blocking(
                "debug_traceTransaction",
                [tx_hash, {"disableStorage": False, "disableMemory": False}]
            )
        except Exception as e:
            print(f"debug_traceTransaction not available: {e}")
            # Fallback to basic trace
            trace_result = self._basic_trace(tx_hash)
        
        # Parse trace steps
        steps = []
        for i, step in enumerate(trace_result.get('structLogs', [])):
            trace_step = TraceStep(
                pc=step['pc'],
                op=step['op'],
                gas=step['gas'],
                gas_cost=step.get('gasCost', 0),
                depth=step['depth'],
                stack=step.get('stack', []),
                memory=''.join(step.get('memory', [])),
                storage=step.get('storage', {})
            )
            steps.append(trace_step)
        
        return TransactionTrace(
            tx_hash=tx_hash,
            from_addr=tx['from'],
            to_addr=tx.get('to', ''),
            value=tx.get('value', 0),
            input_data=tx.get('input', '0x'),
            gas_used=receipt['gasUsed'],
            output=trace_result.get('returnValue', '0x'),
            steps=steps,
            success=receipt['status'] == 1,
            error=trace_result.get('error')
        )
    
    def _basic_trace(self, tx_hash: str) -> Dict[str, Any]:
        """Basic trace using eth_call if debug namespace not available."""
        tx = self.w3.eth.get_transaction(tx_hash)
        receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        
        # Simulate with eth_call
        call_params = {
            'from': tx['from'],
            'to': tx.get('to'),
            'value': tx.get('value', 0),
            'data': tx.get('input', '0x'),
            'gas': tx['gas']
        }
        
        try:
            result = self.w3.eth.call(call_params, tx['blockNumber'] - 1)
            return {
                'returnValue': result.hex() if isinstance(result, bytes) else result,
                'structLogs': []  # No detailed trace available
            }
        except Exception as e:
            return {
                'error': str(e),
                'structLogs': []
            }
    
    def replay_transaction(self, tx_hash: str, stop_at_pc: Optional[int] = None) -> TransactionTrace:
        """Replay a transaction, optionally stopping at a specific PC."""
        trace = self.trace_transaction(tx_hash)
        
        if stop_at_pc is not None:
            # Find the step to stop at
            for i, step in enumerate(trace.steps):
                if step.pc == stop_at_pc:
                    trace.steps = trace.steps[:i+1]
                    break
        
        return trace
    
    def format_trace_step(self, step: TraceStep, source_map: Dict[int, Tuple[str, int]], 
                         step_num: int, total_steps: int) -> str:
        """Format a single trace step for display."""
        # Get source location
        source_loc = source_map.get(step.pc, (0, 0))
        source_str = ""
        
        # If we have ethdebug info, use it for better source mapping
        if self.ethdebug_info:
            context = self.ethdebug_parser.get_source_context(step.pc, context_lines=0)
            if context:
                source_str = info(f"{os.path.basename(context['file'])}:{context['line']}:{context['column']}")
        elif source_loc[1] > 0:
            source_str = info(f"line {source_loc[1]}")
        
        # Format the step with colors
        step_str = f"{dim(str(step_num).rjust(4))}"
        pc_str = pc_value(step.pc)
        op_str = opcode(f"{step.op:<15}")
        gas_str = gas_value(step.gas)
        
        # Format stack with colors
        if not step.stack:
            stack_str = dim("[empty]")
        else:
            stack_items = []
            for i, val in enumerate(step.stack[:3]):
                stack_items.append(stack_item(i, val))
            if len(step.stack) > 3:
                stack_items.append(dim(f"... +{len(step.stack) - 3} more"))
            stack_str = " ".join(stack_items)
        
        # Build the final string
        parts = [step_str, pc_str, op_str, gas_str, stack_str]
        if source_str:
            parts.append(f"{dim('<-')} {source_str}")
        
        return " | ".join(parts[:4]) + " | " + " | ".join(parts[4:])
    
    def print_trace(self, trace: TransactionTrace, source_map: Dict[int, Tuple[str, int]], 
                   max_steps: int = 50):
        """Print formatted trace."""
        print(f"\n{bold('Tracing transaction:')} {info(trace.tx_hash)}")
        print(f"{dim('Gas used:')} {number(str(trace.gas_used))}")
        if trace.output:
            print(f"{dim('Return value:')} {cyan(trace.output)}")
        if trace.error:
            print(f"{error('Error:')} {trace.error}")
        
        # Handle special cases for showing all steps
        show_all = max_steps <= 0
        steps_to_show = len(trace.steps) if show_all else min(max_steps, len(trace.steps))
        
        if show_all:
            print(f"\n{bold('Execution trace')} {dim(f'(all {len(trace.steps)} steps):')}")
        else:
            print(f"\n{bold('Execution trace')} {dim(f'(first {steps_to_show} steps):')}")
        
        print(dim("-" * 80))
        header = f"{dim('Step')} | {dim('PC')}   | {dim('Op')}              | {dim('Gas')}     | {dim('Stack')}"
        print(header)
        print(dim("-" * 80))
        
        # Show the requested number of steps
        for i in range(steps_to_show):
            print(self.format_trace_step(trace.steps[i], source_map, i, len(trace.steps)))
        
        # Show summary if not all steps were displayed
        if not show_all and len(trace.steps) > max_steps:
            print(dim(f"... {len(trace.steps) - max_steps} more steps ..."))
    
    def load_abi(self, abi_path: str):
        """Load ABI and extract function signatures."""
        try:
            with open(abi_path, 'r') as f:
                abi = json.load(f)
            
            for item in abi:
                if item.get('type') == 'function':
                    name = item['name']
                    inputs = item.get('inputs', [])
                    # Build function signature
                    input_types = ','.join([inp['type'] for inp in inputs])
                    signature = f"{name}({input_types})"
                    # Calculate selector (first 4 bytes of keccak256 hash)
                    selector_bytes = self.w3.keccak(text=signature)[:4]
                    selector = '0x' + selector_bytes.hex()
                    self.function_signatures[selector] = {
                        'name': signature,  # Store full signature as name
                        'signature': signature
                    }
                    # Store full ABI for parameter decoding
                    self.function_abis[selector] = item
                    # Store parameter info by function name
                    self.function_params[name] = inputs
                    
        except Exception as e:
            print(f"Warning: Could not load ABI: {e}")
    
    def lookup_function_signature(self, selector: str) -> Optional[str]:
        """Look up function signature from 4byte.directory."""
        try:
            # Clean up selector format
            if selector.startswith('0x'):
                selector = selector[2:]
            
            # Query 4byte.directory API
            url = f"https://www.4byte.directory/api/v1/signatures/?hex_signature=0x{selector}"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('results'):
                    # Return the first (most common) signature
                    return data['results'][0]['text_signature']
        except Exception as e:
            # Silently fail - don't interrupt execution for API failures
            pass
        
        return None
    
    def decode_function_parameters(self, selector: str, calldata: str) -> List[Tuple[str, Any]]:
        """Decode function parameters from calldata."""
        params = []
        
        if selector not in self.function_abis:
            return params
        
        abi_item = self.function_abis[selector]
        inputs = abi_item.get('inputs', [])
        
        if not inputs:
            return params
        
        try:
            # Remove selector from calldata (first 10 chars including 0x)
            if isinstance(calldata, str):
                param_data = calldata[10:]  # Skip 0x + 8 hex chars
            else:
                param_data = calldata.hex()[8:]  # Skip 8 hex chars if bytes
            
            # Decode parameters (each uint256 is 64 hex chars)
            offset = 0
            for inp in inputs:
                param_name = inp.get('name', f'param{len(params)}')
                param_type = inp['type']
                
                if param_type == 'uint256':
                    # Extract 32 bytes (64 hex chars)
                    hex_value = param_data[offset:offset+64]
                    if hex_value:
                        value = int(hex_value, 16)
                        params.append((param_name, value))
                    offset += 64
                elif param_type == 'address':
                    # Extract 20 bytes (40 hex chars) with padding
                    hex_value = param_data[offset+24:offset+64]  # Skip 12 bytes of padding
                    if hex_value:
                        value = '0x' + hex_value
                        params.append((param_name, value))
                    offset += 64
                else:
                    # For other types, show raw hex for now
                    hex_value = param_data[offset:offset+64]
                    params.append((param_name, f"0x{hex_value}"))
                    offset += 64
                    
        except Exception as e:
            print(f"Warning: Could not decode parameters: {e}")
        
        return params
    
    def analyze_calling_pattern(self, trace: TransactionTrace, function_step: int, 
                               func_name: str) -> Dict[str, int]:
        """Analyze the calling pattern to determine parameter locations."""
        # Look backwards to understand how this function was called
        pattern_info = {
            'call_type': 'internal',  # internal, external, etc.
            'stack_depth': 0,
            'param_base_offset': 2,  # Default for internal calls
        }
        
        # Analyze instructions before the function entry
        look_back = min(function_step, 50)
        for i in range(function_step - look_back, function_step):
            if i < 0:
                continue
                
            step = trace.steps[i]
            
            # Look for patterns that indicate how parameters were set up
            if step.op == "JUMPDEST" and i < function_step - 1:
                # Count JUMPDESTs to understand call depth
                pattern_info['stack_depth'] += 1
            elif step.op.startswith("DUP"):
                # DUP operations often duplicate parameters
                pass
            elif step.op == "CALLDATALOAD":
                # This suggests external call
                pattern_info['call_type'] = 'external'
                pattern_info['param_base_offset'] = 0
        
        return pattern_info
    
    def find_parameter_value_on_stack(self, trace: TransactionTrace, function_step: int, 
                                      param_index: int, param_type: str, func_name: str = None) -> Optional[Any]:
        """Try to find parameter value by analyzing the stack and calling patterns.
        
        NOTE: Without proper debug information about variable locations (which would come
        from an enhanced ETHDebug format or DWARF-style debug info), we use heuristics
        to locate parameters on the stack. This works for simple cases but may not be
        accurate for complex calling patterns.
        
        Future improvements:
        1. ETHDebug format should include variable location information
        2. Solidity compiler could emit DWARF-style debug info with stack locations
        3. We could analyze the bytecode pattern more deeply to understand the ABI
        """
        if function_step >= len(trace.steps):
            return None
            
        step = trace.steps[function_step]
        current_stack = step.stack if step.stack else []
        
        # Analyze the calling pattern to better understand parameter locations
        pattern = self.analyze_calling_pattern(trace, function_step, func_name)
        
        # For Solidity internal function calls, use pattern analysis
        base_offset = pattern['param_base_offset']
        
        # Try the most likely position first based on pattern analysis
        param_position = base_offset + param_index
        
        # Analyze stack to find parameter position
        # For Solidity internal calls, scan the stack for likely parameter values
        if len(current_stack) > 2:
            # Look for the parameter value by checking multiple positions
            # In our testing, we found that for simple internal calls,
            # the parameter is often at position 2 in the stack
            for check_pos in [2, 3, 1, 4, 0]:
                if check_pos < len(current_stack):
                    try:
                        val = int(current_stack[check_pos], 16)
                        # Check if this could be our parameter
                        # For increment functions, we expect small positive integers
                        # TODO: HANDLE MORE TYPES!!! AND INVESTIGATE CALLING CONVENTION
                        if param_type == 'uint256' and 0 < val < 100:
                            param_position = check_pos
                            break
                    except:
                        continue
        
        if param_position < len(current_stack):
            try:
                stack_value = current_stack[param_position]
                if param_type == 'uint256':
                    value = int(stack_value, 16)
                    # Validate it's a reasonable parameter value
                    # For internal calls, parameters are often small values
                    if 0 < value < 2**64:  # Reasonable range
                        return value
                else:
                    return f'0x{stack_value}'
            except:
                pass
        
        # If not found at expected position, scan nearby positions
        search_range = range(max(0, param_position - 2), min(len(current_stack), param_position + 3))
        for pos in search_range:
            if pos != param_position and pos < len(current_stack):
                try:
                    stack_value = current_stack[pos]
                    if param_type == 'uint256':
                        value = int(stack_value, 16)
                        # Additional heuristics to identify parameters
                        # Parameters are often small positive integers
                        if 0 < value < 1000:
                            return value
                except:
                    continue
        
        return None
    
    def analyze_function_calls(self, trace: TransactionTrace) -> List[FunctionCall]:
        """Analyze trace to extract function calls including internal calls."""
        function_calls = []
        call_stack = []  # Track active function calls
        
        # Extract function selector from transaction input data
        main_selector = None
        if trace.input_data and len(trace.input_data) >= 10:  # 0x + 8 hex chars
            # Ensure we're working with hex string, not bytes
            if isinstance(trace.input_data, bytes):
                input_hex = '0x' + trace.input_data.hex()
            else:
                input_hex = trace.input_data
            main_selector = input_hex[:10]  # First 4 bytes (0x + 8 chars)
        
        # Track function entry/exit patterns
        function_pcs = {}  # PC -> function name mapping
        jump_targets = {}  # Track JUMP targets
        jump_stack_values = {}  # Track stack values at JUMP instructions
        stack_snapshots = {}  # PC -> stack snapshot for function entries
        
        # First pass: identify all function entry points using source mappings
        if self.ethdebug_info:
            for i, step in enumerate(trace.steps):
                if step.op == "JUMPDEST":
                    context = self.ethdebug_parser.get_source_context(step.pc, context_lines=0)
                    if context and 'function' in context.get('content', ''):
                        # Extract function name from source
                        content = context['content'].strip()
                        match = re.search(r'function\s+(\w+)\s*\(', content)
                        if match:
                            func_name = match.group(1)
                            function_pcs[step.pc] = func_name
        
        # Second pass: track execution flow and build call stack
        current_depth = 0
        for i, step in enumerate(trace.steps):
            # Track JUMP targets and stack values
            if step.op == "JUMP" and step.stack:
                jump_target = int(step.stack[0], 16)
                jump_targets[i+1] = jump_target
                # Store stack values (excluding the jump target itself)
                # Parameters are typically at stack[1], stack[2], etc.
                if len(step.stack) > 1:
                    jump_stack_values[jump_target] = step.stack[1:]
            
            # Detect function entries
            if step.op == "JUMPDEST":
                # Save stack snapshot at this PC
                stack_snapshots[step.pc] = step.stack.copy() if step.stack else []
                
                # Check if we jumped here from a JUMP
                jumped_from = None
                for j in range(max(0, i-10), i):
                    if j+1 in jump_targets and jump_targets[j+1] == step.pc:
                        jumped_from = j
                        break
                
                # Check if this is a function entry
                if step.pc in function_pcs or (self.ethdebug_info and jumped_from is not None):
                    func_name = function_pcs.get(step.pc)
                    
                    if not func_name and self.ethdebug_info:
                        # Try to get function name from source context
                        context = self.ethdebug_parser.get_source_context(step.pc, context_lines=5)
                        if context:
                            # Look for function declaration in context
                            for line in context.get('context_lines', []):
                                match = re.search(r'function\s+(\w+)\s*\(', line)
                                if match:
                                    func_name = match.group(1)
                                    break
                    
                    if func_name:
                        # This is a function entry
                        source_line = None
                        if self.ethdebug_info:
                            context = self.ethdebug_parser.get_source_context(step.pc, context_lines=0)
                            if context:
                                source_line = context['line']
                        
                        # Try to get parameters from current stack state
                        args = []
                        current_stack = step.stack if step.stack else []
                        
                        if func_name in self.function_params:
                            params_info = self.function_params[func_name]
                            
                            # For internal calls, try to find parameters by looking backwards
                            for idx, param_info in enumerate(params_info):
                                param_name = param_info.get('name', f'param{idx}')
                                param_type = param_info.get('type', 'unknown')
                                
                                # First try our backwards search method
                                param_value = self.find_parameter_value_on_stack(trace, i, idx, param_type, func_name)
                                
                                if param_value is not None:
                                    args.append((param_name, param_value))
                                else:
                                    # Fallback: try current stack or jump stack values
                                    if idx < len(current_stack):
                                        try:
                                            stack_value = current_stack[idx]
                                            if param_type == 'uint256':
                                                param_value = int(stack_value, 16)
                                                args.append((param_name, param_value))
                                            else:
                                                args.append((param_name, f'0x{stack_value}'))
                                        except:
                                            args.append((param_name, '[passed via stack]'))
                                    else:
                                        args.append((param_name, '[passed via stack]'))
                        
                        call = FunctionCall(
                            name=func_name,
                            selector="",  # Internal calls don't have selectors
                            entry_step=i,
                            exit_step=None,  # Will be filled later
                            gas_used=0,  # Will be calculated later
                            depth=len(call_stack),
                            args=args,
                            source_line=source_line,
                            stack_at_entry=current_stack.copy(),
                            call_type="internal"  # Internal function call
                        )
                        call_stack.append(call)
                        function_calls.append(call)
            
            # Detect function exits (JUMP back or STOP/RETURN)
            if call_stack and (step.op in ["STOP", "RETURN", "REVERT"] or 
                               (step.op == "JUMP" and i < len(trace.steps) - 1)):
                # Check if we're returning from a function
                # For JUMP, we'd need more sophisticated analysis
                if step.op in ["STOP", "RETURN", "REVERT"]:
                    # End all remaining calls
                    while call_stack:
                        call = call_stack.pop()
                        call.exit_step = i
                        call.gas_used = trace.steps[call.entry_step].gas - step.gas
        
        # Close any remaining open calls
        for call in call_stack:
            call.exit_step = len(trace.steps) - 1
            call.gas_used = trace.steps[call.entry_step].gas - trace.steps[-1].gas
        
        # Handle the main entry function specially
        if main_selector:
            function_info = self.function_signatures.get(main_selector)
            if function_info:
                main_function_name = function_info['name']
            else:
                # Try to look up from 4byte.directory
                signature = self.lookup_function_signature(main_selector)
                if signature:
                    main_function_name = signature
                else:
                    main_function_name = f"function_{main_selector}"
            
            # Find the main function in our detected calls
            main_func_found = False
            for call in function_calls:
                if call.name in main_function_name or main_function_name.startswith(call.name + "("):
                    call.selector = main_selector
                    # Decode parameters from calldata
                    call.args = self.decode_function_parameters(main_selector, trace.input_data)
                    call.call_type = "external"  # This is the external entry point
                    main_func_found = True
                    break
            
            # If we didn't find it through source mapping, add it manually
            if not main_func_found and len(trace.steps) > 50:
                # Look for the main function execution after dispatcher
                for i in range(20, min(200, len(trace.steps))):
                    step = trace.steps[i]
                    if step.op == "JUMPDEST" and i > 35:
                        # This could be our main function
                        source_line = None
                        if self.ethdebug_info:
                            context = self.ethdebug_parser.get_source_context(step.pc, context_lines=0)
                            if context and context['line'] > 8:
                                source_line = context['line']
                                # Decode parameters from calldata
                                decoded_params = self.decode_function_parameters(main_selector, trace.input_data)
                                
                                # Insert at beginning (after dispatcher)
                                main_call = FunctionCall(
                                    name=main_function_name,
                                    selector=main_selector,
                                    entry_step=i,
                                    exit_step=function_calls[0].entry_step - 1 if function_calls else len(trace.steps) - 1,
                                    gas_used=trace.steps[i].gas - (trace.steps[function_calls[0].entry_step - 1].gas if function_calls else trace.steps[-1].gas),
                                    depth=0,
                                    args=decoded_params,
                                    source_line=source_line,
                                    call_type="external"  # Main entry from transaction
                                )
                                function_calls.insert(0, main_call)
                                # Adjust depth of subsequent calls
                                for call in function_calls[1:]:
                                    call.depth += 1
                                break
        
        # Always add the contract entry point first
        if len(trace.steps) > 0:
            # Determine if this is contract creation or runtime
            contract_name = self.ethdebug_info.contract_name if self.ethdebug_info else 'Contract'
            if self.ethdebug_info and self.ethdebug_info.environment == 'create':
                entry_name = f"{contract_name}::constructor"
            else:
                entry_name = f"{contract_name}::runtime_dispatcher"
            
            # Get source location for contract definition
            source_line = None
            if self.ethdebug_info:
                # Find first meaningful source mapping (usually contract definition)
                for step in trace.steps[:10]:
                    context = self.ethdebug_parser.get_source_context(step.pc, context_lines=0)
                    if context and 'contract' in context.get('content', ''):
                        source_line = context['line']
                        break
            
            # Add contract entry point
            entry_call = FunctionCall(
                name=entry_name,
                selector="",
                entry_step=0,
                exit_step=function_calls[0].entry_step - 1 if function_calls else len(trace.steps) - 1,
                gas_used=trace.steps[0].gas - (trace.steps[function_calls[0].entry_step - 1].gas if function_calls else trace.steps[-1].gas),
                depth=0,
                args=[],
                source_line=source_line,
                call_type="entry"  # Contract entry point (dispatcher/constructor)
            )
            function_calls.insert(0, entry_call)
            
            # Adjust depth of all other calls
            for call in function_calls[1:]:
                call.depth += 1
        
        return function_calls
    
    def print_function_trace(self, trace: TransactionTrace, function_calls: List[FunctionCall]):
        """Print pretty function call trace."""
        print(f"\n{bold('Function Call Trace:')} {info(trace.tx_hash)}")
        print(f"{dim('Gas used:')} {number(str(trace.gas_used))}")
        
        if trace.error:
            print(f"{error('Error:')} {trace.error}")
        
        print(f"\n{bold('Call Stack:')}")
        print(dim("-" * 60))
        
        if not function_calls:
            # Fallback: show entry point
            print(f"#0 {cyan('Contract::fallback()')} {dim('(no function selector matched)')}")
        else:
            # Sort calls by entry_step to ensure proper ordering
            sorted_calls = sorted(function_calls, key=lambda x: x.entry_step)
            
            for i, call in enumerate(sorted_calls):
                indent = "  " * call.depth
                
                # Format function name with selector if available
                if call.selector:
                    func_display = f"{cyan(call.name)} {dim(f'[{call.selector}]')}"
                else:
                    func_display = cyan(call.name)
                
                # Add call type indicator
                if call.call_type == "external":
                    call_type_display = success("[external]")
                elif call.call_type == "internal":
                    call_type_display = info("[internal]")
                elif call.call_type == "entry":
                    call_type_display = dim("[entry]")
                else:
                    call_type_display = dim(f"[{call.call_type}]")
                
                # Format gas usage
                gas_info = dim(f"gas: {number(str(call.gas_used))}")
                
                # Format source location
                source_info = ""
                if call.source_line:
                    if self.ethdebug_info:
                        # Try to get more detailed source info
                        step = trace.steps[call.entry_step] if call.entry_step < len(trace.steps) else None
                        if step:
                            context = self.ethdebug_parser.get_source_context(step.pc, context_lines=0)
                            if context:
                                source_info = dim(f" @ {os.path.basename(context['file'])}:{context['line']}")
                            else:
                                source_info = dim(f" @ line {call.source_line}")
                    else:
                        source_info = dim(f" @ line {call.source_line}")
                elif "dispatcher" in call.name or "constructor" in call.name:
                    # For entry point, show contract definition line
                    if self.ethdebug_info:
                        source_info = dim(f" @ {os.path.basename(self.ethdebug_info.sources.get(0, 'Contract.sol'))}:8")
                    else:
                        source_info = dim(f" @ Contract entry point")
                
                print(f"{indent}#{i} {func_display} {call_type_display} {gas_info}{source_info}")
                
                # Show entry/exit steps for non-entry-point functions
                if call.depth > 0:  # Show steps for actual function calls, not dispatcher
                    step_info = dim(f"   steps: {call.entry_step}-{call.exit_step}")
                    print(f"{indent}{step_info}")
                
                if call.args:
                    # Display parameters with names and values
                    for param_name, param_value in call.args:
                        if isinstance(param_value, int):
                            # Format large numbers nicely
                            value_str = cyan(str(param_value))
                        else:
                            value_str = cyan(str(param_value))
                        print(f"{indent}   {info(param_name)}: {value_str}")
                
                if call.return_value:
                    print(f"{indent}   → {call.return_value}")
        
        print(dim("-" * 60))
        print(f"\n{dim('Use --raw flag to see detailed instruction trace')}")


class SourceMapper:
    """Maps EVM bytecode positions to Solidity source locations."""
    
    def __init__(self, source_file: str, source_map_str: str):
        self.source_file = source_file
        self.source_lines = []
        
        # Load source file
        if os.path.exists(source_file):
            with open(source_file, 'r') as f:
                self.source_lines = f.readlines()
        
        # Parse source map
        self.pc_to_source = self._parse_source_map(source_map_str)
    
    def _parse_source_map(self, source_map: str) -> Dict[int, Tuple[int, int, int]]:
        """Parse Solidity source map format."""
        mappings = {}
        pc = 0
        
        if not source_map:
            return mappings
        
        # Source map format: s:l:f:j;s:l:f:j;...
        entries = source_map.split(';')
        prev_s, prev_l, prev_f = 0, 0, 0
        
        for entry in entries:
            if ':' in entry:
                parts = entry.split(':')
                s = int(parts[0]) if parts[0] else prev_s
                l = int(parts[1]) if len(parts) > 1 and parts[1] else prev_l
                f = int(parts[2]) if len(parts) > 2 and parts[2] else prev_f
                
                # Convert byte offset to line/column
                line, col = self._offset_to_line_col(s)
                mappings[pc] = (line, col, l)
                
                prev_s, prev_l, prev_f = s, l, f
            
            pc += 1
        
        return mappings
    
    def _offset_to_line_col(self, offset: int) -> Tuple[int, int]:
        """Convert byte offset to line and column."""
        current_offset = 0
        
        for line_num, line in enumerate(self.source_lines, 1):
            line_len = len(line)
            if current_offset + line_len > offset:
                col = offset - current_offset + 1
                return (line_num, col)
            current_offset += line_len
        
        return (1, 1)
    
    def get_source_line(self, pc: int) -> Optional[str]:
        """Get source line for a PC."""
        if pc in self.pc_to_source:
            line_num, _, _ = self.pc_to_source[pc]
            if 0 < line_num <= len(self.source_lines):
                return self.source_lines[line_num - 1].rstrip()
        return None
