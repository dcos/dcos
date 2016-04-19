# Pkgpanda

Manages the collection of DC/OS components on the host system.

Most DC/OS components ship inside Docker containers for ease of deployment. Some, however, we need to not ship inside of containers because they are hostile to containers, or because the host OS we are integrating with needs tighter coupling with them (systemd unit files, mesos-{master, slave}, mesos modules, mesos config, java, python, etc).

Pkgpanda allows for having multiple versions of every component present on a host, and then can select a subset of those
which are currently active.

## Documentation

See the `docs/` folder for current documentaiton.

## Running the Tests

Run `tox` in the top level directory.
