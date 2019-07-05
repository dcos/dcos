Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 1.14.0 (in development)


### What's new

* Updated Signal service to release [1.6.0](https://github.com/dcos/dcos-signal/releases/tag/1.6.0)

* Metronome post-install configuration can be added to `/var/lib/dcos/metronome/environment`. (DCOS_OSS-5309)

* The DC/OS configuration variable `mesos_seccomp_enabled` now defaults to `true`, with `mesos_seccomp_profile_name` set to `default.json`. This is not expected to break tasks. If you experience problems, though, please note that seccomp can be disabled for individual tasks through the DC/OS SDK and Marathon. (DCOS-50038)

* Updated ref of dvdcli to fix dvdcli package build (DCOS-53581)

* Updated DC/OS UI to [master+v2.111.1](https://github.com/dcos/dcos-ui/releases/tag/master+v2.111.1)

* Fixed performance degradation in Lashup. As of now, dcos-dns uses a new LWW mode to gossip dns zone updates. (DCOS_OSS-4240)

* Optimized memory and cpu usage in dcos-net. (DCOS_OSS-5269, DCOS_OSS-5268)

* Telegraf now supports specyfying port names for task-label based Prometheus endpoints discovery. (DCOS-55100)

* Enabled Mesos IPC namespace isolator for configurable IPC namespace and /dev/shm. (DCOS-54618)

* Enhanced compatibility of `gen/build_deploy/bash.py` with Oracle Linux (Thanks to Michal Jakobczyk for the patch).

* Upgraded Admin Router's underlying OpenResty/nginx from 1.13.x to 1.15.x. (DCOS_OSS-5320)

* Upgraded Erlang OTP to release 22.0.3. (DCOS_OSS-5276)

* Upgraded platform CPython to release 3.6.8. (DCOS_OSS-5318)

* Upgraded CockroachDB to release [2.1.7](https://www.cockroachlabs.com/docs/releases/v2.1.7.html). (DCOS_OSS-5262)

* Upgraded platform curl from 7.59.0 to 7.65.1. (DCOS_OSS-5319)

* Upgraded platform OpenSSL from 1.0.2x to release 1.1.1x. (DCOS-54108)

* Updated DC/OS UI to [master+v2.117.0](https://github.com/dcos/dcos-ui/releases/tag/master+v2.117.0)

* Added L4LB metrics in DC/OS Net. (DCOS_OSS-5011)

* Bumped Mesos to upstream commit '1a6760c60dc823b088ffbcf48909cf3e371570f3'. (DCOS_OSS-5342)


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
