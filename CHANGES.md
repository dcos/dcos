Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 2.2.0-dev (in development)

* Updated to Mesos [1.11.0-dev](https://github.com/apache/mesos/blob/a679eb4bc35bd2d7c4cffdd9440ab301d8fc8986/CHANGELOG)


### Security updates


### Notable changes


### Fixed and improved

* Fixing some corner-cases that could render `etcd` unable to start [D2IQ-69069](https://jira.d2iq.com/browse/D2IQ-69069)

* Storing etcd initial state on `/var/lib/dcos` instead of `/run/dcos` [COPS-6183](https://jira.d2iq.com/browse/COPS-6183)

* Updated DC/OS UI to [v5.1.1](https://github.com/dcos/dcos-ui/releases/tag/v5.1.1).

* Removed Exhibitor snapshot cleanup and now rely on ZooKeeper autopurge. (D2IQ-68109)

* Ensured that marathon and SDK labeled reservations are not offered to other schedulers (D2IQ-68800)

* Updated OpenResty to 1.15.8.4. (DCOS_OSS-5967)
