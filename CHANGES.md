Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 2.2.0-dev (in development)

* Updated to Mesos [1.11.0-dev](https://github.com/apache/mesos/blob/2bf7f5d8dcb359845a663a011a941809ffc2366d/CHANGELOG)

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
