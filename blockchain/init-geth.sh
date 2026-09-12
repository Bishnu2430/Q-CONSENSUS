#!/bin/sh
# Initialize and run the single-node geth clique (PoA) chain used for
# anchoring. Idempotent: safe to run against an already-initialized
# datadir (e.g. the gethdata volume surviving a container restart).
#
# This is bind-mounted into the container at /usr/local/bin/init-geth.sh
# by docker-compose.yml, so editing this file takes effect on the next
# container start without rebuilding the image.
set -u

GETH_HOME="${GETH_HOME:-/data}"
DEV_ADDRESS="0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
DEV_PRIVATE_KEY="ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

mkdir -p "$GETH_HOME"

# Safe to re-run: geth init no-ops (with a warning) if the datadir already
# has a genesis block.
geth --datadir="$GETH_HOME" init "$GETH_HOME/genesis.json" >/dev/null 2>&1 || true

# Import the well-known single-signer dev key if it isn't already in the
# keystore. account import fails loudly on a duplicate key, which is
# expected and harmless on every restart after the first.
key_file="$(mktemp)"
printf '%s\n' "$DEV_PRIVATE_KEY" > "$key_file"
geth account import --datadir="$GETH_HOME" --password=/dev/null "$key_file" >/dev/null 2>&1 || true
rm -f "$key_file"

exec geth \
  --datadir="$GETH_HOME" \
  --networkid=1337 \
  --http --http.addr=0.0.0.0 --http.port=8545 \
  --http.vhosts=* --http.corsdomain=* \
  --http.api=eth,net,web3,personal,miner,txpool \
  --allow-insecure-unlock \
  --unlock="$DEV_ADDRESS" --password=/dev/null \
  --mine --miner.etherbase="$DEV_ADDRESS" \
  --nodiscover
