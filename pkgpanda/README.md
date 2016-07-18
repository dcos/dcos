# Pkgpanda

`pkgpanda` manages the collection of DC/OS components on the host system.

Most DC/OS components ship inside Docker containers for ease of deployment. Some, however, need not ship inside of
containers because they are hostile to containers, or because the host OS we are integrating with needs tighter
coupling with those components. Examples of those components include `systemd unit files`, `mesos-master`,
`mesos-slave` modules,` mesos` config,  `java` and `python` language runtime, etc.

`pkgpanda` allows for having multiple versions of every component present on a host, mark certain versions of those
components as active, and then select a subset of currently active components.

## Documentation

See the `docs/` folder for current documentaiton.

## Running the Tests

Run `tox` in the top level directory.
