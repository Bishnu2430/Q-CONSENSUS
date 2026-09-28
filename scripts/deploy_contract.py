"""Deploy the RunCommitmentAnchor contract, idempotently.

Run by the one-shot "contract" service in docker-compose.yml once the chain
is healthy. With ANCHOR_CONTRACT_ADDRESS_FILE set, it keeps the address saved
in that file while the chain still has code there; otherwise (first start, or
the chain volume was reset) it deploys a new contract and saves its address
for the orchestrator to read.

Prints ANCHOR_CONTRACT_ADDRESS=<address> and CONTRACT_STATUS=existing|deployed,
or CONTRACT_STATUS=disabled when CONTRACT_ANCHOR_ENABLED is false.
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional

from web3 import Web3

SOURCE = """
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

# Well-known signer of the local dev chain (blockchain/genesis.json).
DEV_CHAIN_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def connect(rpc_url: str, timeout_seconds: float = 60) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    deadline = time.monotonic() + timeout_seconds
    while not w3.is_connected():
        if time.monotonic() > deadline:
            raise RuntimeError(f"Cannot connect to Ethereum RPC at {rpc_url}")
        time.sleep(2)
    return w3


def saved_address(w3: Web3, path: Path) -> Optional[str]:
    """The address saved in `path`, if the chain still has contract code there."""
    try:
        address = Web3.to_checksum_address(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if len(w3.eth.get_code(address)) > 0:
        return address
    print(f"no contract code at {address} (the chain was reset); redeploying")
    return None


def save_address(path: Path, address: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(address + "\n", encoding="utf-8")
    os.replace(tmp, path)


def deploy(w3: Web3, private_key: str, solc_version: str) -> str:
    from solcx import compile_source, install_solc, set_solc_version

    install_solc(solc_version)  # no-op when already installed (the image pre-fetches it)
    set_solc_version(solc_version)
    _, contract_interface = compile_source(SOURCE, output_values=["bin"]).popitem()

    acct = w3.eth.account.from_key(private_key)
    tx = {
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gasPrice": w3.eth.gas_price,
        "gas": 3000000,
        "chainId": w3.eth.chain_id,
        "data": "0x" + contract_interface["bin"],
    }
    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction), timeout=120)
    if receipt.status != 1 or not w3.eth.get_code(receipt.contractAddress):
        raise RuntimeError(f"contract deployment failed (tx status {receipt.status})")
    return receipt.contractAddress


def main() -> int:
    if os.getenv("CONTRACT_ANCHOR_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        print("CONTRACT_STATUS=disabled")
        return 0

    w3 = connect(os.getenv("ETH_RPC_URL", "http://localhost:8545"))
    address_file = os.getenv("ANCHOR_CONTRACT_ADDRESS_FILE")
    path = Path(address_file) if address_file else None

    address = saved_address(w3, path) if path else None
    status = "existing"
    if address is None:
        private_key = os.getenv("ETH_PRIVATE_KEY") or DEV_CHAIN_PRIVATE_KEY
        address = deploy(w3, private_key, os.getenv("SOLC_VERSION", "0.8.17"))
        status = "deployed"
        if path:
            save_address(path, address)

    print(f"ANCHOR_CONTRACT_ADDRESS={address}")
    print(f"CONTRACT_STATUS={status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
