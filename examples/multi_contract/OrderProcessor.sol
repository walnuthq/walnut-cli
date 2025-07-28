// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ITaxCalculator {
    function calculateTax(uint256 value, string calldata orderType) external returns (uint256);
}

interface IShippingManager {
    function initiateShipping(address customer, string calldata method) external returns (uint256);
}

interface IPaymentProcessor {
    function processPayment(address from, uint256 amount) external payable;
}

interface ILogger {
    function log(string calldata message) external;
    function logValue(uint256 value) external;
    function logBoth(string calldata message, uint256 value) external;
}

contract OrderProcessor {
    address public admin;

    ITaxCalculator public taxCalculator;
    ILogger public logger;
    IShippingManager public shipping;
    IPaymentProcessor public payments;

    event OrderProcessed(address customer, uint256 value, uint256 tax, uint256 shippingCost, uint256 total);

    constructor(
        address _taxCalc,
        address _logger,
        address _shipping,
        address _payments
    ) {
        admin = msg.sender;
        taxCalculator = ITaxCalculator(_taxCalc);
        logger = ILogger(_logger);
        shipping = IShippingManager(_shipping);
        payments = IPaymentProcessor(_payments);
    }

    function processOrder(uint256 value, string calldata orderType, string calldata shippingMethod) external payable returns (uint256) {
        logger.log("Starting order processing");

        uint256 tax = taxCalculator.calculateTax(value, orderType);
        logger.logValue(tax);

        uint256 shippingCost = shipping.initiateShipping(msg.sender, shippingMethod);
        logger.logValue(shippingCost);

        uint256 total = finalizeAmount(value, tax, shippingCost);

        payments.processPayment{value: total}(msg.sender, total);
        logger.logBoth("Order complete", total);

        emit OrderProcessed(msg.sender, value, tax, shippingCost, total);

        return total;
    }

    function finalizeAmount(uint256 base, uint256 tax, uint256 shippingCost) public pure returns (uint256) {
        if (tax > base / 2) {
            return base + (tax / 2);  // discounting if tax is high
        } else {
            return base + tax;
        }
    }
}
