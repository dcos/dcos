#!/bin/bash

# protoc is compiled with shared libaries (a part of mesos dcos package)
# and needs LD_LIBARY_PATH to be set correctly, this is done by sourcing
# the `environment.export` file below.
source /opt/mesosphere/environment.export

pushd /pkg/src/mesos-modules

mkdir -p build
pushd build

cmake .. \
  -DMESOS_ROOT=/opt/mesosphere/active/mesos \
  -DBOOST_ROOT_DIR=/opt/mesosphere/active/boost-libs \
  -DCMAKE_INSTALL_RPATH=/opt/mesosphere/lib \
  -DBUILD_TESTING=OFF \
  -DCMAKE_BUILD_TYPE=Release

cmake --build . --config Release -- -j$NUM_CORES

cmake -DCMAKE_INSTALL_PREFIX=$PKG_PATH -P cmake_install.cmake

popd
popd
