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


### Security Updates

* Update cURL to 7.59. (DCOS_OSS-2367)

* Updated OpenSSL to 1.0.2n. (DCOS_OSS-1903)

* Mesos does not expose ZooKeeper credentials anymore via its state JSON document. (DCOS_OSS-2162)


### Notable changes

* Updated Metronome to 0.5.0. (DCOS_OSS-2338)

* Updated REX-Ray to v0.11.2. (DCOS_OSS-2245)

