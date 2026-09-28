# Geth clique blockchain initialization and management

FROM ethereum/client-go:v1.13.15

ENV GETH_HOME="/data"

# Create data directory and genesis config
RUN mkdir -p ${GETH_HOME}/keystore ${GETH_HOME}/geth

# Copy genesis and init script
COPY genesis.json ${GETH_HOME}/
COPY init-geth.sh /usr/local/bin/

# Strip CRs in case the script was saved with Windows line endings; sh would
# otherwise fail on every line.
RUN sed -i 's/\r$//' /usr/local/bin/init-geth.sh

EXPOSE 8545 8546 30303

# Run through sh so the script doesn't depend on an executable bit, which
# git doesn't preserve on Windows checkouts.
ENTRYPOINT ["sh", "/usr/local/bin/init-geth.sh"]
