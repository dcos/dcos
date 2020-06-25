Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 2.0.6 (in development)

### What's new

* Updated DC/OS UI to [v5.1.1](https://github.com/dcos/dcos-ui/releases/tag/v5.1.1)
* Update to Fluentbit [1.4.6](https://docs.fluentbit.io/manual/installation/upgrade-notes)


### Security updates

### Notable changes

### Fixed and improved

* Fix incorrect ownership after migration of `/run/dcos/telegraf/dcos_statsd/containers`. (D2IQ-69295)

* Fix to allow spaces in services endpoint URI's. (DCOS_OSS-5967)


## DC/OS 2.0.5 (2020-06-15)

### Security updates

### Notable changes

* Updated to Mesos [1.9.1-dev](https://github.com/apache/mesos/blob/b3b6dbb27a93a9ace4e4d2d1e83b16ea92f1a8e1/CHANGELOG)

### Fixed and improved

* Removed trailing newline from ZooKeeper log messages. (D2IQ-68394)

* Ensured that marathon and SDK labeled reservations are not offered to other schedulers. (D2IQ-68800)


#### Update Metronome to 0.6.48

* Fix an issue in Metronome where it became unresponsive when lots of pending jobs existed during boot. (DCOS_OSS-5965)


## DC/OS 2.0.4 (2020-05-12)

### What's new

* Updated DC/OS UI to [v4.0.1](https://github.com/dcos/dcos-ui/releases/tag/v4.0.1).

* Update Metronome to 0.6.44

* Metronome jobs can be configured to join container networks (MARATHON-8727)

### Fixed and improved

* Update OpenResty to 1.15.8.3. (D2IQ-66506)

* Update to OpenSSL 1.1.1g. (D2IQ-67050)

* Update Metronome to 0.6.44

* A bug was introduced in Metronome for DC/OS 2.0.3 in which jobs created in previous versions of DC/OS were not seen. This has been fixed, and jobs created before 2.0.3 are visible once again. (MARATHON-8746)

## DC/OS 2.0.3 (2020-03-25)

* Updated to Mesos [1.9.1-dev](https://github.com/apache/mesos/blob/b84b0a4bd8945b0901214b90b61e6a54fa4b3215/CHANGELOG)

### What's new

### Fixed and improved

* With UnreachableStrategy, setting `expungeAfterSeconds` and `inactiveAfterSeconds` to the same value will cause the
  instance to be expunged immediately; this helps with `GROUP_BY` or `UNIQUE` constraints. (MARATHON-8719)

* Allow Admin Router to accept files up to 32GB, such as for uploading large packages to Package Registry. (DCOS-61233)

* Fix Telegraf migration when no containers present. (D2IQ-64507)

* Update OpenSSL to 1.1.1d. (D2IQ-65604)

* Adjust dcos-net (l4lb) to allow for graceful shutdown of connections by changing the VIP backend weight to `0`
  when tasks are unhealthy or enter the `TASK_KILLING` state instead of removing them. (D2IQ-61077)

* Update Metronome to 0.6.41

    * There was a case where regex validation of project ids was ineffecient for certain inputs. The regex has been optimized. (MARATHON-8730)

* Marathon updated to 1.9.136

    * /v2/tasks plaintext output in Marathon 1.5 returned container network endpoints in an unusable way (MARATHON-8721)

    * Marathon launched too many tasks. (DCOS_OSS-5679)

    * Marathon used to omit pod status report with tasks in `TASK_UNKOWN` state. (MARATHON-8710)

    * With UnreachableStrategy, setting `expungeAfterSeconds` and `inactiveAfterSeconds` to the same value will cause the
      instance to be expunged immediately; this helps with `GROUP_BY` or `UNIQUE` constraints. (MARATHON-8719)

    * Marathon was checking authorization for unrelated apps when performing a kill-and-scale operations; this has been resolved. (MARATHON-8731)

## DC/OS 2.0.2 (2020-01-17)

* Updated DC/OS UI to [master+v2.154.16](https://github.com/dcos/dcos-ui/releases/tag/master+v2.154.16).

### What's new

### Fixed and improved

* Set network interfaces as unmanaged for networkd only on coreos. (DCOS-60956)

* Mesos: support quoted realms in WWW-Authenticate headers. (DCOS-61529)

* Build Admin Router without SSE4.2 instructions to work on older CPUs. (DCOS_OSS-5643)

* Update Java to version 8u232. This was mistakenly downgraded during the switch to OpenJDK. (DCOS-62548)


## DC/OS 2.0.1 (2019-11-22)

* Updated to Mesos [1.9.1-dev](https://github.com/apache/mesos/blob/4575c9b452c25f64e6c6cc3eddc12ed3b1f8538b/CHANGELOG)

### What's new

### Fixed and improved

* Marathon: the upgrade to DC/OS 2.0 would fail if Marathon had undergoing a deployment during the upgrade (MARATHON-8712)

* Marathon: Pod statuses could fail to report properly with unlaunched resident pods are scaled down (MARATHON-8711)

* Marathon: Pod status report with tasks in `TASK_UNKONW` state would be omitted. (MARATHON-8710)

* dcos-net: task update leads to two DNS zone updates. (DCOS_OSS-5495)

* DC/OS overlay networks should be compared by-value. (DCOS_OSS-5620)

* Drop labels from Lashup's kv_message_queue_overflows_total metric. (DCOS_OSS-5634)

* Reserve all agent VTEP IPs upon recovering from replicated log. (DCOS_OSS-5626)


## DC/OS 2.0.0 (2019-10-17)

### What's new

* Switched from Oracle Java 8 to OpenJDK 8

* Added the ability to drain agent nodes via the DC/OS CLI and UI. (DCOS-53654)

* Remove nogroup group from installation (COPS-5220)

* Created new diagnostics bundle REST API with performance improvements. (DCOS_OSS-5098)

* Upgraded Marathon to 1.9.100. Marathon 1.9 brings support for multi-role, enabling you to launch services for different roles (against different Mesos quotas) with the same Marathon instance.

* The configuration option `marathon_new_group_enforce_role` has been added to the installation config, and defaults to "top". This changes the default role for new services posted to non-existent groups, and ultimately affects the ability to deploy to public agents. Consider switching to use a top-level group `/slave_public` for these services. The config option can be changed from "top" to "off".

* The configuration option `MARATHON_ACCEPTED_RESOURCE_ROLES_DEFAULT_BEHAVIOR` replaces the config option `MARATHON_DEFAULT_ACCEPTED_RESOURCE_ROLES`. Please see the Marathon [command-line flag documentation](https://github.com/mesosphere/marathon/blob/master/docs/docs/command-line-flags.md) for a description of the flag.

* Updated Signal service to release [1.6.0](https://github.com/dcos/dcos-signal/releases/tag/1.6.0). Also, Signal now sends telemetry data every 5 minutes instead of every hour. This is to align the frequency with DC/OS Enterprise.

* Updated to Metronome 0.6.33 which has the following benefits: When querying run detail with embed=history, successfulFinishedRuns and failedFinishedRuns contains new field tasks which is an array of taskIds of that finished run. This will allow people to query task ids even for finished job runs.  Updated to the latest version of cron-utils 9.0.0 and removed threeten-backport. This fixes a number of cron related issues in the underlying dependencies.  Fixed a bug when task status was not updated after the task turned running (when querying embed=activeRuns).  Fixes DCOS_OSS-5166 where metronome did not use the revive operation

* Metronome post-install configuration can be added to `/var/lib/dcos/metronome/environment`. (DCOS_OSS-5309)

* Updated telegraf to process mesos operations metrics (DCOS_OSS-5023)

* The DC/OS configuration variable `mesos_seccomp_enabled` now defaults to `true`, with `mesos_seccomp_profile_name` set to `default.json`. This is not expected to break tasks. If you experience problems, though, please note that seccomp can be disabled for individual tasks through the DC/OS SDK and Marathon. (DCOS-50038)

* Updated ref of dvdcli to fix dvdcli package build (DCOS-53581)

* Fixed performance degradation in Lashup. As of now, dcos-dns uses a new LWW mode to gossip dns zone updates. (DCOS_OSS-4240)

* Optimized memory and cpu usage in dcos-net. (DCOS_OSS-5269, DCOS_OSS-5268)

* Telegraf now supports specyfying port names for task-label based Prometheus endpoints discovery. (DCOS-55100)

* Enabled Mesos IPC namespace isolator for configurable IPC namespace and /dev/shm. (DCOS-54618)

* Enhanced compatibility of `gen/build_deploy/bash.py` with Oracle Linux (Thanks to Michal Jakobczyk for the patch).

* Upgraded Admin Router's underlying OpenResty/nginx from 1.13.x to 1.15.x. (DCOS_OSS-5320)

* Upgraded Erlang OTP to release 22.0.3. (DCOS_OSS-5276)

* Upgraded platform CPython to release 3.6.8. (DCOS_OSS-5318)

* Upgraded CockroachDB to release [2.1.8](https://www.cockroachlabs.com/docs/releases/v2.1.8.html). (DCOS_OSS-5360)

* Upgraded platform curl from 7.59.0 to 7.65.1. (DCOS_OSS-5319)

* Upgraded platform OpenSSL from 1.0.2x to release 1.1.1x. (DCOS-54108)

* Updated DC/OS UI to [master+v2.150.2](https://github.com/dcos/dcos-ui/releases/tag/master+v2.150.2).

* Added L4LB metrics in DC/OS Net. (DCOS_OSS-5011)

* Updated to Mesos [1.9.1-dev](https://github.com/apache/mesos/blob/88697cb136555a7c7406349cbb78c6f3b15beac5/CHANGELOG)

* Bumped Mesos modules to have overlay metrics exposed. (DCOS_OSS-5322)

* Bumped Telegraf to have Mesos overlay module metrics collected. (DCOS_OSS-5323)

* Add more vm metrics to dcos-net. (DCOS_OSS-5335)

* Introduced a new DC/OS configuration parameter `mesos_docker_volume_chown`, by default as `false`. If this parameter is set as `true`, Mesos will change the ownership of a docker volumes non-recursively to be the task user when launching a container. Please notice that this parameter is NOT recommended to switch on if there is any docker volume shared by multiple non-root users. (DCOS_OSS-5381)

* Introduced a new DC/OS configuration parameter `mesos_disallow_sharing_agent_ipc_namespace`, defaulting to `false`. This parameter can be used to control whether the top-level Mesos container is allowed to share Mesos agent host's IPC namespace and /dev/shm. (DCOS-56619)

* Introduced a new DC/OS configuration parameter `mesos_default_container_shm_size`. This parameter can be used to specify the default size of the /dev/shm for the Mesos container which has its own /dev/shm. The format is `[number][unit]`, `number` must be a positive integer and `unit` can be B (bytes), KB (kilobytes), MB (megabytes), GB (gigabytes) or TB (terabytes). (DCOS-56619)

* Add dcos-net overlay metrics. (DCOS_OSS-5324)

* Added containerizer debug endpoint into the diagnostic bundle. This endpoint is used for tracking data for stuck tasks. (DCOS-55383)

* Prune VIPs with no backends in order to avoid unbounded growth of state and messages exchanged among `dcos-net` processes. (DCOS_OSS-5356)

* DC/OS no longer increases the rate limit for journald logging.  Scale testing demonstrated that raising the limit overloads journald, causing problems for other components that see delayed or lost logs or, worse, hang until log buffers are read. The default of 10000 messages per 30 seconds appears to distinguish well between busy components and excessively verbose components. (DCOS-53763)

* DC/OS Net: Fix support for big sets in the ipset manager. (COPS-5229)

* DC/OS Net: switch to Erlang/OTP's Logger in order to be able to handle log message bursts without compromising the system stability. (DCOS_OSS-5461)

* DC/OS Net: use exponential backoff when retrying failed requests to Mesos in order not to impose additional load onto potentially already overloaded Mesos. (DCOS_OSS-5459)

* Mesos overlay networking: support dropping agents from the state. (DCOS_OSS-5536)

* Added support for new optional fields `lastModified` and `hasKnownIssues` in cosmos for packaging version v3, v4, and v5.
* Updated Marathon to 1.9.99

    * Marathon API performance has been improved. JSON serialization is 50% faster and has 50% less memory overhead.


### Breaking changes

The following parameters have been removed from the DC/OS installer:

* --set-superuser-password
* --offline
* --cli-telemetry-disabled
* --validate-config
* --preflight
* --install-prereqs
* --deploy
* --postflight

The Marathon option `MARATHON_DEFAULT_ACCEPTED_RESOURCE_ROLES` has been deprecated. Please use `MARATHON_ACCEPTED_RESOURCE_ROLES_DEFAULT_BEHAVIOR`, instead, which has valid values of `any`, `unreserved`, or `reserved`.

### Fixed and improved

* Improved the performance of command health checks to increase scalability. (DCOS-53656)

* Added framework ID tags to Mesos framework metrics. (DCOS-53302)

* Fix preflight docker version check failing for docker 1.19. (DCOS-56831)

* DC/OS Net: wait till agents become active before fanning out Mesos tasks. (DCOS_OSS-5463)
