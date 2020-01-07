Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 2.0.1 (in development)

* Updated to Mesos [1.9.1-dev](https://github.com/apache/mesos/blob/4575c9b452c25f64e6c6cc3eddc12ed3b1f8538b/CHANGELOG)


### What's new


### Fixed and improved

* Marathon: the upgrade to DC/OS 2.0 would fail if Marathon had undergoing a deployment during the upgrade (MARATHON-8712)

* Marathon: Pod statuses could fail to report properly with unlaunched resident pods are scaled down (MARATHON-8711)

* dcos-net: task update leads to two DNS zone updates. (DCOS_OSS-5495)

* DC/OS overlay networks should be compared by-value. (DCOS_OSS-5620)

* Drop labels from Lashup's kv_message_queue_overflows_total metric. (DCOS_OSS-5634)

* Reserve all agent VTEP IPs upon recovering from replicated log. (DCOS_OSS-5626)

* Set network interfaces as unmanaged for networkd only on coreos. (DCOS-60956)

* Mesos: support quoted realms in WWW-Authenticate headers. (DCOS-61529)

* Build Admin Router without SSE4.2 instructions to work on older CPUs. (DCOS_OSS-5643)

* Update Java to version 8u232. This was mistakenly downgraded during the switch to OpenJDK. (DCOS-62548)
