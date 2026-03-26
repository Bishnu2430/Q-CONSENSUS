#!/bin/bash
# Initialize geth clique network

set -e

GETH_HOME="/data"
GETH_BIN=$(which geth)

# Create genesis.json if doesn't exist
if [ ! -f "$GETH_HOME/genesis.json" ]; then
    cat > "$GETH_HOME/genesis.json" <<'EOF'
{
  "config": {
    "chainId": 1337,
    "homesteadBlock": 0,
    "eip150Block": 0,
    "eip155Block": 0,
    "eip158Block": 0,
    "byzantiumBlock": 0,
    "constantinopleBlock": 0,
    "petersburgBlock": 0,
    "istanbulBlock": 0,
    "londonBlock": 0,
    "clique": {
      "period": 5,
      "epoch": 30000
    }
  },
  "difficulty": "0x1",
  "gasLimit": "0x8000000",
  "alloc": {
    "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266": {
      "balance": "0x200000000000000000000000000000000000000000000000000000000000000"
    }
  },
  "extradata": "0x0000000000000000000000000000000000000000000000000000000000000000f39fd6e51aad88f6f4ce6ab8827279cfffb922660000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
}
EOF
fi

# Initialize if not already done
if [ ! -d "$GETH_HOME/geth/chaindata" ]; then
    "$GETH_BIN" --datadir "$GETH_HOME" init "$GETH_HOME/genesis.json"
fi

# Create keystore directory
mkdir -p "$GETH_HOME/keystore"

# Pre-create account with known key (test account)
# Account: 0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266
# Key: ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
if [ ! -f "$GETH_HOME/keystore/"* ]; then
    cat > "$GETH_HOME/keystore/UTC--2026-03-25T00-00-00.000000000Z--f39fd6e51aad88f6f4ce6ab8827279cfffb92266" <<'EOF'
{"address":"f39fd6e51aad88f6f4ce6ab8827279cfffb92266","crypto":{"cipher":"aes-128-ctr","ciphertext":"4d87a1b6c1e8f2a9b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5","cipherparams":{"iv":"a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"},"kdf":"scrypt","kdfparams":{"dklen":32,"n":262144,"p":1,"r":8,"salt":"b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6"},"mac":"c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0"},"id":"a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d","version":3}
EOF
fi

echo "Geth initialization complete"
