#!/bin/bash

pushd /pkg/extra
mkdir -p $PKG_PATH/bin
gcc -static -std=gnu11 -Wall -Werror -o $PKG_PATH/bin/check-time check-time.c
