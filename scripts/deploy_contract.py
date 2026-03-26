from solcx import compile_source, install_solc, set_solc_version
from web3 import Web3

source = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

contract RunCommitmentAnchor {
    address public owner;

    struct CommitmentRecord {
        bytes32 commitment;
        uint256 blockNumber;
        address submitter;
    }

    mapping(bytes32 => CommitmentRecord) private commitments;

    constructor() {
        owner = msg.sender;
    }

    function commit(bytes32 run_id, bytes32 commitment) external {
        require(msg.sender == owner, "Only owner could anchor");
        commitments[run_id] = CommitmentRecord({
            commitment: commitment,
            blockNumber: block.number,
            submitter: msg.sender
        });
    }

    function getCommitment(bytes32 run_id) external view returns (bytes32, uint256, address) {
        CommitmentRecord memory rec = commitments[run_id];
        return (rec.commitment, rec.blockNumber, rec.submitter);
    }
}
"""

install_solc("0.8.17")
set_solc_version("0.8.17")
compiled = compile_source(source, output_values=["bin"])
_, contract_interface = compiled.popitem()
bytecode = contract_interface["bin"]

w3 = Web3(Web3.HTTPProvider("http://localhost:8545"))
acct = w3.eth.account.from_key("0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
nonce = w3.eth.get_transaction_count(acct.address)

tx = {
    "nonce": nonce,
    "gasPrice": w3.eth.gas_price,
    "gas": 3000000,
    "chainId": w3.eth.chain_id,
    "data": "0x" + bytecode,
}

signed = w3.eth.account.sign_transaction(tx, private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
print("STATUS", receipt.status)
print("ADDRESS", receipt.contractAddress)
print("CODE_BYTES", len(w3.eth.get_code(receipt.contractAddress)))
