Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 2.2.0-dev (in development)

* Updated to Mesos [1.11.0-dev](https://github.com/apache/mesos/blob/c78dc333fc893a43d40dc33299a61987198a6ea9/CHANGELOG)

* Update to Fluentbit [1.4.6](https://docs.fluentbit.io/manual/installation/upgrade-notes)

* Remove DC/OS Signal [D2IQ-69818](https://jira.d2iq.com/browse/D2IQ-69818)
* Starting services on clusters with static masters now only requires a majority of ZooKeeper nodes to be available. 
  Previously, all ZooKeeper nodes needed to be available.
  On clusters with dynamic master lists, all ZooKeeper nodes must still be available. (D2IQ-4248)

### Fixed and improved

* Fix incorrect ownership after migration of `/run/dcos/telegraf/dcos_statsd/containers`. (D2IQ-69295)

* Fix to allow spaces in services endpoint URI's. (DCOS_OSS-5967)

* Update Telegraf configuration to reduce errors, vary requests to reduce load, sample less frequently. (COPS-5629)

* Display user email address in UI when logging in using external provider. (D2IQ-70199)

* Updated DC/OS UI to [v5.1.7](https://github.com/dcos/dcos-ui/releases/tag/v5.1.7).

* Removed Exhibitor snapshot cleanup and now rely on ZooKeeper autopurge. (D2IQ-68109)

* Updated CockroachDB Python package to 0.3.5. (D2IQ-62221)

* Wait on ZooKeeper instead of Exhibitor during bootstrap. (D2IQ-70393)


* Updated Exhibitor to version running atop [Jetty 9.4.30](https://github.com/dcos/exhibitor/commit/e6e232e1)

#### Bump Marathon to 1.10.26

* Fix a regression where Marathon would sometimes fail to replace lost unreachable tasks (MARATHON-8758)

## DC/OS 2.1.0 (2020-06-09)


### What's new

* Upgrade coreOS AMIs (D2IQ-64271)

* Added a new configuration option `mesos_http_executors_domain_sockets`, which will cause the mesos-agent to use
  domain sockets when communicating with executors. While this change should not have any visible impact on users
  in itself, it does enable administrators to write firewall rules blocking unauthorized access to the agent port
  5051 since access to this will not be required anymore for executors to work.

* Switched from Oracle Java 8 to OpenJDK 8 (DCOS-54902)

* Updated DC/OS UI to [v5.0.52](https://github.com/dcos/dcos-ui/releases/tag/v5.0.52).

* The configuration option `MARATHON_ACCEPTED_RESOURCE_ROLES_DEFAULT_BEHAVIOR` replaces the config option `MARATHON_DEFAULT_ACCEPTED_RESOURCE_ROLES`. Please see the Marathon [command-line flag documentation](https://github.com/mesosphere/marathon/blob/master/docs/docs/command-line-flags.md) for a description of the flag.

* Updated to Mesos [1.10.0-dev](https://github.com/apache/mesos/blob/1ff2fcd90eabd98786531748869b8596120f7dfe/CHANGELOG)

* Mesos overlay networking: support dropping agents from the state. (DCOS_OSS-5536)

* Update CNI to 0.7.6

* Updated to Boost 1.65.0 (DCOS_OSS-5555)

* Admin Router: Accept nil task list from Marathon when updating cache. (DCOS_OSS-5541)

* Marathon pod instances are now included in the DC/OS diagnostic bundle (DCOS_OSS-5616)

* Replace [docker-gc](https://github.com/spotify/docker-gc) with `docker system prune`. (DCOS_OSS-5441)

* Port the Mesos Fluent Bit container logger module to Windows. (DCOS-58622)

* Port the Mesos open source metrics module to Windows. (DCOS-58008)

* Add etcd into DC/OS. (DCOS-59004)

* Add etcd metrics into the DC/OS Telegraf Pipeline. (D2IQ-61004)

* Update libpq to 9.6.15 (DCOS-59145)


### Security updates


### Notable changes

* Upgraded to CockroachDB 19.1 (D2IQ-69872)


### Fixed and improved

* Updated `etcd` to [v3.4.9](https://github.com/etcd-io/etcd/releases/tag/v3.4.9).

* Fixing some corner-cases that could render `etcd` unable to start [D2IQ-69069](https://jira.d2iq.com/browse/D2IQ-69069)

* Storing etcd initial state on `/var/lib/dcos` instead of `/run/dcos` [COPS-6183](https://jira.d2iq.com/browse/COPS-6183)

* Updated DC/OS UI to [v5.2.1](https://github.com/dcos/dcos-ui/releases/tag/v5.2.1).

* Removed Exhibitor snapshot cleanup and now rely on ZooKeeper autopurge. (D2IQ-68109)

* Ensured that marathon and SDK labeled reservations are not offered to other schedulers (D2IQ-68800)

* Updated OpenResty to 1.15.8.4. (DCOS_OSS-5967)

* Update Telegraf configuration to reduce errors, vary requests to reduce load, sample less frequently. (COPS-5629)

* Update Bouncer dependencies. (D2IQ-54115, D2IQ-62221)

* Updated Exhibitor to version running atop [Jetty 9.4.30](https://github.com/dcos/exhibitor/commit/e6e232e1)

* Ensure Docker network for Calico is eventually created correctly following failures. (D2IQ-70674)

* Check that `spartan` ips (`198.51.100.1-3`) are not listed as upstream resolvers. (COPS-4616)

* Log diff to resolv.conf in addition to the new contents. (COPS-6411)
