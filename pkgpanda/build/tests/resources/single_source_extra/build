#!/bin/bash

if [ ! -e /pkg/src/single_source_extra/foo ]; then
	echo "Single source file wasn't copied where it should have been."
	exit 1
fi


if [ ! -e /pkg/extra/foo ]; then
	echo "Extra not mounted as expected"
	ls -alh /pkg/extra
	exit 1
fi

