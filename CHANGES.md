Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 2.2.1 (in development)

### Security updates

### Notable changes

### Fixed and improved

* Update DC/OS UI to [6.1.19](https://github.com/dcos/dcos-ui/releases/tag/6.1.19)

## DC/OS 2.2.0 (29-10-2020)

* Updated to Mesos [1.11.0-dev](https://github.com/apache/mesos/blob/cb6cfe9b122d1b60a8264b28b6abb38a3c8417b4/CHANGELOG)

* Update to Fluentbit [1.4.6](https://docs.fluentbit.io/manual/installation/upgrade-notes)

* Remove DC/OS Signal [D2IQ-69818](https://jira.d2iq.com/browse/D2IQ-69818)


### Security updates


### Notable changes

* Upgraded to CockroachDB 19.1 (D2IQ-69872)

* Metronome jobs now supports dependencies

### Fixed and improved

* Updated `etcd` to [v3.4.9](https://github.com/etcd-io/etcd/releases/tag/v3.4.9).

* Allow disabling Calico overlay by setting `calico_enabled` to `false`. (COPS-6451)

* Fixing some corner-cases that could render `etcd` unable to start [D2IQ-69069](https://jira.d2iq.com/browse/D2IQ-69069)

* Storing etcd initial state on `/var/lib/dcos` instead of `/run/dcos` [COPS-6183](https://jira.d2iq.com/browse/COPS-6183)

* Update DC/OS UI to [v6.1.16](https://github.com/dcos/dcos-ui/releases/tag/v6.1.16).

* Removed Exhibitor snapshot cleanup and now rely on ZooKeeper autopurge. (D2IQ-68109)

* Ensured that marathon and SDK labeled reservations are not offered to other schedulers (D2IQ-68800)

* Updated OpenResty to 1.15.8.4. (DCOS_OSS-5967)

* Update Telegraf configuration to reduce errors, vary requests to reduce load, sample less frequently. (COPS-5629)

* Update Bouncer dependencies. (D2IQ-54115, D2IQ-62221)

* Updated Exhibitor to version running atop [Jetty 9.4.30](https://github.com/dcos/exhibitor/commit/e6e232e1)

* Ensure Docker network for Calico is eventually created correctly following failures. (D2IQ-70674)

* Check that `spartan` ips (`198.51.100.1-3`) are not listed as upstream resolvers. (COPS-4616)

* Log diff to resolv.conf in addition to the new contents. (COPS-6411)

* Turn on `enable_docker_gc` for on-prem by default. (COPS-5520)

* Stop all services at once during upgrade. (COPS-6512)

* Sequence service start-up to avoid timeouts in CockroachDB unit start. (D2IQ-62292)

* dcos-net now configures NetworkManager ignores for its interfaces (COPS-6519)

#### Marathon updated to 1.11.23

* Marathon apps have support for CSI volumes. (MARATHON-8765) (MARATHON-8767)

* Resource limits are now properly read from persistence (MARATHON-8773)

* Enforce-role property no longer shows for sub-groups (MARATHON-8769)

* Fix issue in which PUT /v2/groups ignored the enforceRole setting (MARATHON-8770)

* Marathon can send offer constraints to Mesos to reduce the number of offers it needs to decline due to placement constraints (MARATHON-8764)

* Marathon will allow GROUP_BY placement constraints to be temporarily imbalanced during deployments. (MARATHON-8752)

* Marathon no longer logs task data, as it may contain secrets for Docker containers. (MARATHON-8774)
