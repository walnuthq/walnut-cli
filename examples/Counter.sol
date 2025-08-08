// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Counter {
    uint256 public count;

    function increment(uint256 value) public {
        count += value;
    }

    function getCount() public view returns (uint256) {
        return count;
    }
}