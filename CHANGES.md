Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 1.14.0 (in development)


### What's new

* Upgraded Marathon to 1.9.30. Marathon 1.9 brings support for multirole, enabling you to launch services for different roles (against different Mesos quotas) with the same Marathon instance.

* Updated Signal service to release [1.6.0](https://github.com/dcos/dcos-signal/releases/tag/1.6.0)

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

* Updated DC/OS UI to [master+v2.128.1](https://github.com/dcos/dcos-ui/releases/tag/master+v2.128.1).

* Added L4LB metrics in DC/OS Net. (DCOS_OSS-5011)

* Updated to [Mesos 1.9.x](https://github.com/apache/mesos/blob/ff8c9a96be6ae1ee47faf9d5b80a518dfb4a3db0/CHANGELOG). (DCOS_OSS-5342)

* Bumped Mesos modules to have overlay metrics exposed. (DCOS_OSS-5322)

* Bumped Telegraf to have Mesos overlay module metrics collected. (DCOS_OSS-5323)

* Add more vm metrics to dcos-net. (DCOS_OSS-5335)

* Introduced a new DC/OS configuration parameter `mesos_disallow_sharing_agent_ipc_namespace`, defaulting to `false`. This parameter can be used to control whether the top-level Mesos container is allowed to share Mesos agent host's IPC namespace and /dev/shm. (DCOS-56619)

* Introduced a new DC/OS configuration parameter `mesos_default_container_shm_size`. This parameter can be used to specify the default size of the /dev/shm for the Mesos container which has its own /dev/shm. The format is `[number][unit]`, `number` must be a positive integer and `unit` can be B (bytes), KB (kilobytes), MB (megabytes), GB (gigabytes) or TB (terabytes). (DCOS-56619)

* Add dcos-net overlay metrics. (DCOS_OSS-5324)


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
