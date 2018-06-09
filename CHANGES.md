## DC/OS 1.12.0

```
* For any significant improvement to DC/OS add an entry to Fixed and Improved section.
* For Security updates, please call out in Security updates section.
* Add to the top of the existing list.
* External Projects like Mesos and Marathon shall provide a link to their published changelogs.

Format of the entries must be.

* Entry with no-newlines. (DCOS_OSS_JIRA)
<new-line>
* Entry two with no-newlines. (DCOS_OSS_JIRA_2)
```


### Fixed and improved

* Increased the timeout for the `mesos_agent_registered_with_masters` check. (DCOS_OSS-2277)

* Enabled Windows-based pkgpanda builds. (DCOS_OSS-1899)

* DC/OS Metrics: moved the prometheus producer from port 9273 to port 61091. (DCOS_OSS-2368)

* Release cosmos v0.6.0. (DCOS_OSS-2195)

* Added a DC/OS API endpoint to distinguish the 'open' and 'enterprise' build variants. (DCOS_OSS-2283)

* A cluster's IP detect script may be changed with a config upgrade (DCOS_OSS-2389)

* DC/OS Net: Support Mesos Windows Agent (DCOS_OSS-2073)

* DC/OS Net: Use Operator HTTP API (DCOS_OSS-1566)

* Admin Router: It is now possible to disable HTTP request buffering for `/service/` endpoint requests through the DCOS_SERVICE_REQUEST_BUFFERING Marathon label. (DCOS_OSS-2420)

* Admin Router: It is now possible to disable upstream request URL rewriting for `/service/` endpoint requests through the DCOS_SERVICE_REWRITE_REQUEST_URLS Marathon label. (DCOS_OSS-2420)


### Security Updates

* Update cURL to 7.59. (DCOS_OSS-2367)

* Updated OpenSSL to 1.0.2n. (DCOS_OSS-1903)

* Mesos does not expose ZooKeeper credentials anymore via its state JSON document. (DCOS_OSS-2162)

* TLS: Admin Router should be configured with both RSA and EC type certificates. (DCOS-22050)

* Disable the 3DES bulk encryption algorithm for Master Admin Router's TLS. (DCOS-21958)

* Disable the TLS 1.1 protocol for Master Admin Router's TLS. (DCOS-22326)


### Notable changes

* Removed the DC/OS web installer. (DCOS_OSS-2256)

* Updated Metronome to 0.5.0. (DCOS_OSS-2338)

* Updated OTP version to 20.3.2 (DCOS_OSS-2378)
