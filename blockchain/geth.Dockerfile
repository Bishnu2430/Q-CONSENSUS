# Geth clique blockchain initialization and management

FROM ethereum/client-go:latest

ENV GETH_HOME="/data"

# Create data directory and genesis config
RUN mkdir -p ${GETH_HOME}/keystore ${GETH_HOME}/geth

# Copy genesis and init script
COPY genesis.json ${GETH_HOME}/
COPY init-geth.sh /usr/local/bin/

RUN chmod +x /usr/local/bin/init-geth.sh

EXPOSE 8545 8546 30303

ENTRYPOINT ["sh", "-c"]
CMD ["geth init ${GETH_HOME}/genesis.json --datadir=${GETH_HOME} 2>/dev/null || true; geth --datadir=${GETH_HOME} --http --http.addr=0.0.0.0 --http.port=8545 --http.api=eth,net,web3,personal --allow-insecure-unlock --unlock=0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266 --password=/dev/null"]
