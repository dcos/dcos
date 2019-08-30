Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 1.14.0 (in development)


### What's new

* Added the ability to drain agent nodes via the DC/OS CLI and UI. (DCOS-53654)
* Remove nogroup group from installation (COPS-5220)

* Created new diagnostics bundle REST API with performance improvements. (DCOS_OSS-5098)

* Upgraded Marathon to 1.9.71. Marathon 1.9 brings support for multi-role, enabling you to launch services for different roles (against different Mesos quotas) with the same Marathon instance.

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

* Updated DC/OS UI to [master+v2.148.1](https://github.com/dcos/dcos-ui/releases/tag/master+v2.148.1).

* Added L4LB metrics in DC/OS Net. (DCOS_OSS-5011)

* Updated to [Mesos 1.9.0-rc3](https://github.com/apache/mesos/blob/cacc0e7a629de4fb1e678d814b30fd716bcb29d7/CHANGELOG). (DCOS_OSS-5342)

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
