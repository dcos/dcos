$ErrorActionPreference = "stop"

if (-not (test-path "c:\pkg\src\single_source\foo")) {
	throw "Single source file wasn't copied where it should have been."
	exit 1
}
