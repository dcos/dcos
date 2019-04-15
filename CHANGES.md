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

* The configuration parameter `aws_secret_access_key` for exhibitor is now marked as secret and will thus not be revealed in `user.config.yaml` on cluster nodes but will from now on appear only in `user.config.full.yaml` which has stricter read permissions and is not included in DC/OS Diagnostics bundles. (DCOS-51751)
