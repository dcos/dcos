#!/bin/bash

set -e  # Fail the script if anything fails
set -x  # Verbose output
set -u  # Undefined variables

cd $OPENRESTY_DIR
./configure \
    "--prefix=$AR_BIN_DIR" \
    --with-ipv6 \
    --with-file-aio \
    --with-http_gunzip_module \
    --with-http_gzip_static_module \
    --without-mail_pop3_module \
    --without-mail_imap_module \
    --without-mail_smtp_module \
    --with-http_ssl_module \
    --with-luajit \
    "$@"

make -j${NUM_CORES}
make install
