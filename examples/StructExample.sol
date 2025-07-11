// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract StructExample {
    // Basic struct representing a person
    struct Person {
        string name;
        uint256 age;
    }

    // Nested struct: a company that has a founder (which is a Person)
    struct Company {
        string companyName;
        Person founder;
    }

    // Events to log the received data
    event PersonReceived(string name, uint256 age);
    event CompanyReceived(string companyName, string founderName, uint256 founderAge);

    // Function that takes a basic struct as input
    function submitPerson(Person calldata person) external {
        emit PersonReceived(person.name, person.age);
    }

    // Function that takes a nested struct as input
    function submitCompany(Company calldata company) external {
        emit CompanyReceived(
            company.companyName,
            company.founder.name,
            company.founder.age
        );
    }
}
