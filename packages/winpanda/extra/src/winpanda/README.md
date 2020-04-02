# Winpanda 

-------------------------------------------------------------------------------
  Winpanda is a part of DC/OS Windows Agent node management toolset. It manages
the whole lifecycle of a DC/OS service package at a Windows Agent node,
beginning from initial package installation (download, install, configure) to
host OS service management (setup, start, stop, remove, etc.) and to
upgrade/downgrade package version.  
  Winpanda should not be confused with the Pkgpanda tool, which provides much
wider range of functionality. It only implements for DC/OS Windows agent nodes
a part of functionality of the Pkgpanda, which is involved in package
management on DC/OS Linux agent nodes.



## Design Documentation

-------------------------------------------------------------------------------
>_>>>>> Under Construction <<<<<_



## Running Test Suite

-------------------------------------------------------------------------------

Change to the `winpanda` extra directory.
```sh
cd packages/winpanda/extra
```

The first time, create a new Python virtualenv.
```sh
virtualenv venv --python=<ABSOLUTE_PATH_TO_PYTHON3_EXE>
```

Activate the new or existing virtualenv.

On Linux:
```sh
source venv/bin/activate
```
On Windows:
```bat
venv\Scripts\activate.bat
```

In a new virtualenv, install `pytest` and the `winpanda` dependencies.
```sh
pip install pytest mock
pip install -r src/winpanda/requirements.txt
``` 

Run `pytest`.
```sh
pytest
```
