<!--

Please fill in the applicable sections of this template, remove any default text which is not applicable and provide a cohesive, readable pull request description.

This template has some special rules embedded.

1. Mergebot parses JIRA tickets listed in the title of the PR, in the High-Level Description and Corresponding DC/OS tickets (Required) section. Fix Version field of those JIRA tickets is updated upon merge of this PR.

2. Fix Version field will not be updated for the JIRA tickets listed in Related tickets (optional) section.

3. A comment is added to any JIRA tickets mentioned in the title or description upon merge of this PR.

-->

## High-level description

What features does this change enable? What bugs does this change fix?


## Corresponding DC/OS tickets (required)

  - [D2IQ-ID](https://jira.d2iq.com/browse/D2IQ-ID) JIRA title / short description.


## Related tickets (optional)

<!--

Please keep the header '## Related tickets (Optional)' if you are adding optional tickets.
Fix Version fields of these JIRAs will not be updated.

-->

  - [D2IQ-ID](https://jira.mesosphere.com/browse/D2IQ-<number>) JIRA title / short description.


## Checklist for component/package updates:

If you are changing components or packages in DC/OS (e.g. you are bumping the sha or ref of anything underneath `packages`), then in addition to the above please also include:

  - [ ] Change log from the last version integrated (this should be a link to commits for easy verification and review): [example](https://github.com/dcos/dcos-mesos-modules/compare/f6fa27d7c40f4207ba3bb2274e2cfe79b62a395a...6660b90fbbf69a15ef46d0184e36755881d6a5ae)
  - [ ] Included a test which will fail if code is reverted but test is not. If there is no test please explain.
  - [ ] Test Results: [link to CI job test results for component]
  - [ ] Code Coverage (if available): [link to code coverage report]
  

<!--

## Instructions and review process

**What is the review process and when will my changes land?**

All PRs require approvals from one developer on the most recent commit. Any commits added to the pull request after approval will invalidate the approvals.

Reviewers should be:

* Developers who understand the code being modified.
* Developers responsible for code that interacts with or depends on the code being modified.

It is best to proactively ask for reviews by @mentioning the candidate reviewers in the PR comments area. The responsibility is on the developer submitting the PR to follow-up with reviewers and make sure a PR is reviewed in a timely manner.
Once a PR has **1 approval**, **no red reviews**, and **all tests are green** it will be included in the next Merge Train.

-->
