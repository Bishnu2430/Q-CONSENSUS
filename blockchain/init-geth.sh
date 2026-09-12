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

echo "Geth initialization complete"
