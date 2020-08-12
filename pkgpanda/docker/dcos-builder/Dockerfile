FROM ubuntu:16.04
MAINTAINER help@dcos.io

RUN apt-get -qq update && apt-get -y install \
  autoconf \
  automake \
  autopoint \
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
  zlib1g-dev \
  bison \
  flex \
  libnfnetlink-dev \
  libmnl-dev \
  libnetfilter-conntrack-dev \
  libnetfilter-cttimeout-dev \
  libnetfilter-cthelper0-dev \
  libnetfilter-queue-dev

ENV CMAKE_VERSION 3.17.0
RUN set -ex \
  && curl -sSL https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-Linux-x86_64.sh \
        -o cmake.sh \
  && echo "c20a2878f5f5ca1bc00f0c987b015984360a6b32 cmake.sh" | \
        sha1sum -c --quiet - \
  && sh cmake.sh --prefix=/usr/local --skip-license \
  && rm cmake.sh \
  && cmake --version

RUN ln -sf /usr/bin/cpp-4.8 /usr/bin/cpp && \
  ln -sf /usr/bin/g++-4.8 /usr/bin/g++ && \
  ln -sf /usr/bin/gcc-4.8 /usr/bin/gcc && \
  ln -sf /usr/bin/gcc-ar-4.8 /usr/bin/gcc-ar && \
  ln -sf /usr/bin/gcc-nm-4.8 /usr/bin/gcc-nm && \
  ln -sf /usr/bin/gcc-ranlib-4.8 /usr/bin/gcc-ranlib && \
  ln -sf /usr/bin/gcov-4.8 /usr/bin/gcov

ENV GOLANG_VERSION 1.15
ENV GOLANG_DOWNLOAD_URL https://golang.org/dl/go$GOLANG_VERSION.linux-amd64.tar.gz
ENV GOLANG_DOWNLOAD_SHA256 2d75848ac606061efe52a8068d0e647b35ce487a15bb52272c427df485193602

RUN curl -fsSL "$GOLANG_DOWNLOAD_URL" -o golang.tar.gz \
  && echo "$GOLANG_DOWNLOAD_SHA256  golang.tar.gz" | sha256sum -c - \
  && tar -C /usr/local -xzf golang.tar.gz \
  && rm golang.tar.gz

# Set GOPATH to expected pkgpanda package path for DC/OS
ENV GOPATH /pkg
ENV PATH $GOPATH/bin:/usr/local/go/bin:$PATH

RUN mkdir -p "$GOPATH/src" "$GOPATH/bin" && chmod -R 777 "$GOPATH"

RUN pip install awscli

ENTRYPOINT ["/bin/bash", "-o", "nounset", "-o", "pipefail", "-o", "errexit"]
