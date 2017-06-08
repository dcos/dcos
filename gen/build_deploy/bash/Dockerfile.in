FROM alpine:3.4
MAINTAINER help@dcos.io

WORKDIR /
RUN apk add --update curl ca-certificates git openssh openssl tar xz zlib && rm -rf /var/cache/apk/*
RUN curl -fLsS --retry 20 -Y 100000 -y 60 -o glibc-2.23-r3.apk https://github.com/sgerrand/alpine-pkg-glibc/releases/download/2.23-r3/glibc-2.23-r3.apk && apk --allow-untrusted add glibc-2.23-r3.apk && rm glibc-2.23-r3.apk && rm -rf /var/cache/apk/*
VOLUME ["/genconf"]

EXPOSE 9000
ENTRYPOINT ["/installer_internal_wrapper"]

# Add the mutable artifacts last to increase caching, starting with the common one
ADD {installer_bootstrap_filename} /opt/mesosphere/
COPY installer_internal_wrapper /installer_internal_wrapper
# TODO(cmaloney): Switch to copying across a whole artifacts directory
COPY {bootstrap_filename} /artifacts/bootstrap/{bootstrap_filename}
COPY {packages_dir} /artifacts/packages
COPY {bootstrap_active_filename} /artifacts/bootstrap/{bootstrap_active_filename}
COPY {bootstrap_latest_filename} /artifacts/bootstrap/{bootstrap_latest_filename}
COPY {latest_complete_filename} /artifacts/complete/{latest_complete_filename}
COPY gen_extra/ /gen_extra
