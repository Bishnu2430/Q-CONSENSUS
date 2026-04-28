"""Contract-based anchoring for Q-CONSENSUS runs.

This module handles deployment and interaction with a simple smart contract
that stores run commitments on-chain via contract storage.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from web3 import Web3
try:
    # Web3 v7+
    from web3.middleware import ExtraDataToPOAMiddleware as _poa_middleware
except Exception:  # pragma: no cover - compatibility fallback
    # Web3 v6
    from web3.middleware import geth_poa_middleware as _poa_middleware


# Minimal Solidity contract for anchoring (simplified)
ANCHOR_CONTRACT_BYTECODE = "6080604052604051610231380380610231833981016040819052610022916100f3565b60005b82518110156100e9576000838281518110610040576100406101f0565b602002602001015190503373ffffffffffffffffffffffffffffffffffffffff168173ffffffffffffffffffffffffffffffffffffffff16146100b35760405162461bcd60e51b815260206004820152601d60248201527f4f6e6c79206f776e657220636f756c6420616e636f726100000000000000604482015260640160405180910390fd5b6001600354600084815260200190815260200160002081905550806100d781610206565b915050610025565b50505061023f565b6000602082840312156101055761010561021b565b5b60006101128482850161012b565b91505092915050565b60008151905061012a81610228565b92915050565b60006020828403121561014657610146610236565b5b600061015484828501610122565b91505092915050565b600061016882610203565b9050919050565b61017981610158565b82525050565b6000819050919050565b61019281610200565b82525050565b60006080820190506101ad6000830187610170565b6101ba6020830186610189565b6101c76040830185610189565b6101d46060830184610170565b95945050505050565b600080fd5b600080fd5b600080fd5b600080fd5b600080fd5b73ffffffffffffffffffffffffffffffffffffffff81169050919050565b600061021d826101f3565b9050919050565b60008282526020820190509291505056fea26469706673582212204d7375727645717569706d656e7421000000000000000000000000000000000064736f6c63430008040033"


@dataclass(frozen=True)
class AnchorContractConfig:
    rpc_url: str
    chain_id: int
    from_address: str
    private_key: str
    contract_address: Optional[str] = None
    contract_owner: Optional[str] = None


class ContractAnchoringClient:
    """Anchors run commitments via a smart contract."""

    def __init__(self, config: AnchorContractConfig):
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
        if not self.w3.is_connected():
            raise RuntimeError(f"Cannot connect to Ethereum RPC at {self.config.rpc_url}")

        # Required for Clique/PoA chains where extraData is larger than 32 bytes.
        self.w3.middleware_onion.inject(_poa_middleware, layer=0)

        # Contract ABI for commit function
        self.contract_abi = [
            {
                "name": "commit",
                "type": "function",
                "inputs": [
                    {"name": "run_id", "type": "bytes32"},
                    {"name": "commitment", "type": "bytes32"},
                ],
                "outputs": [],
                "stateMutability": "nonpayable",
            },
            {
                "name": "getCommitment",
                "type": "function",
                "inputs": [{"name": "run_id", "type": "bytes32"}],
                "outputs": [
                    {"name": "", "type": "bytes32"},
                    {"name": "", "type": "uint256"},
                    {"name": "", "type": "address"},
                ],
                "stateMutability": "view",
            },
        ]

    @staticmethod
    def from_env() -> Optional["ContractAnchoringClient"]:
        enabled = os.getenv("CONTRACT_ANCHOR_ENABLED", "false").lower() in {"1", "true", "yes"}
        if not enabled:
            return None

        rpc_url = os.getenv("ETH_RPC_URL", "http://localhost:8545")
        chain_id = int(os.getenv("ETH_CHAIN_ID", "1337"))
        from_address = os.getenv("ETH_FROM_ADDRESS")
        private_key = os.getenv("ETH_PRIVATE_KEY")
        contract_address = os.getenv("ANCHOR_CONTRACT_ADDRESS")

        if not from_address or not private_key:
            raise RuntimeError("ETH_FROM_ADDRESS and ETH_PRIVATE_KEY must be set when CONTRACT_ANCHOR_ENABLED=true")

        return ContractAnchoringClient(
            AnchorContractConfig(
                rpc_url=rpc_url,
                chain_id=chain_id,
                from_address=from_address,
                private_key=private_key,
                contract_address=contract_address,
                contract_owner=from_address,
            )
        )

    def deploy_contract(self) -> str:
        if self.config.contract_address:
            return self.config.contract_address

        acct = self.w3.eth.account.from_key(self.config.private_key)
        nonce = self.w3.eth.get_transaction_count(acct.address)

        tx = {
            "nonce": nonce,
            "gasPrice": self.w3.eth.gas_price,
            "gas": 3000000,
            "chainId": self.config.chain_id,
            "data": ANCHOR_CONTRACT_BYTECODE,
        }

        signed = self.w3.eth.account.sign_transaction(tx, private_key=self.config.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status != 1 or not receipt.contractAddress:
            raise RuntimeError(f"Contract deployment failed, tx={tx_hash.hex()}")

        return receipt.contractAddress

    def anchor_commitment(self, *, run_id: str, commitment: str, contract_address: str) -> str:
        """Anchor a commitment to the contract."""
        run_id_bytes = Web3.keccak(text=run_id)

        raw_commitment = bytes.fromhex(commitment.lstrip("0x"))
        if len(raw_commitment) != 32:
            raise ValueError("commitment must be exactly 32 bytes (sha256 hex)")
        commitment_bytes = raw_commitment

        contract = self.w3.eth.contract(address=contract_address, abi=self.contract_abi)

        acct = self.w3.eth.account.from_key(self.config.private_key)
        nonce = self.w3.eth.get_transaction_count(acct.address)

        tx = contract.functions.commit(run_id_bytes, commitment_bytes).build_transaction(
            {
                "nonce": nonce,
                "gasPrice": self.w3.eth.gas_price,
                "gas": 100000,
                "chainId": self.config.chain_id,
            }
        )

        signed = self.w3.eth.account.sign_transaction(tx, private_key=self.config.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)

        return tx_hash.hex()

    def verify_commitment(self, *, run_id: str, contract_address: str) -> Optional[str]:
        """Verify a commitment was anchored on-chain."""
        run_id_bytes = Web3.keccak(text=run_id)
        contract = self.w3.eth.contract(address=contract_address, abi=self.contract_abi)

        try:
            result = contract.functions.getCommitment(run_id_bytes).call()
            if result[0] != b"\x00" * 32:
                return result[0].hex()
        except Exception:
            pass

        return None
