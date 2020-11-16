Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 2.3.0-dev (in development)


### Security updates


### Notable changes


### Fixed and improved

* Update DC/OS UI to [v6.1.19](https://github.com/dcos/dcos-ui/releases/tag/v6.1.19)

* Fixed dcos-net startup script to configure network ignore file for on-prem (D2IQ-73113).

* etcd is now disabled when calico is disabled via `calico_enable` (D2IQ-73299).

#### Update Marathon to 1.11.24

* Don't respect instances that are about to be restarted in placement constraints. (MARATHON-8771)
