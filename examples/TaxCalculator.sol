// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract TaxCalculator {
    event TaxComputed(address caller, uint256 orderValue, uint256 taxAmount);

    function calculateTax(uint256 value, string calldata orderType) external returns (uint256) {
        require(value > 0, "Order value must be positive");

        uint256 tax = _determineTaxRate(value, orderType);

        emit TaxComputed(msg.sender, value, tax);

        return tax;
    }

    function _determineTaxRate(uint256 value, string calldata orderType) internal pure returns (uint256) {
        bytes32 otype = keccak256(bytes(orderType));
        if (otype == keccak256("digital")) {
            return (value * 5) / 100;  // 5%
        } else if (otype == keccak256("physical")) {
            return (value * 8) / 100;  // 8%
        } else {
            return (value * 10) / 100; // default 10%
        }
    }
}
