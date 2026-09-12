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

# Invoked via "sh <script>" rather than executing it directly: this repo's
# git config has core.filemode=false (it lives on an NTFS-mounted drive),
# so the executable bit set above is never actually tracked by git -- a
# fresh clone, even on ext4, checks the script out as non-executable, and
# docker-compose.yml bind-mounts the host copy over this one at runtime,
# overriding the chmod. Running it through sh sidesteps needing the
# executable bit at all while keeping the bind mount's "edit without
# rebuilding" convenience.
ENTRYPOINT ["sh", "/usr/local/bin/init-geth.sh"]
