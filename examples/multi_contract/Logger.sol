// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Logger {
    event LogMessage(address user, string message);
    event ValueLogged(address user, uint256 value);

    function log(string calldata message) external {
        emit LogMessage(msg.sender, message);
    }

    function logValue(uint256 value) external {
        emit ValueLogged(msg.sender, value);
    }

    function logBoth(string calldata message, uint256 value) external {
        emit LogMessage(msg.sender, message);
        emit ValueLogged(msg.sender, value);
    }
}
