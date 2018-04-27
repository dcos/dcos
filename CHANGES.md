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

* Enabled Windows-based pkgpanda builds. (DCOS_OSS-1899)

* DC/OS Metrics: moved the prometheus producer from port 9273 to port 61091. (DCOS_OSS-2368)

* Release cosmos v0.6.0. (DCOS_OSS-2195)

* Added a DC/OS API endpoint to distinguish the 'open' and 'enterprise' build variants. (DCOS_OSS-2283)

* A cluster's IP detect script may be changed with a config upgrade (DCOS_OSS-2389)

* DC/OS Net: Support Mesos Windows Agent (DCOS_OSS-2073)

* DC/OS Net: Use Operator HTTP API (DCOS_OSS-1566)

* Admin Router: It is now possible to disable HTTP request buffering for `/service/` endpoint requests through the DCOS_SERVICE_REQUEST_BUFFERING Marathon label

* Admin Router: It is now possible to disable upstream request URL rewriting for `/service/` endpoint requests through the DCOS_SERVICE_REWRITE_REQUEST_URLS Marathon label

### Security Updates

* Update cURL to 7.59. (DCOS_OSS-2367)

* Updated OpenSSL to 1.0.2n. (DCOS_OSS-1903)

* Mesos does not expose ZooKeeper credentials anymore via its state JSON document. (DCOS_OSS-2162)

* TLS: Admin Router should be configured with both RSA and EC type certificates. (DCOS-22050)


### Notable changes

* Updated Metronome to 0.5.0. (DCOS_OSS-2338)

* Updated REX-Ray to v0.11.2. (DCOS_OSS-2245)

* Updated OTP version to 20.3.2 (DCOS_OSS-2378)
