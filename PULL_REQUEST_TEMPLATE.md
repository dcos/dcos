## High-level description

<!-- This template uses HTML comments for providing guidance. They are not visible in the PR output -->


What features does this change enable? What bugs does this change fix?


## Corresponding DC/OS tickets (required)

<!--

Please provide a list of JIRA tickets that this Pull Request acts upon. This section will be parsed, 
a comment will be added, and the FixVersion field of the JIRA will be set to DC/OS release version upon merged.
The FixVersion will correspond to the [fix_version_map](https://github.com/dcos/dcos/blob/master/mergebot-config.json#L30) 
of the mergebot-config.

These DC/OS JIRA ticket(s) must be updated, in the moment this PR lands. 

-->

  - [DCOS-ID](https://jira.mesosphere.com/browse/DCOS-<number>) JIRA title / short description.


## Related tickets (optional)

<!--

Other tickets related to this change. The JIRAs mentioned in this section will not be parsed, no comments be will added,
FixVersion will not be updated.

Please keep the header '## Related tickets (Optional)' if you are adding optional tickets. Information below this header 
will excluded from Mergebot parsing behavior for JIRA comment updates and fix version.

-->

  - [DCOS-ID](https://jira.mesosphere.com/browse/DCOS-<number>) JIRA title / short description.


## Checklist for component/package updates:

If you are changing components or packages in DC/OS (e.g. you are bumping the sha or ref of anything underneath `packages`), then in addition to the above please also include:

  - [ ] Change log from the last version integrated (this should be a link to commits for easy verification and review): [example](https://github.com/dcos/dcos-mesos-modules/compare/f6fa27d7c40f4207ba3bb2274e2cfe79b62a395a...6660b90fbbf69a15ef46d0184e36755881d6a5ae)
  - [ ] Test Results: [link to CI job test results for component]
  - [ ] Code Coverage (if available): [link to code coverage report]
  

<!--

**PLEASE FILL IN THE TEMPLATE ABOVE** / **DO NOT REMOVE ANY SECTIONS ABOVE THIS LINE**


## Instructions and review process

**What is the review process and when will my changes land?**

All PRs require 2 approvals using GitHub's pull request reviews. 

Reviewers should be:

* Developers who understand the code being modified.
* Developers responsible for code that interacts with or depends on the code being modified.

It is best to proactively ask for 2 reviews by @mentioning the candidate reviewers in the PR comments area. The responsibility is on the developer submitting the PR to follow-up with reviewers and make sure a PR is reviewed in a timely manner. 
Once a PR has **2 ship-it's**, **no red reviews**, and **all tests are green** it will be included in the next Merge Train.

-->
