$ErrorActionPreference = "stop"

if (-not (test-path "c:\pkg\src\single_source_extra\foo")) {
	get-chileitem -recurse "c:\pkg\src\single_source_extra"
	throw "Single source file wasn't copied where it should have been."
	exit 1
}


if (-not (test-path "c:\pkg\extra\foo")) {
	get-chileitem -recurse "c:\pkg\extra"
	throw "Extra not mounted as expected"
	exit 1
}
