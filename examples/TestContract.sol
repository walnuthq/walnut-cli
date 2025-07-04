// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title TestContract
 * @dev Simple contract for demonstrating EVM debugging
 */
contract TestContract {
    uint256 public counter;
    mapping(address => uint256) public balances;
    
    event CounterIncremented(uint256 newValue);
    event BalanceUpdated(address indexed user, uint256 newBalance);
    
    constructor() {
        counter = 0;
    }
    
    /**
     * @dev Increment the counter by a given amount
     * @param amount The amount to increment by
     */
    function increment(uint256 amount) public {
        require(amount > 0, "Amount must be positive");
        
        // This is where we might set a breakpoint
        uint256 oldValue = counter;
        counter += amount;
        
        increment2(amount);

        emit CounterIncremented(counter);
    }

    /**
     * @dev Increment the counter by a given amount
     * @param amount The amount to increment by
     */
    function increment2(uint256 amount) public {
        require(amount > 0, "Amount must be positive");
        
        // This is where we might set a breakpoint
        uint256 oldValue = counter;
        counter += amount;
        
        increment3(amount);

        emit CounterIncremented(counter);
    }


    function increment3(uint256 amount) public {
        require(amount > 0, "Amount must be positive");
        
        // This is where we might set a breakpoint
        uint256 oldValue = counter;
        counter += amount;

        emit CounterIncremented(counter);
    }

    /**
     * @dev Update balance for a user
     * @param user The user address
     * @param amount The new balance amount
     */
    function updateBalance(address user, uint256 amount) public {
        require(user != address(0), "Invalid address");
        
        // Another good breakpoint location
        uint256 oldBalance = balances[user];
        balances[user] = amount;
        
        emit BalanceUpdated(user, amount);
    }
    
    /**
     * @dev Complex calculation for testing stepping
     */
    function complexCalculation(uint256 a, uint256 b) public pure returns (uint256) {
        uint256 result = a + b;         // Line 50: Breakpoint here
        result = result * 2;            // Line 51: Step through
        result = result - 1;            // Line 52: Step through
        
        if (result > 100) {             // Line 54: Conditional breakpoint
            result = result / 2;
        }
        
        return result;
    }
    
    /**
     * @dev Test memory operations
     */
    function memoryTest() public pure returns (bytes memory) {
        bytes memory data = new bytes(64);
        
        // Fill with pattern
        for (uint i = 0; i < data.length; i++) {
            data[i] = bytes1(uint8(i));
        }
        
        return data;
    }
}
