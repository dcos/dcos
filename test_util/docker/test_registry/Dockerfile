FROM registry:2
ADD client.key /client.key
ADD client.cert /client.cert
ENV REGISTRY_HTTP_TLS_CERTIFICATE=/client.cert
ENV REGISTRY_HTTP_TLS_KEY=/client.key
