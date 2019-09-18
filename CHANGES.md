Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 2.1.0 (in development)


### What's new

* Switched from Oracle Java 8 to OpenJDK 8 (DCOS-54902)

* Updated DC/OS UI to [master+v2.148.8](https://github.com/dcos/dcos-ui/releases/tag/master+v2.148.8).
* Created new diagnostics bundle REST API with performance improvements. (DCOS_OSS-5098)

* Upgraded Marathon to 1.9.73. Marathon 1.9 brings support for multi-role, enabling you to launch services for different roles (against different Mesos quotas) with the same Marathon instance.

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

* Updated DC/OS UI to [master+v2.148.2](https://github.com/dcos/dcos-ui/releases/tag/master+v2.148.2).

* Added L4LB metrics in DC/OS Net. (DCOS_OSS-5011)

* Updated to [Mesos 1.9.0-rc3](https://github.com/apache/mesos/blob/5e79a584e6ec3e9e2f96e8bf418411df9dafac2e/CHANGELOG). (DCOS_OSS-5342)

* Mesos overlay networking: support dropping agents from the state. (DCOS_OSS-5536)

### Breaking changes


### Fixed and improved

* Fixes increasing diagnostics job duration when job is done (DCOS_OSS-5494)

* Remove the octarine package from DC/OS. It was originally used as a proxy for the CLI but is not used for this purpose, anymore.
