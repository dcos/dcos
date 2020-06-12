Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 2.2.0-dev (in development)

* Updated to Mesos [1.11.0-dev](https://github.com/apache/mesos/blob/3d68993c8743231b6067738050786e750edda9b1/CHANGELOG)


### Security updates


### Notable changes


### Fixed and improved

* Storing etcd initial state on `/var/lib/dcos` instead of `/run/dcos` [COPS-6183](https://jira.d2iq.com/browse/COPS-6183)
* Updated DC/OS UI to [v5.0.55](https://github.com/dcos/dcos-ui/releases/tag/v5.0.55).

* Removed Exhibitor snapshot cleanup and now rely on ZooKeeper autopurge. (D2IQ-68109)
