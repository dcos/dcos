# DC/OS Installer Utilities
This submodule provides access to various helper functions we need throughout the rest of the module.

Acceptable methods are ones that do not call other submodules within DC/OS installer, but rather provide baseline utilitarian, atomic value.

We don't want to call other submodules from this class because those classes are most likely calling us, this will result in circular imports.

## Methods
Atomic, straightforward.

## Module Constants
Since we have several constants we need to a single source of truth for them, this is the place.
