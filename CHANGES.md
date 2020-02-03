Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 2.1.0 (in development)


### What's new

* Added a new configuration option `mesos_http_executors_domain_sockets`, which will cause the mesos-agent to use
  domain sockets when communicating with executors. While this change should not have any visible impact on users
  in itself, it does enable administrators to write firewall rules blocking unauthorized access to the agent port
  5051 since access to this will not be required anymore for executors to work.

* Switched from Oracle Java 8 to OpenJDK 8 (DCOS-54902)

* Updated DC/OS UI to [master+v2.150.2](https://github.com/dcos/dcos-ui/releases/tag/master+v2.150.2).

* The configuration option `MARATHON_ACCEPTED_RESOURCE_ROLES_DEFAULT_BEHAVIOR` replaces the config option `MARATHON_DEFAULT_ACCEPTED_RESOURCE_ROLES`. Please see the Marathon [command-line flag documentation](https://github.com/mesosphere/marathon/blob/master/docs/docs/command-line-flags.md) for a description of the flag.

* Updated to Mesos [1.10.0-dev](https://github.com/apache/mesos/blob/3d197d8e815f1f2de0565ce64547f409997c5e82/CHANGELOG)
* Updated to Mesos [1.10.0-dev](https://github.com/apache/mesos/blob/3d197d8e815f1f2de0565ce64547f409997c5e82/CHANGELOG)

* Mesos overlay networking: support dropping agents from the state. (DCOS_OSS-5536)

* Update CNI to 0.7.6

* Updated to Boost 1.65.0 (DCOS_OSS-5555)

* Admin Router: Accept nil task list from Marathon when updating cache. (DCOS_OSS-5541)

* Marathon pod instances are now included in the DC/OS diagnostic bundle (DCOS_OSS-5616)

* Replace [docker-gc](https://github.com/spotify/docker-gc) with `docker system prune`. (DCOS_OSS-5441)

* Port the Mesos Fluent Bit container logger module to Windows. (DCOS-58622)

* Port the Mesos open source metrics module to Windows. (DCOS-58008)

* Add etcd into DC/OS. (DCOS-59004)

* Update libpq to 9.6.15 (DCOS-59145)

* Enable proxing of gRPC requests through Admin Router (DCOS-59091)

* Calico in DC/OS: introduced Calico networking into DC/OS, and provided network policy support (DCOS-58413)

* Updated DC/OS UI to [master+v2.154.16](https://github.com/dcos/dcos-ui/releases/tag/master+v2.154.16).
### Breaking changes

* Remove the octarine package from DC/OS. It was originally used as a proxy for the CLI but is not used for this purpose, anymore.

* DC/OS Net: wait till agents become active before fanning out Mesos tasks. (DCOS_OSS-5463)

* Remove the avro-cpp package from DC/OS. It was originally used as part of the metrics-collection framework which now relies on a different infrastructure.

* Remove the spartan package from DC/OS. Is was deprecated in 1.11 and replaced by dcos-net.

* Remove the toybox package from DC/OS. Is was used only by Spartan.

* Remove the dcos-history-service from DC/OS. (DCOS-58529)

* New format for Admin Router access logs. (DCOS-59598)

* Update OpenResty to 1.15.8.2. (DCOS-61159)

### Fixed and improved

* Reserve all agent VTEP IPs upon recovering from replicated log. (DCOS_OSS-5626)

* Set network interfaces as unmanaged for networkd only on coreos. (DCOS-60956)

* Marathon launched too many tasks. (DCOS-62078)

* Marathon used to omit pod status report with tasks in `TASK_UNKONW` state. (MARATHON-8710)

* Update Kazoo to version 2.6.1. (DCOS-63065)

* With UnreachableStrategy, setting `expungeAfterSeconds` and `inactiveAfterSeconds` to the same value will cause the
  instance to be expunged immediately; this helps with `GROUP_BY` or `UNIQUE` constraints. (MARATHON-8719)
