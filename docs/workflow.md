# DC/OS Development Workflow

        "... there is absolutely nothing "obvious" about source-control systems, or workflows before you already know them"

This document explains the DC/OS development workflow for both Open
Source Mesosphere DC/OS and Closed Source Mesosphere DC/OS Enterprise.

### Introduction

Mesosphere DC/OS has two primary repositories.

1. Open Source Mesosphere DC/OS (https://github.com/dcos/dcos)
2. Closed Source Mesosphere DC/OS Enterprise (https://github.com/mesosphere/dcos-enterprise)
which is a private repository accessible only to Mesosphere employees and partners. The Closed Source Mesosphere DC/OS Enterprise [depends upon the artifact](https://github.com/mesosphere/dcos-enterprise/blob/master/util/build.py) produced by the Open Source DC/OS.

We have designed the DC/OS Pull Request workflow to test Open Source changes along
with the Enterprise consumer, and keep both versions ready for release at any given moment. To keep two
repositories in sync, a bot called `@mesosphere-mergebot` assists the developers with the workflow.

#### DC/OS Branches

The `master` branches of the two repositories represent the in-development version of DC/OS. The branch names that follow the pattern `(<Major-Verion-Number>.<Minor-Version-Number>[.<Patch-Version-Number>]` (For e.g. `1.11` or `1.11.3`) correspond to a supported versions of DC/OS.

Short-lived branches with patch version numbers like `1.11.0` or `1.10.7` are created from the major branches
just before the release. These branches are created after the code-freeze cut-off date for the planned release.

A feature targeted for the upcoming version of DC/OS should go into `master` branch.
Bug fixes must be ported to all the active branches of DC/OS where the bug is present.

#### Pull Request lifecycle.

Contribution to DC/OS starts with a Github Pull Request either against both `dcos/dcos` and `mesosphere/dcos-enterprise` repositories, or only against `mesosphere/dcos-enterprise` repository if it is an Enterprise only change. We use Github labels to indicate the state of a Pull Request.

**1. Work In Progress state.**

When a Pull Request is created against any DC/OS repo, a **Work In Progress** label is applied
to it. This indicates that the Pull Request is not complete and is not ready for review yet.

**2. Associating an Enterprise Pull Request.**

If the Pull Request was created against Open Source Mesosphere DC/OS, the `dcos/dcos` repository, an Enterprise reference Pull Request is required.

The Pull Request creator or a Mesosphere Developer can invoke `@mesosphere-mergebot` with a comment on an
Open Source Pull Request to create an Enterprise Pull Request that will test the current Open Pull Request.

```
@mesosphere-mergebot bump-ee
```

This will create a pull request against `mesosphere/dcos-enterprise`
and provide a link to the Pull Request in the comments.

a. Enterprise additions, if required, must utilize the branch created by the **bump-ee** command.

For e.g, if the Pull Request created has a branch like `mergebot/dcos/1.11/42`, then developers
need to clone the Pull Request branch locally, and add the Enterprise changes to that branch.

```
git clone git@github.com:mesosphere/dcos-enterprise.git
git pull origin
git checkout -b mergebot/dcos/1.11/2909 origin/mergebot/dcos/1.11/42
# make your changes to this branch
git push origin mergebot/dcos/1.11/42
```

**3. Ready For Review**

When a Pull Request is ready for review, the Pull Request creator can comment on the Pull Request
requesting `@mesosphere-mergebot` to move the pull request to the next state called **Ready for Review**.

```
@mesosphere-mergebot label ready for review
```

* This must be done on both Open Source Pull Request and the Enterprise Pull Request.

* When a Pull Request is set to **"Ready for Review"** state, `@mesosphere-mergebot` will start monitoring
the Pull Request. It will start monitoring for comments, and status checks on the Pull Request.

* When all the required status checks against a Pull Request is successful,
`@mesosphere-mergebot` will apply a **"Ship It"** label and move the Pull Request to the next state.

* When there is no activity observed on a **"Ready For Review"** Pull Request
for 3 days, `@mesosphere-mergebot` will comment on the lack of activity.

**4. Ship it**

When the Pull Request in **Ready For Review** state meets all the required criteria encoded in the required
status checks, it is automatically moved to a next state by applying a "Ship It" label. A "Ship It"
label indicates that the pull request is ready for inclusion in the next [merge train](#merge-train).

#### Review Process and Expectations

The Pull Request creator can request for review from other developers who can validate and authorize the contents of the Pull Request.

* Mergebot requires two approvals at the last commit of the Pull Request, i.e, at the HEAD sha of the branch,
  and two approvals at the enterprise Pull Request that points to the last commit of the open Pull Request.

* Mergebot requires No changes-requested pending, and if changes were requested by a reviewer, an approval
 is required from the same reviewer after the changes requested comment is addressed by the Pull Request creator.

This means, during review, the Pull Request creator has to follow this process repeatedly.

    While (new-changes-pushed)

        1. @mesosphere-mergebot bump-ee
            # bump-ee will require to update the branch, if the target branch has new changes.
            # Pull Request creator will have to merge from target branch if the target branch had moved.

        2. Get two approvals again since the previous approvals are now invalid.

        3. Ensure if any changes were requested (by Red X mark), after addressing the request, get an approval from the
        developer who requested those changes

#### Failed status checks.

If there is a failure observed in the Pull Request, Pull Request creator is  responsible for triaging, and fix the failure.

If the status check failure is not related to the change being introduced, `dcos-owners`
can help to override the failure, and satisfy the status check requirement.


```
@mesosphere-mergebot override-status status-check-name JIRA-WHICH-IS-NOT-CLOSED
```

### Merge Train

In order to avoid frequent rebasing, and to safely merge all the PRs that are ready in both open source
and enterprise repos, `@mesosphere-mergebot` creates an integration train with "Ship It" labelled PRs.
The integration pull request is created on weekdays at 12:00 for all the active branches of DC/OS.

#### Merge

A train Pull Request can be merged by developers who are in the [dcos-owners](https://github.com/dcos/dcos/blob/master/owners.json) file.
The train Pull Request with all status checks can be merged using the command.

```
@mesosphere-mergebot merge-it
```

* `@mesosphere-mergebot` verifies that all status checks are satisfied for both Open and Enterprise
PR. If there is any status check which is not satisfied, mergebot will refuse to merge the PR.
