#!/bin/bash
set -x

source /opt/mesosphere/environment

export CFLAGS="-I/opt/mesosphere/include -I/opt/mesosphere/active/libsodium/include"
export LDFLAGS="-L/opt/mesosphere/lib -L/opt/mesosphere/active/libsodium/lib -Wl,-rpath=/opt/mesosphere/active/libsodium/lib"
export CPPFLAGS=${CFLAGS}


pushd /pkg/src/dcos-net
./rebar3 update
./rebar3 as prod release
popd

cp -r /pkg/src/dcos-net/_build/prod/rel/dcos-net ${PKG_PATH}

mkdir -p $PKG_PATH/bin

# dcos-net-env

dcos_net_env="$PKG_PATH/bin/dcos-net-env"
cp "/pkg/extra/$(basename $dcos_net_env)" "$dcos_net_env"
chmod +x "$dcos_net_env"

# Systemd

dcos_net_setup="$PKG_PATH/dcos-net/bin/dcos-net-setup.py"
cp "/pkg/extra/$(basename $dcos_net_setup)" "$dcos_net_setup"
chmod +x "$dcos_net_setup"

dcos_net_service=${PKG_PATH}/dcos.target.wants/dcos-net.service
mkdir -p $(dirname $dcos_net_service)
envsubst '${PKG_PATH}' < "/pkg/extra/$(basename $dcos_net_service)" > "${dcos_net_service}"

## Gen resolv

resolvconf_service="$PKG_PATH/dcos.target.wants/dcos-gen-resolvconf.service"
mkdir -p "$(dirname "$resolvconf_service")"
cp "/pkg/extra/$(basename $resolvconf_service)" "$resolvconf_service"

resolvconf_timer="$PKG_PATH/dcos.target.wants/dcos-gen-resolvconf.timer"
mkdir -p "$(dirname "$resolvconf_timer")"
cp "/pkg/extra/$(basename $resolvconf_timer)" "$resolvconf_timer"

gen_resolvconf="$PKG_PATH/bin/gen_resolvconf.py"
cp "/pkg/extra/$(basename $gen_resolvconf)" "$gen_resolvconf"
chmod +x "$gen_resolvconf"

### Watchdogs

dcos_net_watchdog="$PKG_PATH/bin/dcos-net-watchdog.py"
cp "/pkg/extra/$(basename $dcos_net_watchdog)" "$dcos_net_watchdog"
chmod +x "$dcos_net_watchdog"

dcos_net_watchdog_service="$PKG_PATH/dcos.target.wants/dcos-net-watchdog.service"
mkdir -p "$(dirname "$dcos_net_watchdog_service")"
cp "/pkg/extra/$(basename $dcos_net_watchdog_service)" "$dcos_net_watchdog_service"
