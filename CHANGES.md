Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 1.14.0 (in development)


### What's new

* The DC/OS configuration variable `mesos_seccomp_enabled` now defaults to `true`, with `mesos_seccomp_profile_name` set to `default.json`. This is not expected to break tasks. If you experience problems, though, please note that seccomp can be disabled for individual tasks through the DC/OS SDK and Marathon. (DCOS-50038)

* Updated ref of dvdcli to fix dvdcli package build (DCOS-53581)

* Updated DC/OS UI to [master+v2.108.0](https://github.com/dcos/dcos-ui/releases/tag/master+v2.108.0)

### Breaking changes

Admin Router now requires a CPU with SSE4.2 support.

The following parameters have been removed from the DC/OS installer:

* --set-superuser-password
* --offline
* --cli-telemetry-disabled
* --validate-config
* --preflight
* --install-prereqs
* --deploy
* --postflight
