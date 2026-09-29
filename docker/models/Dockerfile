# One-shot downloader for the model files (see fetch-models.sh).
FROM alpine:3.20

RUN apk add --no-cache curl

COPY fetch-models.sh /usr/local/bin/fetch-models.sh
# Strip CRs in case the script was saved with Windows line endings; sh would
# otherwise fail on every line.
RUN sed -i 's/\r$//' /usr/local/bin/fetch-models.sh

ENTRYPOINT ["sh", "/usr/local/bin/fetch-models.sh"]
