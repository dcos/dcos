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

* Windows-based pkgpanda builds (DCOS_OSS-1899)

* Upgrade REX-Ray to v0.11.2. (DCOS_OSS-2245)

* Moves the dcos-metrics Prometheus producer from port 9273 to port 61091. Using a port which is not available to Mesos (any unoccupied port > 61000) avoids the need to update anything. (DCOS-21594)

* Update Metronome to 0.5.0 (DCOS_OSS-2338)

### Security Updates

* Bump curl from 7.48 to 7.59 (DCOS-21557)

* Update openssl to 1.0.2n (DCOS_OSS-1903)

### Mesos Changelog

* Bumps mesos modules enabling file based ZK configuration (DCOS_OSS-2162)

### Marathon Changelog




