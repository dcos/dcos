Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 2.1.0 (in development)


### What's new

* Switched from Oracle Java 8 to OpenJDK 8 (DCOS-54902)

* Updated DC/OS UI to [master+v2.149.3](https://github.com/dcos/dcos-ui/releases/tag/master+v2.149.3).

* The configuration option `MARATHON_ACCEPTED_RESOURCE_ROLES_DEFAULT_BEHAVIOR` replaces the config option `MARATHON_DEFAULT_ACCEPTED_RESOURCE_ROLES`. Please see the Marathon [command-line flag documentation](https://github.com/mesosphere/marathon/blob/master/docs/docs/command-line-flags.md) for a description of the flag.

* Updated to [Mesos 1.9](https://github.com/apache/mesos/blob/4895d4430f1349dc126fb004102184f8d0e9d2b3/CHANGELOG). (DCOS_OSS-5342)

* Mesos overlay networking: support dropping agents from the state. (DCOS_OSS-5536)

* Update CNI to 0.7.6

* Updated to Boost 1.65.0 (DCOS_OSS-5555)


### Breaking changes

* Remove the octarine package from DC/OS. It was originally used as a proxy for the CLI but is not used for this purpose, anymore.

* DC/OS Net: wait till agents become active before fanning out Mesos tasks. (DCOS_OSS-5463)

* Remove the avro-cpp package from DC/OS. It was originally used as part of the metrics-collection framework which now relies on a different infrastructure.

* Remove the spartan package from DC/OS. Is was deprecated in 1.11 and replaced by dcos-net.

* Remove the toybox package from DC/OS. Is was used only by Spartan.