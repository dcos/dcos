$ErrorActionPreference = "stop"

$LIB_INSTALL_DIR="$PKG_PATH/lib/python3.6/site-packages"

New-Item -ItemType Directory -Path "$LIB_INSTALL_DIR"

Copy-Item -Recurse -Path "C:\pkg\build\extra\src\*" "$env:PKG_PATH\bin\"

echo "pip version: $(pip --version)"
echo "Install packages from wheel files."
# Install from local source directories (git checkout or extracted tarballs).
# Order matters. Some of these packages require Cython or build C extensions
# for speed-up if Cython is availble.
echo "Install packages from local source directories."
$packages = ("requests,pySmartDL,docopt,jinja2")
foreach ($package in $packages){
  pip install -v --no-deps --install-option="--prefix=$PKG_PATH" --root=/ /pkg/src/$package
}