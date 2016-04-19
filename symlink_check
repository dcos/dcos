#!/bin/bash
set -o errexit -o nounset -o pipefail

# TODO: Convert to a tox unit test

function main {
  if [ $# -eq 0 ]
  then
    msg "ERROR: must provide directories to scan as an argument"
    exit 1
  fi
  hash symlinks 2>/dev/null || { sudo apt-get -y install symlinks >/dev/null; }
  local non_relative_links=$(symlinks -vr "$@" 2>/dev/null|grep -v '^relative:')
  if [ "$non_relative_links" ]
  then
    msg "ERROR: Non-relative symlinks detected"
    msg "$non_relative_links"
    exit 1
  else
    out "Symlink check passed"
  fi
}

function msg { out "$*" >&2 ;}
function err { local x=$? ; msg "$*" ; return $(( x == 0 ? 1 : x )) ;}
function out { printf '%s\n' "$*" ;}

if [[ ${1:-} ]] && declare -F | cut -d' ' -f3 | fgrep -qx -- "${1:-}"
then "$@"
else main "$@"
fi
