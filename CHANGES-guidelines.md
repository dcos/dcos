Major releases (e.g. 1.13.0) are treated different from patch releases (e.g. 1.13.3). We would like to focus on building up complete and correct changelog content especially for patch releases. 

## Patch releases

**Any user-facing change** between two patch releases must be reflected in `CHANGES.md`, in one of three sections:

* _Security updates_
* _Notable changes_
* _Fixed and improved_

### How to choose the section 

* If the change fixes a security issue, and for this reason it is strongly recommended to stop using earlier versions of this release, then the change must go in the _Security updates_ section.
* If the change modifies the installation procedure or adds a new DC/OS install-time configuration option then the change must go in the _Notable changes_ section ([example](https://github.com/dcos/dcos/blame/ba77808952a9db03cd75db0631ca42921390ca06/CHANGES.md#L18)).
* If the change updates a component with externally maintained release notes then the change must go in the _Notable changes_ section. In particular, when updating Mesos, Marathon, or the DC/OS UI please add a line of the format `Updated to [Mesos 1.5.1-dev](public-link-to-changelog-or-release-notes)` or update the existing line. This is also the method to choose when updating third-party components such as ZooKeeper, linking to external release notes.
* If the change provides a new capability to DC/OS then the change must go in the _Notable changes_ section.
* Other externally visible changes go in the _Fixed and improved_ section.
* Changes that are not externally visible do not need to go in the `CHANGES.md` file. Examples include changes that only modify repository configuration and tests, or code changes that do not change external behavior.

### Format

Individual entries must be separated by two newline characters, so that the Markdown source shows an empty line between entries:
```
* Entry with no newline characters. (DCOS_OSS_JIRA)
<empty-line>
* Another entry with no newline characters. (DCOS_OSS_JIRA_2)
```

Add new entries to the top of the existing content within a section. Each entry should be a proper English sentence, reflecting the change in easily comprehensible terms using the past tense. A JIRA ticket ID, if applicable, should be provided side-by-side with the entry as shown above.

If the entry describes a bug fix in response to a customer operations (COPS) ticket then please also add the corresponding COPS ticket ID.

## Major releases

For major releases (e.g. development towards 1.14.0) we would like to optimize for documenting 
* breaking changes compared to the previous major release branch
* major additions / features / improvements

That is why there are only two sections to be filled, _Breaking changes_ and _What's new_.

In case of a bug fix forward port into the development version of the next major release there is no need to mention this in the changelog of the major release. Example: a bug is fixed for the upcoming 1.12.3 release while 1.13.0 is still in development. As of common sense the same bug fix gets forward-ported into 1.13.0-dev. That very forward-port does not need to be accompanied by a changelog entry. It's _expected_ behavior for this bug fix to be included in 1.13.0. If it's not, it's a bug in itself and will be fixed with with a future 1.13.x release, accompanied with a relevant changelog entry.

## Markdown templates

This section is meant to be consumed by DC/OS maintainers.

This snippet is the source of truth for the `CHANGES.md` modification which must happen upon a *minor branch switch* (e.g. where `2.0.0` is branched off from the `2.0` branch, so that the `2.0` branch now reflects `2.0.1` development). In particular, it shows the desired state of `CHANGES.md` in the source branch upon branch switch: it shows how a new `in development` section is to be added, including subsections. 

```
## DC/OS 2.0.1 (in development)


### Security updates


### Notable changes


### Fixed and improved



## DC/OS 2.0.0 (2019-10-17)


### What's new

- A dummy entry. (D2IQ-13337)

### Breaking changes

- A dummy entry. (D2IQ-13338)
```
