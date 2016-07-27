FROM registry:2
RUN apt-get update && \
    apt-get install -y curl && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean
ADD client.key /client.key
ADD client.cert /client.cert
ENV REGISTRY_HTTP_TLS_CERTIFICATE=/client.cert
ENV REGISTRY_HTTP_TLS_KEY=/client.key
