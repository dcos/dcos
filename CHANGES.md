Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 2.1.0 (in development)


### What's new

* Switched from Oracle Java 8 to OpenJDK 8 (DCOS-54902)

* Updated DC/OS UI to [master+v2.150.2](https://github.com/dcos/dcos-ui/releases/tag/master+v2.150.2).

* The configuration option `MARATHON_ACCEPTED_RESOURCE_ROLES_DEFAULT_BEHAVIOR` replaces the config option `MARATHON_DEFAULT_ACCEPTED_RESOURCE_ROLES`. Please see the Marathon [command-line flag documentation](https://github.com/mesosphere/marathon/blob/master/docs/docs/command-line-flags.md) for a description of the flag.

* Updated to Mesos [1.10.0-dev](https://github.com/apache/mesos/blob/2a1c5d518b43be21673b2cfdf72fc2e60658a826/CHANGELOG)

* Mesos overlay networking: support dropping agents from the state. (DCOS_OSS-5536)

* Update CNI to 0.7.6

* Updated to Boost 1.65.0 (DCOS_OSS-5555)

* Admin Router: Accept nil task list from Marathon when updating cache. (DCOS_OSS-5541)

* Marathon pod instances are now included in the DC/OS diagnostic bundle (DCOS_OSS-5616)

* Replace [docker-gc](https://github.com/spotify/docker-gc) with `docker system prune`. (DCOS_OSS-5441)

* Port the Mesos Fluent Bit container logger module to Windows. (DCOS-58622)

* Port the Mesos open source metrics module to Windows. (DCOS-58008)

* Switch to Mesos Operator Streaming API in DC/OS L4LB (DCOS_OSS-5464)

* Add etcd into DC/OS. (DCOS-59004)
* Update libpq to 9.6.15 (DCOS-59145)

### Breaking changes

* Remove the octarine package from DC/OS. It was originally used as a proxy for the CLI but is not used for this purpose, anymore.

* DC/OS Net: wait till agents become active before fanning out Mesos tasks. (DCOS_OSS-5463)

* Remove the avro-cpp package from DC/OS. It was originally used as part of the metrics-collection framework which now relies on a different infrastructure.

* Remove the spartan package from DC/OS. Is was deprecated in 1.11 and replaced by dcos-net.

* Remove the toybox package from DC/OS. Is was used only by Spartan.

* Remove the dcos-history-service from DC/OS. (DCOS-58529)

### Fixed and improved

* Reserve all agent VTEP IPs upon recovering from replicated log. (DCOS_OSS-5626)
