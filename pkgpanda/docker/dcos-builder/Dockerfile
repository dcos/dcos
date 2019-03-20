FROM ubuntu:16.04
MAINTAINER help@dcos.io

RUN apt-get -qq update && apt-get -y install \
  autoconf \
  automake \
  autopoint \
  cmake \
  cpp \
  curl \
  default-jdk \
  default-jre \
  dpkg-dev \
  g++-4.8 \
  gcc-4.8 \
  gettext-base \
  git \
  gzip \
  libapr1-dev \
  libc6-dev \
  libcurl4-openssl-dev \
  libnl-3-dev \
  libnl-genl-3-dev \
  libpcre++-dev \
  libpopt-dev \
  libsasl2-dev \
  libsvn-dev \
  libsystemd-dev \
  libtool \
  linux-headers-4.4.0-45-generic \
  make \
  maven \
  patch \
  pkg-config \
  python-dev \
  python-pip \
  python-setuptools \
  ruby \
  scala \
  unzip \
  wget \
  xutils-dev \
  xz-utils \
  zlib1g-dev

RUN ln -sf /usr/bin/cpp-4.8 /usr/bin/cpp && \
  ln -sf /usr/bin/g++-4.8 /usr/bin/g++ && \
  ln -sf /usr/bin/gcc-4.8 /usr/bin/gcc && \
  ln -sf /usr/bin/gcc-ar-4.8 /usr/bin/gcc-ar && \
  ln -sf /usr/bin/gcc-nm-4.8 /usr/bin/gcc-nm && \
  ln -sf /usr/bin/gcc-ranlib-4.8 /usr/bin/gcc-ranlib && \
  ln -sf /usr/bin/gcov-4.8 /usr/bin/gcov

ENV GOLANG_VERSION 1.11.5
ENV GOLANG_DOWNLOAD_URL https://golang.org/dl/go$GOLANG_VERSION.linux-amd64.tar.gz
ENV GOLANG_DOWNLOAD_SHA256 ff54aafedff961eb94792487e827515da683d61a5f9482f668008832631e5d25

RUN curl -fsSL "$GOLANG_DOWNLOAD_URL" -o golang.tar.gz \
  && echo "$GOLANG_DOWNLOAD_SHA256  golang.tar.gz" | sha256sum -c - \
  && mkdir -p /gobootstrap \
  && tar -C /gobootstrap -xzf golang.tar.gz \
  && rm golang.tar.gz

ENV GOROOT_BOOTSTRAP /gobootstrap/go
ENV GOLANG_COMMIT 3fb9dafacc45817296885a6e877ba7a5f1c199a4
ARG USER=root
RUN git clone https://go.googlesource.com/go /usr/local/go && \
        cd /usr/local/go && \
        git checkout ${GOLANG_COMMIT} && \
        cd src && \
        # The golang build runs all tests as part of the build process. The
        # tests include privileged syscalls tests in linux. The `docker build`
        # command cannot be executed in privileged dome and thus the syscall
        # tests are failing. The syscall tests are looking for presence of
        # `./dockerenv` file that indicates that tests are executed in a docker
        # container.
        # https://github.com/moby/moby/issues/1916
        touch /.dockerenv && \
        ./all.bash && \
    # Remove the bootstrap go
    rm -rf /gobootstrap

# Set GOPATH to expected pkgpanda package path for DC/OS
ENV GOPATH /pkg
ENV PATH $GOPATH/bin:/usr/local/go/bin:$PATH

RUN mkdir -p "$GOPATH/src" "$GOPATH/bin" && chmod -R 777 "$GOPATH"

RUN pip install awscli

ENTRYPOINT ["/bin/bash", "-o", "nounset", "-o", "pipefail", "-o", "errexit"]
