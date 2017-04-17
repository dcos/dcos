#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE}")/.." && pwd -P)
cd "${project_dir}"

echo "Generating API docs..." >&2
make api

# refresh the index that diff-files uses
git update-index --refresh

if ! git diff-files --quiet ; then
  echo "Found unstaged changes!" >&2
  echo "Please run \`cd packages/adminrouter/extra/src && make api\` and commit the result." >&2
  exit 1
fi

if ! git ls-files --exclude-standard --others ; then
  echo "Found untracked and unignored files!" >&2
  echo "Please run \`cd packages/adminrouter/extra/src && make api\` and commit the result." >&2
  exit 1
fi

echo "No changes found -- API docs are up to date." >&2
