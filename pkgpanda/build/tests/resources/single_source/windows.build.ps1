$ErrorActionPreference = "stop"

if (-not (test-path "c:\pkg\src\single_source\foo")) {
	get-chileitem -recurse "c:\pkg\src\single_source"
	throw "Single source file wasn't copied where it should have been."
	exit 1
}