Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 2.0.1 (in development)

* Updated to Mesos [1.9.1-dev](https://github.com/apache/mesos/blob/c31316814398990abf1013bb0681a907426a4fec/CHANGELOG)


### What's new


### Fixed and improved

* dcos-net: task update leads to two DNS zone updates. (DCOS_OSS-5495)

* DC/OS overlay networks should be compared by-value. (DCOS_OSS-5620)

* Drop labels from Lashup's kv_message_queue_overflows_total metric. (DCOS_OSS-5634)
