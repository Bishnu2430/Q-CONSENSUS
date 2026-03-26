# Geth clique blockchain initialization and management

FROM ethereum/client-go:v1.13.15

ENV GETH_HOME="/data"

# Create data directory and genesis config
RUN mkdir -p ${GETH_HOME}/keystore ${GETH_HOME}/geth

# Copy genesis and init script
COPY genesis.json ${GETH_HOME}/
COPY init-geth.sh /usr/local/bin/

RUN chmod +x /usr/local/bin/init-geth.sh

EXPOSE 8545 8546 30303

ENTRYPOINT ["sh", "-c"]
CMD ["mkdir -p ${GETH_HOME}; geth --datadir=${GETH_HOME} init ${GETH_HOME}/genesis.json >/dev/null 2>&1 || true; printf 'ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80\n' > /tmp/geth-key && geth account import --datadir=${GETH_HOME} --password=/dev/null /tmp/geth-key >/dev/null 2>&1 || true; rm -f /tmp/geth-key; geth --datadir=${GETH_HOME} --networkid=1337 --http --http.addr=0.0.0.0 --http.port=8545 --http.api=eth,net,web3,personal,miner,txpool --allow-insecure-unlock --unlock=0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266 --password=/dev/null --mine --miner.etherbase=0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266 --nodiscover"]
