// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./Counter.sol";

contract Controller {
    Counter public counter;

    constructor(address _counterAddress) {
        counter = Counter(_counterAddress);
    }

    function callIncrement() public {
        counter.increment(); 
    }

    function readValue() public view returns (uint256) {
        return counter.getCount(); 
    }
}