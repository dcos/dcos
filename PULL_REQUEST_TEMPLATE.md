## High Level Description

What features does this change enable? What bugs does this change fix? High-Level description of how things changed.

## Related Issues

  - [DCOS-<number>](https://dcosjira.atlassian.net/browse/DCOS-<number>) Foo the Bar so it stops Bazzing.
  - [DCOS-<number>](https://mesosphere.atlassian.net/browse/DCOS-<number) TRACKING: dcosjira-123 Foo the Bar

## Checklist for all PR's

  - [ ] Included a test which will fail if code is reverted but test is not. If there is no test please explain here:
  - [ ] Read the [DC/OS contributing guidelines](https://github.com/dcos/dcos/blob/master/contributing.md)
  - [ ] Followed relevant code rules [Rules for Packages and Systemd](https://github.com/dcos/dcos/tree/master/docs)

## Checklist for component/package updates:

If you are changing components or packages in DC/OS (e.g. you are bumping the sha or ref of anything underneath `packages`), then in addition to the above please also include:

  - [ ] Change log from the last version integrated (this should be a link to commits for easy verification and review): [example](https://github.com/dcos/dcos-mesos-modules/compare/f6fa27d7c40f4207ba3bb2274e2cfe79b62a395a...6660b90fbbf69a15ef46d0184e36755881d6a5ae)
  - [ ] Test Results: [link to CI job test results for component]
  - [ ] Code Coverage (if available): [link to code coverage report]
___
**PLEASE FILL IN THE TEMPLATE ABOVE** / **DO NOT REMOVE ANY SECTIONS ABOVE THIS LINE**

## Instructions and Review Process

**What is the review process and when will my changes land?**

All PRs require 2 approvals using github's [pull request reviews](https://help.github.com/articles/about-pull-request-reviews/).

Reviewers should be:
* Developers who understand the code being modified.
* Developers responsible for code that interacts with or depends on the code being modified.

It is best to proactively ask for 2 reviews by @mentioning the candidate reviewers in the PR comments area. The responsibility is on the developer submitting the PR to follow-up with reviewers and make sure a PR is reviewed in a timely manner. Once a PR has **2 ship-it's**, **no red reviews**, and **all tests are green** it will be included in the [next train](https://github.com/dcos/dcos/blob/master/contributing.md).
