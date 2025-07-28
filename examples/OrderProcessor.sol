// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ITaxCalculator {
    function calculateTax(uint256 value, string calldata orderType) external returns (uint256);
}

contract OrderProcessor {
    address public admin;
    ITaxCalculator public taxCalculator;

    event OrderProcessed(address customer, uint256 value, uint256 tax, uint256 total);

    constructor(address _taxCalculator) {
        admin = msg.sender;
        taxCalculator = ITaxCalculator(_taxCalculator);
    }

    function processOrder(uint256 orderValue, string calldata orderType) external returns (uint256) {
        require(orderValue >= 100, "Minimum order value not met");

        uint256 tax = taxCalculator.calculateTax(orderValue, orderType);

        uint256 totalCost = _finalizeAmount(orderValue, tax);

        emit OrderProcessed(msg.sender, orderValue, tax, totalCost);

        return totalCost;
    }

    function _finalizeAmount(uint256 base, uint256 tax) internal pure returns (uint256) {
        if (tax > base / 2) {
            return base + (tax / 2);  // discounting if tax is high
        } else {
            return base + tax;
        }
    }
}
