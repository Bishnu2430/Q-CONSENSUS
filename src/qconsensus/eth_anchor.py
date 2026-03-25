from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from web3 import Web3


@dataclass(frozen=True)
class EthConfig:
    rpc_url: str
    chain_id: int
    from_address: str
    private_key: str


class EthRunAnchoringClient:
    """Anchors a run commitment to an Ethereum-compatible chain.

    MVP approach: send a transaction to self with `data` containing a short payload.
    """

    def __init__(self, config: EthConfig):
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
        if not self.w3.is_connected():
            raise RuntimeError(f"Cannot connect to Ethereum RPC at {self.config.rpc_url}")

    @staticmethod
    def from_env() -> Optional["EthRunAnchoringClient"]:
        enabled = os.getenv("ETH_ANCHOR_ENABLED", "false").lower() in {"1", "true", "yes"}
        if not enabled:
            return None

        rpc_url = os.getenv("ETH_RPC_URL", "http://localhost:8545")
        chain_id = int(os.getenv("ETH_CHAIN_ID", "1337"))
        from_address = os.getenv("ETH_FROM_ADDRESS")
        private_key = os.getenv("ETH_PRIVATE_KEY")
        if not from_address or not private_key:
            raise RuntimeError("ETH_FROM_ADDRESS and ETH_PRIVATE_KEY must be set when ETH_ANCHOR_ENABLED=true")

        return EthRunAnchoringClient(
            EthConfig(rpc_url=rpc_url, chain_id=chain_id, from_address=from_address, private_key=private_key)
        )

    def anchor_run(self, *, run_id: str, commitment: str) -> str:
        payload = f"QCONS|{run_id}|{commitment}".encode("utf-8")
        data_hex = "0x" + payload.hex()

        acct = self.w3.eth.account.from_key(self.config.private_key)
        if acct.address.lower() != self.config.from_address.lower():
            raise RuntimeError("ETH_FROM_ADDRESS does not match ETH_PRIVATE_KEY")

        nonce = self.w3.eth.get_transaction_count(acct.address)
        tx = {
            "to": acct.address,
            "value": 0,
            "data": data_hex,
            "nonce": nonce,
            "chainId": self.config.chain_id,
            "gas": 120000,
            "maxFeePerGas": self.w3.to_wei(2, "gwei"),
            "maxPriorityFeePerGas": self.w3.to_wei(1, "gwei"),
        }

        signed = self.w3.eth.account.sign_transaction(tx, private_key=self.config.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()
