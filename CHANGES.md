## DC/OS 1.14.0

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

### Highlights

#### What's new

#### Breaking changes

#### Known limitations

#### Fixed and improved

* DC/OS Diagnostics now applies timeouts when reading systemd journal entries. The timeout that's applied is configured via the `command-exec-timeout` configuration parameter.
* `docker-gc` now removes unused volumes (DCOS_OSS-1502)

* Use gzip compression for some UI assets (DCOS-5978)
