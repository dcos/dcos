$ErrorActionPreference = "stop"

if (-not (test-path "c:\pkg\src\url_extract-tar\bar")) {
	throw "Single source file wasn't copied where it should have been."
	exit 1
}
