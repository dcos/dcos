FROM ubuntu:16.04
MAINTAINER help@dcos.io

RUN apt-get -qq update && apt-get -y install \
  autoconf \
  automake \
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

RUN pip install awscli
