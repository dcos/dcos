FROM ubuntu:16.04

# Let's try to limit the number of layers to minimum:
ENV OPENRESTY_VERSION=1.9.15.1 \
    OPENRESTY_DOWNLOAD_SHASUM=491a84d70ed10b79abb9d1a7496ee57a9244350b \
    OPENRESTY_DIR=/usr/local/src/openresty \
    OPENRESTY_COMPILE_SCRIPT=/usr/local/src/build-resty.sh \
    OPENRESTY_COMPILE_OPTS="" \
    VENV_DIR=/usr/local/venv \
    AR_BIN_DIR=/usr/local/adminrouter/ \
    VEGETA_DOWNLOAD_SHA256=2f0a69d0ae6f0bf268b7f655bd37c0104d5568d5b2bc45bbb2c405266f74e33d \
    VEGETA_DOWNLOAD_URL=https://github.com/tsenart/vegeta/releases/download/v6.1.1/vegeta-v6.1.1-linux-amd64.tar.gz \
    IAM_PUBKEY_FILE_PATH=/usr/local/iam.jwt-key.pub \
    IAM_PRIVKEY_FILE_PATH=/usr/local/iam.jwt-key.priv \
    IAM_SHARED_SECRET_FILE_PATH=/usr/local/iam.jwt-key.shared-secret

# These depend on other ENV vars, so we need a separate ENV block:
ENV OPENRESTY_DOWNLOAD_URL=https://openresty.org/download/openresty-$OPENRESTY_VERSION.tar.gz \
    AUTH_ERROR_PAGE_DIR_PATH=${AR_BIN_DIR}/nginx/conf/errorpages

WORKDIR /usr/local/src/

# Some remarks when it comes to apt-get update:
# * `apt-get update` and `apt-get install` are unreliable. Because of that there
#   is some basic retrying logic
# * we put it on top of every apt-get install, because docker layer cache will
#   not re-run it when updating image with `make update-devkit` if it is a
#   separate `RUN` line. This leads to `404 Not Found errors.

#### Stuff useful while debugging docker container, not strictly needed for
#### building:
RUN set -ex \
    && bash -x -c 'for i in {1..5}; do apt-get update && break || sleep 2; done' \
    && apt-get install -y --no-install-recommends \
        apt-file \
        dnsutils \
        git \
        iproute2 \
        less \
        psmisc \
        strace \
        tcpdump \
        telnet \
        tree \
        vim

# AR related:
RUN set -ex \
    && bash -x -c 'for i in {1..5}; do apt-get update && break || sleep 2; done' \
    && apt-get install -y --no-install-recommends \
        gcc \
        gettext-base \
        libdigest-sha-perl \
        libffi-dev \
        libffi6 \
        libpcre++-dev \
        libssl-dev \
        make \
        python3 \
        python3-dev \
        python3-pip \
        python3-virtualenv \
        rsync

# Upgrading pip/setuptools and making the upgrade actually apply in the
# following filesystem layers works more reliable when using a virtualenv for
# creating the Python environment, especially on overlayfs.
# Refs:
#   https://github.com/docker/docker/issues/12327#issuecomment-188921470
#   https://github.com/docker/docker/issues/12327#issuecomment-187158265
RUN python3 -m pip install --upgrade virtualenv
RUN set -ex \
    && virtualenv --no-site-packages $VENV_DIR \
    && ${VENV_DIR}/bin/pip install --upgrade setuptools pip

ENV PATH ${VENV_DIR}/bin:$PATH

COPY ./requirements-tests.txt .
RUN pip install -r requirements-tests.txt

# Install Node & NPM
RUN curl -sL https://deb.nodesource.com/setup_6.x | bash - \
    && apt-get install -y --no-install-recommends nodejs

# Install Ngindox for API doc generation
RUN npm install -g ngindox@0.2.0

# Download Vegeta tool for benchmarking
RUN curl -fsSL "$VEGETA_DOWNLOAD_URL" -o vegeta.tar.gz \
    && echo "$VEGETA_DOWNLOAD_SHA256  vegeta.tar.gz" | sha256sum -c - \
        && tar -C /usr/local/bin -xzf vegeta.tar.gz \
        && rm vegeta.tar.gz

# Prepare Openresty. Compilation is done in Makefile itself so that
# this container can be reused during DC/OS build.
RUN set -ex \
    && curl -fsSL "$OPENRESTY_DOWNLOAD_URL" -o openresty.tar.gz \
    && echo "$OPENRESTY_DOWNLOAD_SHASUM  openresty.tar.gz" | shasum -c - \
    && mkdir -pv $OPENRESTY_DIR \
    && tar --strip-components=1 -C $OPENRESTY_DIR -xzf openresty.tar.gz \
    && rm openresty.tar.gz

COPY build-resty.sh $OPENRESTY_COMPILE_SCRIPT

# Some files that mimic DC/OS environment:
COPY iam.jwt-key.pub \
     iam.jwt-key.priv \
     iam.jwt-key.shared-secret \
        /usr/local/
COPY cluster-id /var/lib/dcos/cluster-id
COPY detect_ip_public /opt/mesosphere/bin/detect_ip_public
COPY active.buildinfo.full.json /opt/mesosphere/active.buildinfo.full.json

# The contents of adminrouter-listen* files differ from the ones that are
# shipped with DC/OS - the IP addresses Nginx binds to are limited to only
# 127.0.0.1 instead of *. The reason for it is that some endpoints also need to
# listen on TCP port 80 and this causes conflicts.
COPY adminrouter-redirect-http-https.conf \
     adminrouter-upstreams.conf \
     adminrouter-listen-master.conf \
     adminrouter-listen-agent.conf \
     adminrouter-tls.conf \
        /opt/mesosphere/etc/
COPY ca.crt /run/dcos/pki/CA/certs/ca-bundle.crt
COPY adminrouter.crt /run/dcos/pki/tls/certs/
COPY adminrouter.key /run/dcos/pki/tls/private/

# Workers run as the dcos_adminrouter group.
RUN groupadd --system dcos_adminrouter

WORKDIR $AR_BIN_DIR/nginx/conf/

CMD ["/bin/bash"]
