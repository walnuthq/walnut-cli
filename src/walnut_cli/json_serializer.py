"""
JSON Serialization for Walnut CLI trace output

Provides serialization of trace data into TypeScript-compatible JSON format
for web app consumption.
"""

import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import asdict
from eth_hash.auto import keccak
from web3 import Web3
from hexbytes import HexBytes
from .transaction_tracer import TransactionTrace, FunctionCall, TraceStep
from .ethdebug_parser import ETHDebugInfo
from .multi_contract_ethdebug_parser import MultiContractETHDebugParser


class TraceSerializer:
    """Serializes trace data to JSON format compatible with web app."""
    
    def __init__(self):
        self.logs = []  # Collect logs during trace processing
        self.log_position = 0
    
    def _convert_to_serializable(self, obj: Any) -> Any:
        """Convert non-serializable objects to JSON-serializable format."""
        if isinstance(obj, HexBytes):
            return obj.hex()
        elif isinstance(obj, bytes):
            return '0x' + obj.hex()
        elif isinstance(obj, dict):
            return {k: self._convert_to_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_serializable(item) for item in obj]
        elif isinstance(obj, tuple):
            return [self._convert_to_serializable(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            # Handle custom objects by converting to dict
            return self._convert_to_serializable(obj.__dict__)
        else:
            return obj
    
    def extract_logs_from_trace(self, trace: TransactionTrace) -> List[Tuple[int, Dict[str, Any]]]:
        """Extract LOG events from the trace steps with their step indices."""
        logs = []
        log_position = 0
        
        for i, step in enumerate(trace.steps):
            if step.op in ['LOG0', 'LOG1', 'LOG2', 'LOG3', 'LOG4']:
                # LOG0, LOG1, LOG2, LOG3, LOG4
                num_topics = int(step.op[-1])
                
                # Get the data and topics from stack
                # Stack layout for LOGn: [offset, size, topic1, topic2, ..., topicN]
                # Note: Stack items are in reverse order (top of stack is index 0)
                if len(step.stack) >= 2 + num_topics:
                    # Memory offset and size are first two stack items
                    try:
                        offset = int(step.stack[0], 16) if isinstance(step.stack[0], str) else int(step.stack[0])
                        size = int(step.stack[1], 16) if isinstance(step.stack[1], str) else int(step.stack[1])
                    except:
                        offset = 0
                        size = 0
                    
                    # Extract data from memory
                    data = "0x"
                    if size > 0:
                        if step.memory:
                            try:
                                # Memory is stored as hex string
                                start = offset * 2  # Each byte is 2 hex chars
                                end = start + (size * 2)
                                # Ensure we don't go out of bounds
                                if end <= len(step.memory):
                                    memory_data = step.memory[start:end]
                                    # Ensure we only take the exact size requested
                                    if len(memory_data) > size * 2:
                                        memory_data = memory_data[:size * 2]
                                    data = "0x" + memory_data
                                else:
                                    # Use whatever memory is available up to size
                                    memory_data = step.memory[start:start + (size * 2)]
                                    data = "0x" + memory_data
                            except:
                                # If memory extraction fails, use zeros
                                data = "0x" + "00" * size
                        else:
                            # No memory available, use zeros
                            data = "0x" + "00" * size
                    
                    # Extract topics from stack
                    # Stack layout for LOGn: [offset, size, topic1, topic2, ..., topicN]
                    topics = []
                    for j in range(num_topics):
                        if len(step.stack) > 2 + j:
                            topic = step.stack[2 + j]
                            # Convert to proper hex format
                            if isinstance(topic, int):
                                # Convert integer to 32-byte hex
                                topic = '0x' + hex(topic)[2:].zfill(64)
                            elif isinstance(topic, str):
                                # Remove 0x prefix if present
                                topic = topic[2:] if topic.startswith('0x') else topic
                                # Pad to 32 bytes (64 hex chars)
                                topic = '0x' + topic.zfill(64)
                            topics.append(topic)
                    
                    # Determine the contract address for this log
                    # This is the current contract being executed
                    contract_address = trace.to_addr
                    
                    # Only add valid logs (skip if topics look invalid)
                    # A valid event signature should be 32 bytes and look like a hash
                    is_valid_log = True
                    if num_topics > 0 and topics and len(topics) > 0:
                        # For LOG1+, check if first topic looks like an event signature
                        first_topic = topics[0]
                        # Skip if it's all zeros or a very small number
                        if (first_topic.startswith('0x00000000000000000000000000000000000000000000000000000000') or
                            first_topic == '0x' + '0' * 64):
                            # This looks like a small number padded to 32 bytes, not an event signature
                            is_valid_log = False
                    
                    if is_valid_log:
                        log = {
                            "address": contract_address,
                            "topics": topics,
                            "data": data,
                            "position": log_position
                        }
                        logs.append((i, log))  # Store with step index
                        log_position += 1
        
        return logs
    
    def encode_function_input(self, call: FunctionCall, trace: TransactionTrace) -> str:
        """Encode function input data from selector and arguments."""
        if call.depth == 0 and trace.input_data:
            # For the root call, use the transaction input data
            input_data = trace.input_data
            if isinstance(input_data, bytes):
                return '0x' + input_data.hex()
            elif isinstance(input_data, HexBytes):
                return input_data.hex()
            else:
                return str(input_data)
        
        if not call.selector:
            return "0x"
        
        # For internal calls, we need to build the encoded input
        # Start with the selector
        input_data = call.selector
        
        # Encode arguments if available
        if call.args:
            # Simple encoding - in reality, we'd use proper ABI encoding
            # For now, assume uint256 parameters (32 bytes each)
            for param_name, param_value in call.args:
                if isinstance(param_value, int):
                    # Encode as 32-byte hex value
                    hex_value = hex(param_value)[2:].zfill(64)
                    input_data += hex_value
                elif isinstance(param_value, str) and param_value.startswith('0x'):
                    # Already hex, just append (removing 0x prefix)
                    input_data += param_value[2:].zfill(64)
                else:
                    # Default to zero padding
                    input_data += "0" * 64
        
        return input_data if input_data.startswith('0x') else '0x' + input_data
    
    def get_function_signature_hash(self, function_name: str, param_types: List[str]) -> str:
        """Calculate the 4-byte function signature hash."""
        # Build the function signature
        signature = f"{function_name}({','.join(param_types)})"
        
        # Calculate keccak256 hash and take first 4 bytes
        selector_bytes = keccak(signature.encode())[:4]
        return '0x' + selector_bytes.hex()
    
    def convert_function_call_to_trace_call(
        self, 
        call: FunctionCall, 
        trace: TransactionTrace,
        logs_with_steps: List[Tuple[int, Dict[str, Any]]],
        all_calls: List[FunctionCall]
    ) -> Dict[str, Any]:
        """Convert a FunctionCall to TraceCall format."""
        # Determine call type
        if call.call_type == "external":
            trace_type = "CALL"
        elif call.call_type == "internal":
            trace_type = "INTERNALCALL"
        elif call.call_type == "delegatecall":
            trace_type = "DELEGATECALL"
        elif call.call_type == "staticcall":
            trace_type = "STATICCALL"
        else:
            trace_type = "CALL"  # Default
        
        # Build input data with proper encoding
        input_data = self.encode_function_input(call, trace)
        
        # For internal functions without selectors, generate them
        if trace_type == "INTERNALCALL" and not call.selector:
            # Extract parameter types from args (simplified)
            param_types = ["uint256"] * len(call.args) if call.args else []
            call.selector = self.get_function_signature_hash(call.name, param_types)
            input_data = self.encode_function_input(call, trace)
        
        # Extract gas information
        # For the root call, get gas from first step
        if call.depth == 0 and trace.steps:
            gas = trace.steps[0].gas
        else:
            # For internal calls, try to get gas from the step where the call starts
            if call.entry_step < len(trace.steps):
                gas = trace.steps[call.entry_step].gas
            else:
                gas = None
        
        gas_used = call.gas_used if call.gas_used else None
        
        # Build the trace call object
        trace_call = {
            "type": trace_type,
            "input": input_data,
        }
        
        # Add optional fields
        if trace_type != "INTERNALCALL":
            trace_call["from"] = trace.from_addr
            trace_call["to"] = trace.to_addr
        
        if gas is not None:
            trace_call["gas"] = gas
        
        if gas_used is not None:
            trace_call["gasUsed"] = gas_used
        
        # Extract logs that belong to this call based on step range
        call_logs = []
        for step_index, log in logs_with_steps:
            # Check if this log belongs to this function call
            if (step_index >= call.entry_step and 
                (call.exit_step is None or step_index <= call.exit_step)):
                # Also check that this log doesn't belong to a child call
                belongs_to_child = False
                for other_call in all_calls:
                    if (other_call.depth == call.depth + 1 and
                        step_index >= other_call.entry_step and
                        (other_call.exit_step is None or step_index <= other_call.exit_step)):
                        belongs_to_child = True
                        break
                
                if not belongs_to_child:
                    call_logs.append(log)
        
        if call_logs:
            trace_call["logs"] = call_logs
        
        # Find child calls
        child_calls = []
        for other_call in all_calls:
            # A call is a child if:
            # 1. Its depth is exactly one more than this call's depth
            # 2. Its entry step is within this call's step range
            # 3. It's not the same call
            if (other_call != call and
                other_call.depth == call.depth + 1 and 
                call.entry_step < other_call.entry_step and
                (call.exit_step is None or other_call.entry_step <= call.exit_step)):
                # Pass the logs that belong to this time range
                child_logs = [(i, log) for i, log in logs_with_steps 
                             if other_call.entry_step <= i <= (other_call.exit_step or i)]
                child_call = self.convert_function_call_to_trace_call(
                    other_call, trace, child_logs, all_calls
                )
                child_calls.append(child_call)
        
        if child_calls:
            trace_call["calls"] = child_calls
        
        # Add output only if there's a return value
        if call.return_value:
            trace_call["output"] = str(call.return_value)
        elif trace_type != "INTERNALCALL":
            # For external calls, always include output field per Ethereum standards
            trace_call["output"] = trace.output if hasattr(trace, 'output') else "0x"
        
        return trace_call
    
    def extract_internal_function_abi(
        self, 
        function_calls: List[FunctionCall],
        tracer_instance = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Extract internal function signatures and create ABI entries for each contract."""
        abis_by_contract = {}
        internal_functions_by_contract = {}
        
        # First, get the existing ABIs from the tracer if available
        if tracer_instance and hasattr(tracer_instance, 'function_abis'):
            # Get existing external function ABIs
            for selector, abi_item in tracer_instance.function_abis.items():
                # This is an external function from the loaded ABI
                contract_addr = tracer_instance.to_addr if hasattr(tracer_instance, 'to_addr') else None
                if contract_addr:
                    if contract_addr not in abis_by_contract:
                        abis_by_contract[contract_addr] = []
                    abis_by_contract[contract_addr].append(abi_item)
        
        # Extract internal functions from the function calls
        for call in function_calls:
            if call.call_type == "internal" and call.name not in ["runtime_dispatcher", "constructor"]:
                # Determine which contract this internal function belongs to
                # For now, assume it belongs to the main contract
                contract_addr = tracer_instance.to_addr if tracer_instance and hasattr(tracer_instance, 'to_addr') else "0x0"
                
                if contract_addr not in internal_functions_by_contract:
                    internal_functions_by_contract[contract_addr] = {}
                
                # Skip if we already have this function
                if call.name in internal_functions_by_contract[contract_addr]:
                    continue
                
                # Build ABI entry for internal function
                inputs = []
                if call.args:
                    for param_name, param_value in call.args:
                        # Infer type from value (simplified)
                        param_type = "uint256"  # Default to uint256
                        if isinstance(param_value, str) and param_value.startswith('0x') and len(param_value) == 42:
                            param_type = "address"
                        
                        inputs.append({
                            "internalType": param_type,
                            "name": param_name,
                            "type": param_type
                        })
                
                internal_abi = {
                    "inputs": inputs,
                    "name": call.name,
                    "outputs": [],  # We don't have return type info yet
                    "stateMutability": "nonpayable",  # Default assumption
                    "type": "function"
                }
                
                internal_functions_by_contract[contract_addr][call.name] = internal_abi
        
        # Merge internal functions into the contract ABIs
        for contract_addr, internal_funcs in internal_functions_by_contract.items():
            if contract_addr not in abis_by_contract:
                abis_by_contract[contract_addr] = []
            # Check for duplicates before adding
            existing_names = {func.get('name') for func in abis_by_contract[contract_addr]}
            for func_name, func_abi in internal_funcs.items():
                if func_name not in existing_names:
                    abis_by_contract[contract_addr].append(func_abi)
        
        return abis_by_contract
    
    def serialize_trace(
        self,
        trace: TransactionTrace,
        function_calls: List[FunctionCall],
        ethdebug_info: Optional[ETHDebugInfo] = None,
        multi_parser: Optional[MultiContractETHDebugParser] = None,
        tracer_instance = None
    ) -> Dict[str, Any]:
        """Serialize trace data to JSON format for web app."""
        # Extract logs from trace with their step indices
        logs_with_steps = self.extract_logs_from_trace(trace)
        
        # Find the root call (entry point)
        # Look for the main external function call (depth 1, since depth 0 is the dispatcher)
        root_calls = [call for call in function_calls if call.depth == 1 and call.call_type == "external"]
        
        if not root_calls:
            # Fallback to depth 0 if no external call found
            root_calls = [call for call in function_calls if call.depth == 0]
        
        if not root_calls:
            # Create a default root call if none exists
            # Extract just the log data for the default case
            logs_only = [log for _, log in logs_with_steps]
            root_trace_call = {
                "type": "CALL",
                "from": trace.from_addr,
                "to": trace.to_addr,
                "gas": trace.steps[0].gas if trace.steps else 0,
                "gasUsed": trace.gas_used,
                "input": trace.input_data,
                "output": trace.output or "0x",
                "logs": logs_only
            }
        else:
            # Convert the root call
            root_trace_call = self.convert_function_call_to_trace_call(
                root_calls[0], trace, logs_with_steps, function_calls
            )
            # Ensure root call has proper from/to addresses
            root_trace_call["from"] = trace.from_addr
            root_trace_call["to"] = trace.to_addr
            root_trace_call["gas"] = trace.steps[0].gas if trace.steps else 0
            root_trace_call["gasUsed"] = trace.gas_used
            # Handle input data
            if isinstance(trace.input_data, (bytes, HexBytes)):
                root_trace_call["input"] = self.encode_function_input(root_calls[0], trace)
            else:
                root_trace_call["input"] = trace.input_data
            # Handle output
            if isinstance(trace.output, bytes):
                root_trace_call["output"] = '0x' + trace.output.hex()
            elif isinstance(trace.output, HexBytes):
                root_trace_call["output"] = trace.output.hex()
            else:
                root_trace_call["output"] = trace.output or "0x"
        
        # Build ABIs mapping
        abis = self.extract_internal_function_abi(function_calls, tracer_instance)
        
        # Build the response
        response = {
            "traceCall": root_trace_call,
            "abis": abis
        }
        
        # Convert any non-serializable objects
        return self._convert_to_serializable(response)