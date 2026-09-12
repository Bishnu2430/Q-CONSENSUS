"""Contract-based anchoring for Q-CONSENSUS runs.

This module handles deployment and interaction with a simple smart contract
that stores run commitments on-chain via contract storage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from web3 import Web3
from web3.exceptions import BadFunctionCallOutput, ContractLogicError
try:
    # Web3 v7+
    from web3.middleware import ExtraDataToPOAMiddleware as _poa_middleware
except Exception:  # pragma: no cover - compatibility fallback
    # Web3 v6
    from web3.middleware import geth_poa_middleware as _poa_middleware


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

    def has_code(self, address: str) -> bool:
        """Return True if the given address currently has deployed contract code.

        Used to detect a stale ANCHOR_CONTRACT_ADDRESS left over in .env after the
        chain's data volume was wiped/recreated but the address was never cleared.
        """
        checksum_address = Web3.to_checksum_address(address)
        code = self.w3.eth.get_code(checksum_address)
        return len(code) > 0

    def anchor_commitment(self, *, run_id: str, commitment: str, contract_address: str) -> str:
        """Anchor a commitment to the contract.

        Raises if the contract has no code at the given address, or if the
        transaction is submitted but reverts on-chain — a caller must not treat
        a returned tx hash as proof the commitment was actually stored.
        """
        run_id_bytes = Web3.keccak(text=run_id)

        raw_commitment = bytes.fromhex(commitment.lstrip("0x"))
        if len(raw_commitment) != 32:
            raise ValueError("commitment must be exactly 32 bytes (sha256 hex)")

        checksum_address = Web3.to_checksum_address(contract_address)
        if not self.has_code(checksum_address):
            raise RuntimeError(
                f"No contract deployed at {checksum_address} — redeploy via "
                "scripts/deploy_contract.py and update ANCHOR_CONTRACT_ADDRESS"
            )

        contract = self.w3.eth.contract(address=checksum_address, abi=self.contract_abi)

        acct = self.w3.eth.account.from_key(self.config.private_key)
        nonce = self.w3.eth.get_transaction_count(acct.address)

        tx = contract.functions.commit(run_id_bytes, raw_commitment).build_transaction(
            {
                "nonce": nonce,
                "gasPrice": self.w3.eth.gas_price,
                "gas": 100000,
                "chainId": self.config.chain_id,
            }
        )

        signed = self.w3.eth.account.sign_transaction(tx, private_key=self.config.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        if receipt.status != 1:
            raise RuntimeError(f"anchor commit transaction reverted, tx={tx_hash.hex()}")

        return tx_hash.hex()

    def verify_commitment(self, *, run_id: str, contract_address: str) -> Dict[str, Any]:
        """Look up a commitment on-chain.

        Returns {"commitment": <hex or None>, "error": <reason or None>}.
        `error` is only set when the lookup itself could not be completed
        (stale/invalid address, RPC failure, ABI mismatch) — a clean "not
        anchored yet" result has `error: None` and `commitment: None`, so
        callers can tell "not found" apart from "couldn't check".
        """
        try:
            checksum_address = Web3.to_checksum_address(contract_address)
        except ValueError as exc:
            return {"commitment": None, "error": f"invalid_contract_address: {exc}"}

        try:
            if not self.has_code(checksum_address):
                return {"commitment": None, "error": "no_contract_at_address"}
        except Exception as exc:  # RPC connectivity issue, etc.
            return {"commitment": None, "error": f"rpc_error_checking_code: {exc}"}

        run_id_bytes = Web3.keccak(text=run_id)
        contract = self.w3.eth.contract(address=checksum_address, abi=self.contract_abi)

        try:
            result = contract.functions.getCommitment(run_id_bytes).call()
        except ContractLogicError as exc:
            return {"commitment": None, "error": f"call_reverted: {exc}"}
        except (BadFunctionCallOutput, ValueError) as exc:
            return {"commitment": None, "error": f"abi_mismatch_or_rpc_error: {exc}"}

        if result[0] == b"\x00" * 32:
            return {"commitment": None, "error": None}

        return {"commitment": result[0].hex(), "error": None}
