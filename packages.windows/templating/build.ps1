[CmdletBinding(DefaultParameterSetName="Standard")]
param(
    [string]
    [ValidateNotNullOrEmpty()]
    $pkgSrc,  # Location of the packages tree sources

    [string]
    [ValidateNotNullOrEmpty()]
    $pkgDest  # Location of the packages tree compiled binaries

)

#$CFLAGS="-I/opt/mesosphere/include -I/opt/mesosphere/active/ncurses/include -I/opt/mesosphere/active/openssl/include"
#$LDFLAGS="-L/opt/mesosphere/lib -L/opt/mesosphere/active/ncurses/lib -L/opt/mesosphere/active/openssl/lib -Wl,-rpath=/opt/mesosphere/active/ncurses/lib -Wl,-rpath=/opt/mesosphere/active/openssl/lib -Wl,-rpath=/opt/mesosphere/lib"
#$CPPFLAGS=$CFLAGS

#pushd /pkg/src/erlang
#./otp_build setup -a --prefix=$PKG_PATH --with-ssl=/opt/mesosphere/active/openssl --with-termcap=/opt/mesosphere/active/ncurses --enable-dirty-schedulers --disable-hipe --enable-kernel-poll
#make -j$NUM_CORES
#make install
#popd

#service=${PKG_PATH}/dcos.target.wants/dcos-epmd.service
#mkdir -p $(dirname $service)
#cat <<EOF > $service
#[Unit]
#Description=Erlang Port Mapping Daemon (EPMD): facilitates communication between distributed Erlang programs
#
#[Service]
#User=dcos_epmd
#Restart=always
#StartLimitInterval=0
#RestartSec=5
#LimitNOFILE=16384
#WorkingDirectory=${PKG_PATH}
#EnvironmentFile=/opt/mesosphere/environment
#ExecStart=${PKG_PATH}/bin/epmd -port 61420
#Environment=HOME=/opt/mesosphere
#EOF
