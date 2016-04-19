# Architecture of getting dcos bits to machines

*DC/OS CLI*: Issue commands to control the cluster
 - dcos install module
 - dcos upgrade mesos {target-version}
 - dcos slave remove
 - dcos slave add

**Deploy Module**: Perform tasks/call endpoints on every machine, query machine state to determine deployment status. Aggregates status pings from the Restart Helper to monitor rollout progress / provide better insights. Has an endpoint `halt` which can have HTTP requests made to it by any sort of SLA monitoring setup an organization has in order to stop the deploy  module from taking further action without explicit clearing from and admin.

**Package Manager (CLI + Module)**: Local on every node in the mesos cluster. Coordinates adding/removing state blobs (Packages), Validating state transitions (Always must have one mesos active, one mesos config active, n modules, etc), listing what packages are available/cached locally.  This is a library for managing the packages + file system layout which is well defined. Optionally pings caller on completion. (Can also be scraped to check state).

*CLI*: Local command line version of package manager used for bootstrapping / operating when a mesos isn’t running. Localhost only.

*Module*: Collection of mesos endpoints for fetching / removing packages from the local filesystem. List the current “active” set of modules.

**Package Repository**: Web server serving package tarballs. Accessible from all nodes in the cluster. Could be s3, nginx, etc. Doesn’t matter. I just have to be able to use mesos fetcher, curl, or some equivalent to get data from it.

**Restart (Module + Helper)**:

*Module*: Restarts mesos, switching from the running set of packages to the specified set of packages. All packages must be local before restart is called. Uses the Restart Helper to ensure mesos comes up cleanly.

*Helper*: Helper binary which lives next to mesos. Stops mesos, then swaps out the active modules using the package cli. Starts up mesos, watching to see if it comes up cleanly. If it doesn’t, tries to roll back. On all events / status changes it pings the Deploy Module so that the deploy module can track the status. If a status ping fails, the deploy module needs.

Helper can also provides “bootstrap”, fetching and activating necessary packages for running

**Provisioning Module (Artemis)**: Provides an api call to decommision_slave, as well as one to add_slave. Must be injected with the necessary configuration to launch a new slave on the current hosting provider (AWS for v1).

**Config Generator**: Given a list of enabled modules, and user-specified options (Resources, etc), generate a new config package.
