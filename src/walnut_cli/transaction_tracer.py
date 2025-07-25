"""
Transaction Tracer for EVM Debugging

Provides transaction tracing and replay functionality for debugging
Solidity contracts on actual blockchain networks.
"""

import json
import os
import sys
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from web3 import Web3
from eth_utils import to_hex, to_checksum_address
from .colors import *
from .ethdebug_parser import ETHDebugParser, ETHDebugInfo
from .multi_contract_ethdebug_parser import MultiContractETHDebugParser, ExecutionContext
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
    
    def __init__(self, rpc_url: str = "http://localhost:8545", quiet_mode: bool = False):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {rpc_url}")
        self.quiet_mode = quiet_mode
        
        self.source_maps = {}
        self.contracts = {}
        self.ethdebug_parser = ETHDebugParser()
        self.ethdebug_info: Optional[ETHDebugInfo] = None
        self.multi_contract_parser: Optional[MultiContractETHDebugParser] = None
        self.function_signatures = {}  # selector -> function name
        self.function_abis = {}  # selector -> full ABI item
        self.function_params = {}  # function name -> parameter info
    
    def _log(self, message: str, level: str = "info"):
        """Log a message to stderr if not in quiet mode."""
        if not self.quiet_mode:
            print(message, file=sys.stderr)
        
    def load_debug_info(self, debug_file: str) -> Dict[int, Tuple[str, int]]:
        """Load debug info from solx output."""
        pc_to_source = {}
        
        if not os.path.exists(debug_file):
            self._log(f"Warning: Debug file {debug_file} not found")
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
            
            self._log(f"Loaded {success(str(len(pc_to_source)))} PC mappings from ethdebug")
            self._log(f"Contract: {info(self.ethdebug_info.contract_name)}")
            self._log(f"Environment: {info(self.ethdebug_info.environment)}")
            return pc_to_source
            
        except Exception as e:
            self._log(f"Warning: Failed to load ethdebug info: {e}")
            return {}
    
    def get_source_context_for_step(self, step: TraceStep, address: Optional[str] = None, context_lines: int = 2) -> Optional[Dict[str, Any]]:
        """Get source context for a step, handling multi-contract scenarios."""
        if self.multi_contract_parser and address:
            # Multi-contract mode: get context from specific contract
            return self.multi_contract_parser.get_source_info_for_address(address, step.pc)
        elif self.ethdebug_parser and self.ethdebug_info:
            # Single contract mode
            return self.ethdebug_parser.get_source_context(step.pc, context_lines)
        return None
    
    def get_current_contract_address(self, trace: TransactionTrace, step_index: int) -> str:
        """Determine the current contract address at a given step."""
        # For now, use the transaction's to address
        # In future, this should track CALL/DELEGATECALL targets
        if self.multi_contract_parser:
            context = self.multi_contract_parser.get_current_context()
            if context:
                return context.address
        return trace.to_addr
    
    def detect_executing_contract(self, trace: TransactionTrace, step_index: int) -> Optional[str]:
        """Detect which contract is executing at a given step by analyzing the bytecode.
        
        This is used to handle --via-ir optimized contracts where the CALL target
        address might be encoded differently.
        """
        if not self.multi_contract_parser:
            return None
            
        # Get the current step
        if step_index >= len(trace.steps):
            return None
            
        step = trace.steps[step_index]
        
        # Try to match the PC with loaded contracts
        for addr, contract_info in self.multi_contract_parser.contracts.items():
            # Check if this PC exists in the contract's debug info
            if contract_info.ethdebug_info:
                # Try to get source info for this PC
                try:
                    source_info = contract_info.parser.get_source_context(step.pc, context_lines=0)
                    if source_info:
                        # Found a match!
                        return addr
                except:
                    continue
        
        # If no match found, return None
        return None
    
    def extract_address_from_stack(self, stack_value: str) -> str:
        """Extract and properly format an address from a stack value."""
        # Remove 0x prefix if present
        if stack_value.startswith('0x'):
            stack_value = stack_value[2:]
        
        # Stack values should be 32 bytes (64 hex chars)
        # Pad to full 32 bytes if shorter
        stack_value = stack_value.zfill(64)
        
        # Extract last 40 hex chars (20 bytes) for the address
        addr_hex = stack_value[-40:]
        try:
            return to_checksum_address('0x' + addr_hex)
        except:
            return '0x' + addr_hex
    
    def extract_address_from_memory(self, memory: str, offset: int) -> Optional[str]:
        """Extract an address from memory at the given offset.
        
        Args:
            memory: The memory as a hex string (without 0x prefix)
            offset: The byte offset in memory where the address is stored
            
        Returns:
            The extracted address or None if extraction fails
        """
        try:
            # Memory is a continuous hex string, 2 chars per byte
            # Skip to the offset (multiply by 2 for hex chars)
            start_pos = offset * 2
            
            # We need 32 bytes (64 hex chars) for a full word
            if start_pos + 64 > len(memory):
                return None
                
            # Extract 32 bytes from memory
            word = memory[start_pos:start_pos + 64]
            
            # Extract address from the word (last 20 bytes / 40 hex chars)
            addr_hex = word[-40:]
            
            # Validate it's not all zeros or obviously invalid
            if addr_hex == '0' * 40:
                return None
                
            try:
                return to_checksum_address('0x' + addr_hex)
            except:
                return '0x' + addr_hex
                
        except Exception as e:
            print(f"Warning: Failed to extract address from memory at offset {offset}: {e}")
            return None
    
    def is_likely_memory_offset(self, value: str) -> bool:
        """Check if a stack value is likely a memory offset rather than an address.
        
        Memory offsets used by --via-ir are typically small values (< 0x1000).
        """
        try:
            int_val = int(value, 16) if value.startswith('0x') else int(value, 16)
            # Memory offsets are typically small (less than 4KB)
            # Real addresses are much larger (have significant upper bytes)
            return int_val < 0x1000
        except:
            return False
    
    def format_address_display(self, address: str, short: bool = True) -> str:
        """Format an address for display, optionally with contract name."""
        if not address:
            return "<unknown>"
        
        # Try to get contract name if in multi-contract mode
        contract_name = None
        if self.multi_contract_parser:
            contract_info = self.multi_contract_parser.get_contract_at_address(address)
            if contract_info:
                contract_name = contract_info.name
        
        # Format address display
        if short and len(address) > 10:
            # Show first 6 and last 4 chars: 0x1234...5678
            addr_display = f"{address[:6]}...{address[-4:]}"
        else:
            addr_display = address
        
        # Add contract name if available
        if contract_name:
            return f"{contract_name} ({addr_display})"
        return addr_display
    
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
    
    def simulate_call_trace(self, to, from_, calldata, block, tx_index=None, value = 0):
        """Simulate a transaction execution."""

        # Prepare call object
        call_obj = {
            'to': to,
            'from': from_,
            'data': "0x" + calldata if not calldata.startswith("0x") else calldata,
            'value': hex(value) if isinstance(value, int) else value
        }
       
        # Call debug_traceCall
        try:
            trace_config = {"disableStorage": False, "disableMemory": False}
            if tx_index is not None:
                trace_config["txIndex"] = tx_index
            # Block param
            if block is None:
                block_param = 'latest'
            else:
                block_param = hex(block)

            trace_result = self.w3.manager.request_blocking(
                "debug_traceCall",
                [call_obj, block_param, trace_config]
            )
        except Exception as e:
            print(f"debug_traceCall not available: {e}")
            raise

        # Parse trace steps (reuse logic from trace_transaction)
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

        # Compose TransactionTrace (simulate, so tx_hash is None)
        return TransactionTrace(
            tx_hash=None,
            from_addr=from_,
            to_addr=to,
            value=0,
            input_data=calldata,
            gas_used=trace_result.get('gas', 0),
            output=trace_result.get('returnValue', '0x'),
            steps=steps,
            success=trace_result.get('failed', False) is False,
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
                         step_num: int, total_steps: int, trace: Optional[TransactionTrace] = None, 
                         step_index: Optional[int] = None) -> str:
        """Format a single trace step for display."""
        # Get source location
        source_loc = source_map.get(step.pc, (0, 0))
        source_str = ""
        
        # If we have ethdebug info, use it for better source mapping
        if self.ethdebug_info or self.multi_contract_parser:
            # Determine current contract address if in multi-contract mode
            address = None
            if self.multi_contract_parser and trace and step_index is not None:
                address = self.get_current_contract_address(trace, step_index)
            
            context = self.get_source_context_for_step(step, address, context_lines=0)
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
            print(self.format_trace_step(trace.steps[i], source_map, i, len(trace.steps), trace, i))
        
        # Show summary if not all steps were displayed
        if not show_all and len(trace.steps) > max_steps:
            print(dim(f"... {len(trace.steps) - max_steps} more steps ..."))
    
    def format_abi_type(self, abi_input: Dict[str, Any]) -> str:
        """Format ABI type, handling tuples correctly."""
        if abi_input['type'] == 'tuple':
            # Build tuple signature from components
            components = abi_input.get('components', [])
            component_types = [self.format_abi_type(comp) for comp in components]
            return f"({','.join(component_types)})"
        elif abi_input['type'].endswith('[]'):
            # Array type
            base_type = abi_input['type'][:-2]
            if base_type == 'tuple':
                components = abi_input.get('components', [])
                component_types = [self.format_abi_type(comp) for comp in components]
                return f"({','.join(component_types)})[]"
            return abi_input['type']
        else:
            return abi_input['type']
    
    def load_abi(self, abi_path: str):
        """Load ABI and extract function signatures."""
        try:
            with open(abi_path, 'r') as f:
                abi = json.load(f)
            
            for item in abi:
                if item.get('type') == 'function':
                    name = item['name']
                    inputs = item.get('inputs', [])
                    # Build function signature with proper tuple formatting
                    input_types = ','.join([self.format_abi_type(inp) for inp in inputs])
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
        """Decode function parameters from calldata using ABI."""
        params = []
        
        if selector not in self.function_abis:
            return params
        
        abi_item = self.function_abis[selector]
        inputs = abi_item.get('inputs', [])
        
        if not inputs:
            return params
        
        try:
            # Remove selector from calldata
            if isinstance(calldata, str):
                if calldata.startswith('0x'):
                    param_data_hex = calldata[10:]  # Skip 0x + 8 hex chars (selector)
                else:
                    param_data_hex = calldata[8:]  # Skip 8 hex chars (selector)
            else:
                param_data_hex = calldata.hex()[8:]  # Skip 8 hex chars if bytes
            
            # Convert hex string to bytes for eth_abi
            param_data_bytes = bytes.fromhex(param_data_hex)
            
            # Use eth_abi to decode parameters
            from eth_abi import decode
            
            # Build the type list for decoding
            type_list = []
            for inp in inputs:
                if inp['type'] == 'tuple':
                    # Build tuple type string
                    type_list.append(self.format_abi_type(inp))
                else:
                    type_list.append(inp['type'])
            
            # Decode all parameters at once
            if param_data_bytes:
                decoded_values = decode(type_list, param_data_bytes)
                
                # Format the decoded values nicely
                for i, (inp, value) in enumerate(zip(inputs, decoded_values)):
                    param_name = inp.get('name', f'param{i}')
                    param_type = inp['type']
                    
                    if param_type == 'tuple' and inp.get('components'):
                        # Format tuple as a nice string representation
                        formatted_value = self.format_tuple_value(value, inp['components'])
                        params.append((param_name, formatted_value))
                    elif param_type == 'address':
                        # Convert to checksum address
                        try:
                            params.append((param_name, to_checksum_address(value)))
                        except:
                            params.append((param_name, value))
                    elif param_type == 'bytes' or param_type.startswith('bytes'):
                        # Convert bytes to hex
                        if isinstance(value, bytes):
                            params.append((param_name, '0x' + value.hex()))
                        else:
                            params.append((param_name, value))
                    else:
                        params.append((param_name, value))
            
        except Exception as e:
            print(f"Warning: Could not decode parameters with eth_abi, falling back to raw decoding: {e}")
            # Fallback to simple raw decoding
            try:
                offset = 0
                for inp in inputs:
                    param_name = inp.get('name', f'param{len(params)}')
                    param_type = inp['type']
                    
                    if offset + 64 <= len(param_data_hex):
                        hex_value = param_data_hex[offset:offset+64]
                        if param_type == 'uint256':
                            value = int(hex_value, 16)
                            params.append((param_name, value))
                        elif param_type == 'address':
                            addr_hex = hex_value[24:]  # Last 20 bytes
                            params.append((param_name, '0x' + addr_hex))
                        else:
                            params.append((param_name, f"0x{hex_value}"))
                        offset += 64
                    else:
                        break
            except Exception as e2:
                print(f"Warning: Fallback decoding also failed: {e2}")
        
        return params
    
    def format_tuple_value(self, value: tuple, components: List[Dict[str, Any]]) -> str:
        """Format a tuple value into a readable string."""
        if not components:
            return str(value)
        
        parts = []
        for i, (component, val) in enumerate(zip(components, value)):
            name = component.get('name', f'field{i}')
            comp_type = component['type']
            
            if comp_type == 'string':
                parts.append(f"{name}={repr(val)}")
            elif comp_type == 'address':
                try:
                    formatted_addr = to_checksum_address(val)
                    parts.append(f"{name}={formatted_addr}")
                except:
                    parts.append(f"{name}={val}")
            elif comp_type == 'tuple' and component.get('components'):
                nested_formatted = self.format_tuple_value(val, component['components'])
                parts.append(f"{name}={nested_formatted}")
            else:
                parts.append(f"{name}={val}")
        
        return f"({', '.join(parts)})"
    
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
    
    def find_parameter_value_from_ethdebug(self, trace: TransactionTrace, 
                                          function_step: int, 
                                          param_name: str, 
                                          param_type: str) -> Optional[Any]:
        """Find parameter value using ETHDebug location information.
        
        This method uses precise variable location information from ETHDebug
        to find parameter values without relying on heuristics.
        
        Args:
            trace: The transaction trace containing execution steps
            function_step: The step index where the function is called
            param_name: The name of the parameter to find
            param_type: The Solidity type of the parameter
            
        Returns:
            The decoded parameter value, or None if not found
        """
        if not self.ethdebug_info:
            # ETHDebug not available - this is expected in many cases
            return None
            
        if function_step >= len(trace.steps):
            print(f"Warning: Function step {function_step} out of range (trace has {len(trace.steps)} steps)")
            return None
            
        step = trace.steps[function_step]
        pc = step.pc
        
        # Debug logging
        if hasattr(self, 'debug_mode') and self.debug_mode:
            print(f"[ETHDebug] Looking for parameter '{param_name}' at PC {pc}")
        
        # Get variable locations at this PC
        try:
            var_locations = self.ethdebug_info.get_variables_at_pc(pc)
            
            if hasattr(self, 'debug_mode') and self.debug_mode:
                print(f"[ETHDebug] Found {len(var_locations)} variables at PC {pc}")
                for var in var_locations:
                    print(f"[ETHDebug]   - {var.name}: {var.location_type}[{var.offset}]")
        except Exception as e:
            print(f"Error getting variable locations at PC {pc}: {e}")
            return None
        
        # Search for the parameter in variable locations
        for var_loc in var_locations:
            if var_loc.name == param_name:
                try:
                    if var_loc.location_type == "stack":
                        # Precise stack location
                        if var_loc.offset < len(step.stack):
                            value = self.decode_value(step.stack[var_loc.offset], param_type)
                            if hasattr(self, 'debug_mode') and self.debug_mode:
                                print(f"[ETHDebug] Found {param_name} on stack[{var_loc.offset}] = {value}")
                            return value
                        else:
                            print(f"Warning: Stack offset {var_loc.offset} out of range (stack size: {len(step.stack)})")
                    elif var_loc.location_type == "memory":
                        # Extract from memory
                        value = self.extract_from_memory(step.memory, var_loc.offset, param_type)
                        if value is not None and hasattr(self, 'debug_mode') and self.debug_mode:
                            print(f"[ETHDebug] Found {param_name} in memory[{var_loc.offset}] = {value}")
                        return value
                    elif var_loc.location_type == "storage":
                        # Extract from storage
                        value = self.extract_from_storage(step.storage, var_loc.offset, param_type)
                        if value is not None and hasattr(self, 'debug_mode') and self.debug_mode:
                            print(f"[ETHDebug] Found {param_name} in storage[{var_loc.offset}] = {value}")
                        return value
                    else:
                        print(f"Warning: Unknown location type '{var_loc.location_type}' for {param_name}")
                except Exception as e:
                    print(f"Error extracting {param_name} from {var_loc.location_type}: {e}")
                    continue
        
        # Parameter not found in ETHDebug data
        if hasattr(self, 'debug_mode') and self.debug_mode:
            print(f"[ETHDebug] Parameter '{param_name}' not found in ETHDebug data at PC {pc}")
        
        return None
    
    def decode_value(self, raw_value: str, param_type: str) -> Any:
        """Decode a raw hex value based on its type."""
        try:
            # Handle empty or invalid values
            if not raw_value:
                return 0 if param_type.startswith(('uint', 'int')) else '0x'
            
            # Remove 0x prefix if present
            if raw_value.startswith('0x'):
                raw_value = raw_value[2:]
            
            if param_type == 'uint256' or param_type.startswith('uint'):
                return int(raw_value, 16) if raw_value else 0
            elif param_type == 'int256' or param_type.startswith('int'):
                # Handle signed integers
                value = int(raw_value, 16)
                # Check if it's a negative number (most significant bit set)
                bits = int(param_type[3:]) if param_type.startswith('int') else 256
                if value >= 2**(bits-1):
                    value -= 2**bits
                return value
            elif param_type == 'address':
                # Ensure proper address formatting
                return to_checksum_address('0x' + raw_value[-40:])
            elif param_type == 'bool':
                return int(raw_value, 16) != 0
            elif param_type == 'bytes32' or param_type.startswith('bytes'):
                return '0x' + raw_value
            elif param_type == 'string':
                # For strings, we'd need to decode from memory
                return f"<string at 0x{raw_value}>"
            else:
                # For complex types, return hex representation
                return '0x' + raw_value
        except Exception as e:
            print(f"Warning: Failed to decode {param_type} value: {e}")
            return '0x' + raw_value
    
    def extract_from_memory(self, memory: str, offset: int, param_type: str) -> Optional[Any]:
        """Extract and decode a value from memory."""
        try:
            # Memory is a hex string, each byte is 2 hex chars
            byte_offset = offset
            
            if param_type == 'string':
                # Strings in memory: first 32 bytes = length, then data
                length_hex = memory[byte_offset*2:(byte_offset+32)*2]
                if length_hex:
                    length = int(length_hex, 16)
                    data_hex = memory[(byte_offset+32)*2:(byte_offset+32+length)*2]
                    return bytes.fromhex(data_hex).decode('utf-8', errors='replace')
            elif param_type.startswith('bytes'):
                if param_type == 'bytes' or param_type == 'bytes[]':
                    # Dynamic bytes: first 32 bytes = length, then data
                    length_hex = memory[byte_offset*2:(byte_offset+32)*2]
                    if length_hex:
                        length = int(length_hex, 16)
                        data_hex = memory[(byte_offset+32)*2:(byte_offset+32+length)*2]
                        return '0x' + data_hex
                else:
                    # Fixed-size bytes (e.g., bytes32)
                    size = int(param_type[5:]) if len(param_type) > 5 else 32
                    data_hex = memory[byte_offset*2:(byte_offset+size)*2]
                    return '0x' + data_hex
            else:
                # For other types, read 32 bytes and decode
                data_hex = memory[byte_offset*2:(byte_offset+32)*2]
                if data_hex:
                    return self.decode_value(data_hex, param_type)
        except Exception as e:
            print(f"Warning: Failed to extract from memory: {e}")
        
        return None
    
    def extract_from_storage(self, storage: Dict[str, str], slot: int, param_type: str) -> Optional[Any]:
        """Extract and decode a value from storage."""
        try:
            # Storage keys are hex strings
            slot_hex = hex(slot)
            if slot_hex in storage:
                return self.decode_value(storage[slot_hex], param_type)
            
            # Try without 0x prefix
            slot_str = str(slot)
            if slot_str in storage:
                return self.decode_value(storage[slot_str], param_type)
        except Exception as e:
            print(f"Warning: Failed to extract from storage: {e}")
        
        return None
    
    def find_parameter_value_on_stack(self, trace: TransactionTrace, function_step: int, 
                                      param_index: int, param_type: str, func_name: str = None) -> Optional[Any]:
        """Try to find parameter value by analyzing the stack.
        
        NOTE: Without proper debug information about variable locations (which would come
        from an enhanced ETHDebug format or DWARF-style debug info), we cannot reliably
        locate parameters on the stack.
        """
        # TODO: Only ETHDebug data is reliable, what can we do more?????
        return None
    
    def identify_function_boundaries_from_ethdebug(self, trace: TransactionTrace) -> Dict[int, Dict[str, Any]]:
        """Use ETHDebug scope information to identify function boundaries.
        
        Returns:
            Dict mapping PC to function info (name, start_pc, end_pc, params)
        """
        function_boundaries = {}
        
        if not self.ethdebug_info:
            return function_boundaries
        
        # Track functions we've already found to avoid duplicates
        found_functions = set()
        
        # Analyze ETHDebug instructions to find function boundaries
        for instruction in self.ethdebug_info.instructions:
            pc = instruction.offset
            
            # Check if this instruction has function scope information
            if instruction.context:
                context = self.ethdebug_parser.get_source_context(pc, context_lines=5)
                if context:
                    # Check if this line actually contains the function signature
                    current_line_content = context.get('content', '').strip()
                    
                    # Only process if the current line contains a function declaration
                    # and we haven't already found this function
                    patterns = [
                        (r'function\s+(\w+)\s*\((.*?)\)', 'function'),
                        (r'constructor\s*\((.*?)\)', 'constructor'),
                        (r'receive\s*\(\s*\)', 'receive'),
                        (r'fallback\s*\((.*?)\)', 'fallback')
                    ]
                    
                    for pattern, pattern_type in patterns:
                        match = re.search(pattern, current_line_content)
                        if match:
                            if pattern_type == 'constructor':
                                func_name = 'constructor'
                                params = match.group(1) if match.lastindex >= 1 else ''
                            elif pattern_type == 'receive':
                                func_name = 'receive'
                                params = ''
                            elif pattern_type == 'fallback':
                                func_name = 'fallback'
                                params = match.group(1) if match.lastindex >= 1 else ''
                            else:
                                func_name = match.group(1)
                                params = match.group(2) if match.lastindex >= 2 else ''
                            
                            # Skip if we've already found this function
                            if func_name in found_functions:
                                continue
                            
                            found_functions.add(func_name)
                            
                            # Parse parameters
                            param_list = []
                            if params:
                                for param in params.split(','):
                                    param = param.strip()
                                    if param:
                                        parts = param.split()
                                        if len(parts) >= 2:
                                            param_list.append({
                                                'type': parts[0],
                                                'name': parts[1] if len(parts) > 1 else f'param{len(param_list)}'
                                            })
                            
                            function_boundaries[pc] = {
                                'name': func_name,
                                'start_pc': pc,
                                'end_pc': None,  # Will be determined later
                                'params': param_list,
                                'source_line': context['line']
                            }
                            break
        
        return function_boundaries
    
    def detect_call_type(self, trace: TransactionTrace, step_index: int) -> str:
        """Detect the type of call being made at a given step.
        
        Returns:
            One of: "internal", "CALL", "DELEGATECALL", "STATICCALL", "CREATE", "CREATE2"
        """
        if step_index >= len(trace.steps):
            return "internal"
        
        step = trace.steps[step_index]
        
        # Check the current operation
        if step.op in ["CALL", "DELEGATECALL", "STATICCALL", "CREATE", "CREATE2"]:
            return step.op
        
        # Look back a few steps to see if we're in the context of an external call
        look_back = min(step_index, 10)
        for i in range(step_index - look_back, step_index):
            if i >= 0 and i < len(trace.steps):
                prev_step = trace.steps[i]
                if prev_step.op in ["CALL", "DELEGATECALL", "STATICCALL"]:
                    # We're likely in the context of an external call
                    return prev_step.op
        
        # Default to internal if no external call pattern found
        return "internal"
    
    def extract_return_value(self, trace: TransactionTrace, exit_step: int, function_name: str, selector: str = None) -> Optional[Any]:
        """Extract return value from a function exit.
        
        Args:
            trace: The transaction trace
            exit_step: The step where the function exits
            function_name: Name of the function for type lookup
            
        Returns:
            The decoded return value, or None if not found
        """
        if exit_step >= len(trace.steps):
            return None
        
        step = trace.steps[exit_step]
        
        # For RETURN opcode, the return data is specified by stack[0] (offset) and stack[1] (length)
        if step.op == "RETURN" and len(step.stack) >= 2:
            try:
                # RETURN pops offset and length from stack (in that order)
                # The exact stack layout depends on the trace format
                offset = int(step.stack[0], 16)
                length = int(step.stack[1], 16)
                
                # Check if function has return values in ABI
                abi = None
                if selector and selector in self.function_abis:
                    abi = self.function_abis[selector]
                else:
                    # Try to find by function name (backward compatibility)
                    for sel, abi_item in self.function_abis.items():
                        if abi_item.get('name') == function_name:
                            abi = abi_item
                            break
                
                if abi:
                    outputs = abi.get('outputs', [])
                    # If function has no outputs, return None (void function)
                    if not outputs:
                        return None
                
                if length > 0 and step.memory:
                    # Extract return data from memory
                    return_data = step.memory[offset*2:(offset+length)*2]
                    
                    # Try to decode based on function return type
                    if abi:
                        outputs = abi.get('outputs', [])
                        if outputs and len(outputs) == 1:
                            output_type = outputs[0].get('type', 'bytes')
                            # For fixed-size types, only take the required bytes
                            if output_type.startswith(('uint', 'int', 'address', 'bool')):
                                # These are all 32 bytes
                                return_data = return_data[:64]  # 64 hex chars = 32 bytes
                            return self.decode_value(return_data, output_type)
                    
                    # Return raw hex if we can't decode
                    return '0x' + return_data
                elif length == 0:
                    # No return data - this is a void function
                    return None
            except Exception as e:
                print(f"Warning: Failed to extract return value: {e}")
        
        # For STOP or REVERT, there's typically no return value
        return None
    
    def analyze_function_calls(self, trace: TransactionTrace) -> List[FunctionCall]:
        """Analyze trace to extract function calls including internal calls.
        """
        function_calls = []
        call_stack = []  # Track active function calls
        
        # Initialize execution context for entry contract in multi-contract mode
        if self.multi_contract_parser and trace.to_addr:
            # Push the entry contract's context onto the execution stack
            self.multi_contract_parser.push_context(trace.to_addr, "ENTRY")
        
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
        
        # Use ETHDebug to identify function boundaries if available
        ethdebug_boundaries = {}
        if self.ethdebug_info:
            ethdebug_boundaries = self.identify_function_boundaries_from_ethdebug(trace)
            # Merge ETHDebug boundaries into function_pcs
            for pc, func_info in ethdebug_boundaries.items():
                function_pcs[pc] = func_info['name']
        
        # First pass: identify all function entry points using source mappings
        if (self.ethdebug_info or self.multi_contract_parser) and not ethdebug_boundaries:
            # Fallback to the original method if ETHDebug boundaries weren't found
            for i, step in enumerate(trace.steps):
                if step.op == "JUMPDEST":
                    # Get current contract address for multi-contract mode
                    address = self.get_current_contract_address(trace, i) if self.multi_contract_parser else None
                    context = self.get_source_context_for_step(step, address, context_lines=0)
                    if context and 'function' in context.get('content', ''):
                        # Extract function name from source
                        content = context['content'].strip()
                        match = re.search(r'function\s+(\w+)\s*\(', content)
                        if match:
                            func_name = match.group(1)
                            function_pcs[step.pc] = func_name
        
        # Second pass: track execution flow and build call stack
        current_depth = 0
        external_call_depth = 0  # Track depth changes from external calls
        
        for i, step in enumerate(trace.steps):
            # Handle external calls (CALL, DELEGATECALL, STATICCALL)
            if step.op in ["CALL", "DELEGATECALL", "STATICCALL"]:
                # Extract call parameters from stack
                if len(step.stack) >= 7:  # CALL requires 7 stack items
                    gas = int(step.stack[0], 16)
                    raw_addr_value = step.stack[1]
                    value = int(step.stack[2], 16) if step.op == "CALL" else 0
                    
                    # Check if this might be a memory offset (--via-ir pattern)
                    if self.is_likely_memory_offset(raw_addr_value) and step.memory:
                        # Try to extract the actual address from memory
                        offset = int(raw_addr_value, 16)
                        actual_addr = self.extract_address_from_memory(step.memory, offset)
                        if actual_addr:
                            to_addr = actual_addr
                            print(f"Debug: Resolved address from memory offset 0x{offset:x}: {to_addr}")
                        else:
                            # For --via-ir optimized code, we might need to detect the actual
                            # target by looking at what contract executes after the CALL
                            # For now, mark it as unknown and resolve it later
                            to_addr = self.extract_address_from_stack(raw_addr_value)
                            
                            # Special handling for via-ir low addresses
                            if int(raw_addr_value, 16) < 0x1000:
                                # Look ahead to see what contract actually executes
                                if i + 1 < len(trace.steps) and trace.steps[i + 1].depth > step.depth:
                                    # External call succeeded, try to determine target from context
                                    # This will be resolved when we detect the depth increase
                                    to_addr = f"0x{int(raw_addr_value, 16):040x}"  # Placeholder
                    else:
                        # Normal address extraction
                        to_addr = self.extract_address_from_stack(raw_addr_value)
                    
                    # Push context if in multi-contract mode
                    if self.multi_contract_parser:
                        self.multi_contract_parser.push_context(to_addr, step.op)
                    
                    # Format call name with proper address display
                    addr_display = self.format_address_display(to_addr, short=True)
                    call_name = f"{step.op.lower()}_to_{addr_display}"
                    
                    # Create external call entry
                    external_call = FunctionCall(
                        name=call_name,
                        selector="",
                        entry_step=i,
                        exit_step=None,
                        gas_used=0,
                        depth=len(call_stack),
                        args=[("to", to_addr), ("value", value), ("gas", gas)],
                        source_line=None,
                        stack_at_entry=step.stack.copy() if step.stack else [],
                        call_type=step.op
                    )
                    call_stack.append(external_call)
                    function_calls.append(external_call)
                    external_call_depth += 1
            
            # Check for external call execution (depth increase)
            if i > 0 and step.depth > trace.steps[i-1].depth:
                # We've entered an external call
                # Check if the previous call had an unresolved address (via-ir pattern)
                if call_stack and call_stack[-1].call_type in ["CALL", "DELEGATECALL", "STATICCALL"]:
                    recent_call = call_stack[-1]
                    # Check if this was a via-ir optimized call with low address
                    if recent_call.args and len(recent_call.args) > 0:
                        to_param = recent_call.args[0]  # ("to", address)
                        if len(to_param) > 1 and isinstance(to_param[1], str):
                            try:
                                addr_val = int(to_param[1], 16) if to_param[1].startswith('0x') else int(to_param[1], 16)
                                if addr_val < 0x1000:  # Likely a via-ir optimization
                                    # Try to determine the actual contract from the source mapping
                                    if self.multi_contract_parser:
                                        # Check which contract's code is executing
                                        actual_addr = self.detect_executing_contract(trace, i)
                                        if actual_addr and actual_addr != to_param[1]:
                                            # Update the call with the actual address
                                            recent_call.args[0] = ("to", actual_addr)
                                            recent_call.name = f"{recent_call.call_type.lower()}_to_{self.format_address_display(actual_addr, short=True)}"
                                            # Update the context stack
                                            self.multi_contract_parser.pop_context()
                                            self.multi_contract_parser.push_context(actual_addr, recent_call.call_type)
                            except ValueError:
                                pass
            
            # Check for external call returns (depth decrease)
            if i > 0 and step.depth < trace.steps[i-1].depth:
                # External call has returned
                if call_stack and external_call_depth > 0:
                    # Pop context if in multi-contract mode
                    if self.multi_contract_parser:
                        self.multi_contract_parser.pop_context()
                    
                    # Find the most recent external call
                    for j in range(len(call_stack) - 1, -1, -1):
                        if call_stack[j].call_type in ["CALL", "DELEGATECALL", "STATICCALL"]:
                            call = call_stack.pop(j)
                            call.exit_step = i
                            call.gas_used = trace.steps[call.entry_step].gas - step.gas
                            # Check if there's a return value
                            if i < len(trace.steps) - 1 and trace.steps[i+1].stack:
                                # Return value is pushed to stack after external call
                                call.return_value = int(trace.steps[i+1].stack[0], 16) if trace.steps[i+1].stack else None
                            external_call_depth -= 1
                            break
            
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
                        # Only create a new function entry if:
                        # 1. We jumped here (not just a JUMPDEST in sequence), OR
                        # 2. This PC is explicitly marked as a function entry in function_pcs
                        # AND we're not already in a function with the same name at a nearby location
                        
                        should_create_entry = False
                        
                        # Check if this is a real function entry (either jumped to or marked in function_pcs)
                        if jumped_from is not None or step.pc in function_pcs:
                            # Check if we're already inside this function
                            already_in_function = False
                            for existing_call in call_stack:
                                if existing_call.name == func_name and existing_call.exit_step is None:
                                    # For the same function, check if we're in a loop/internal jump
                                    # by seeing if the PC is close to the existing entry
                                    if step.pc > existing_call.entry_step:
                                        # We're after the function entry, likely still in the same function
                                        already_in_function = True
                                        break
                            
                            should_create_entry = not already_in_function
                        
                        if should_create_entry:
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
                                    
                                    # First try ETHDebug if available
                                    param_value = None
                                    if self.ethdebug_info:
                                        param_value = self.find_parameter_value_from_ethdebug(trace, i, param_name, param_type)
                                    
                                    # Fallback to heuristics if ETHDebug didn't work
                                    if param_value is None:
                                        param_value = self.find_parameter_value_on_stack(trace, i, idx, param_type, func_name)
                                    
                                    if param_value is not None:
                                        args.append((param_name, param_value))
                                    else:
                                        # No reliable way to determine parameter value
                                        args.append((param_name, '<unknown>'))
                            
                            # Detect the call type using ETHDebug-enhanced method
                            call_type = self.detect_call_type(trace, i)
                            
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
                                call_type=call_type  # Use detected call type
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
                        
                        # Try to extract return value if RETURN opcode
                        if step.op == "RETURN":
                            call.return_value = self.extract_return_value(trace, i, call.name, call.selector)
        
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
            # In multi-contract mode, use the actual target contract
            if self.multi_contract_parser and trace.to_addr:
                target_contract = self.multi_contract_parser.get_contract_at_address(trace.to_addr)
                if target_contract:
                    contract_name = target_contract.name
                    is_create = target_contract.ethdebug_info.environment == 'create'
                else:
                    contract_name = 'Contract'
                    is_create = False
            else:
                contract_name = self.ethdebug_info.contract_name if self.ethdebug_info else 'Contract'
                is_create = self.ethdebug_info and self.ethdebug_info.environment == 'create'
            
            if is_create:
                entry_name = f"{contract_name}::constructor"
            else:
                entry_name = f"{contract_name}::runtime_dispatcher"
            
            # Get source location for contract definition
            source_line = None
            if self.multi_contract_parser and trace.to_addr:
                # Multi-contract mode: get source from the target contract
                contract_info = self.multi_contract_parser.get_contract_at_address(trace.to_addr)
                if contract_info:
                    for step in trace.steps[:10]:
                        context = contract_info.parser.get_source_context(step.pc, context_lines=0)
                        if context and 'contract' in context.get('content', ''):
                            source_line = context['line']
                            break
            elif self.ethdebug_info:
                # Single contract mode
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
        
        # Clean up execution context for entry contract in multi-contract mode
        if self.multi_contract_parser and trace.to_addr:
            # Pop the entry contract's context from the execution stack
            self.multi_contract_parser.pop_context()
        
        return function_calls
    
    def print_function_trace(self, trace: TransactionTrace, function_calls: List[FunctionCall]):
        """Print pretty function call trace with multi-contract support."""
        print(f"\n{bold('Function Call Trace:')} {info(trace.tx_hash)}")
        
        # Show all loaded contracts if in multi-contract mode
        if self.multi_contract_parser:
            loaded_contracts = self.multi_contract_parser.get_all_loaded_contracts()
            if loaded_contracts:
                print(f"{dim('Loaded contracts:')}")
                for addr, name in loaded_contracts:
                    addr_display = self.format_address_display(addr, short=False)
                    print(f"  {info(addr_display)}")
        else:
            if trace.to_addr:
                addr_display = self.format_address_display(trace.to_addr, short=False)
                print(f"{dim('Contract:')} {info(addr_display)}")
        
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
                
                # Add call type indicator with enhanced info for external calls
                if call.call_type in ["CALL", "DELEGATECALL", "STATICCALL"]:
                    # For external calls, show the target contract name if available
                    target_info = ""
                    if self.multi_contract_parser and call.args:
                        # Extract target address from args
                        for arg_name, arg_value in call.args:
                            if arg_name == "to":
                                target_contract = self.multi_contract_parser.get_contract_at_address(str(arg_value))
                                if target_contract:
                                    target_info = f" → {target_contract.name}"
                                break
                    call_type_display = success(f"[{call.call_type}]{target_info}")
                elif call.call_type == "external":
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
                    if self.ethdebug_info or self.multi_contract_parser:
                        # Try to get more detailed source info
                        step = trace.steps[call.entry_step] if call.entry_step < len(trace.steps) else None
                        if step:
                            # Determine contract address for multi-contract mode
                            address = None
                            if self.multi_contract_parser:
                                # For external calls, use the target address
                                if call.call_type in ["CALL", "DELEGATECALL", "STATICCALL"] and call.args:
                                    for arg_name, arg_value in call.args:
                                        if arg_name == "to":
                                            address = str(arg_value)
                                            break
                                else:
                                    address = self.get_current_contract_address(trace, call.entry_step)
                            
                            context = self.get_source_context_for_step(step, address, context_lines=0)
                            if context:
                                source_info = dim(f" @ {os.path.basename(context['file'])}:{context['line']}")
                            else:
                                source_info = dim(f" @ line {call.source_line}")
                    else:
                        source_info = dim(f" @ line {call.source_line}")
                elif "dispatcher" in call.name or "constructor" in call.name:
                    # For entry point, show contract definition line
                    if self.multi_contract_parser and trace.to_addr:
                        # Multi-contract mode: get the correct contract's source
                        contract_info = self.multi_contract_parser.get_contract_at_address(trace.to_addr)
                        if contract_info and contract_info.ethdebug_info:
                            source_file = os.path.basename(contract_info.ethdebug_info.sources.get(0, f'{contract_info.name}.sol'))
                            source_info = dim(f" @ {source_file}:{call.source_line if call.source_line else '1'}")
                        else:
                            source_info = dim(f" @ {contract_info.name}.sol:1" if contract_info else " @ Contract entry point")
                    elif self.ethdebug_info:
                        source_info = dim(f" @ {os.path.basename(self.ethdebug_info.sources.get(0, 'Contract.sol'))}:{call.source_line if call.source_line else '1'}")
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
