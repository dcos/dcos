# DC/OS Development Workflow


        "... there is absolutely nothing "obvious" about source-control systems, or workflows before you already know them"

Mesosphere DC/OS has two primary repositories.

1. Open Source DC/OS (https://github.com/dcos/dcos)
2. Closed Source Mesosphere Enterprise DC/OS (https://github.com/mesosphere/dcos-enterprise)

In our design, the closed source Mesosphere Enterprise DC/OS depends on the Open Source DC/OS, [builds on top of the artifact](https://github.com/mesosphere/dcos-enterprise/blob/master/util/build.py) from the Open source DC/OS.

We have designed our DC/OS pull request workflow, in such a way,  we test our Open Source changes
with the Enterprise consumer,  we keep both versions ready for release at any moment in time.
It can be cumbersome, and error-prone to deal with two version control systems at the same time.
A friendly bot called `@mesosphere-mergebot` comes to our rescue and helps the developers with the process.

#### How do I contribute a change to dcos/dcos ?

If a change is only to Enterprise DC/OS, the developer should create the pull request against the Enterprise Repository.

For all contributions, a pull request is against Open Source DC/OS and tested with both Open and
Enterprise, and we merge the Open Source pull request, and update the reference in Enterprise.

#### What should be my target branch?

All Pull Requests should be against `master` branch, and the bug-fixes should be actively backported to the
supported versions of DC/OS. The dcos/dcos repo will have the list of actively supported branches, and developers
should create the back-port pull requests if they have to include the change in the particular version DC/OS.

#### What should I do after I create a pull request against DC/OS?

We use labels, to set the status of a pull-request. All pull requests start at "Work In
Progress" state. The pull request creator can continue working on this until he/she is ready.

When a pull request is ready for review, the pull request creator is expected to run this command.

```
@mesosphere-mergebot label ready for review
```

The above command will set the label of the PR to "Ready For Review" and it is crucial,
as it will now fall under the radar of Mergebot to monitor for status updates to the PR.

And also, do update to Enterprise reference using the command:

```
@mesosphere-mergebot bump-ee
```

The will create a Pull Request against the dcos-enterprise repository and share a link to the pull-request in the github comments.

a. If your changes require Enterprise only addition, you are expected to update the pull request thus created, with your changes.
If the pull request created has a branch like `mergebot/dcos/1.11/42`

```
git clone git@github.com:mesosphere/dcos-enterprise.git
git pull origin
git checkout -b mergebot/dcos/1.11/2909 origin/mergebot/dcos/1.11/42
# make your changes to this branch
git push origin mergebot/dcos/1.11/42
```

b. If you are an open source contributor, no EE contributions is required; the Bump-EE PR only
   serves to test and update the reference to the SHA, when your open source contribution is merged.

To re-iterate, with every PR, when it ready for review, developers have to do these two steps

```
1. @mesosphere-mergebot label ready for review
```

and

```
2. @mesosphere-mergebot bump-ee
```

#### How do I get my reviews for my pull request?

We @mention people the comments on the Pull Request, to get their attention to review a pull request.

Open source contributors can expect that the committers are watching the repo,
and they will @mention the correct reviewer or will review the PR by themselves.

TODO (skumaran) : DCOS_OSS-1906 - Github CODEOWNERS for dcos/dcos

We expect two approvals at the last commit of your PR (HEAD of your branch), and
two approvals at the enterprise PR that points to the last commit of your open PR.

There should also be no changes-requested pending during the entire review, and if changes are requested
by a reviewer, an approval IS required after the developer has addressed the changes requested in his code or pull request.


That means, for every comment that you address, and "push to the repo" to update your pull request.

You will have do to

    While (new-changes-pushed == True)

        1. @mesosphere-mergebot bump-ee
            # bump-ee will require you update your branch, if the target branch has new changes.
            # You will have to merge from target branch if the target branch had moved.

        2. And get two approvals again since the previous approvals are now invalid.

        3. Ensure if any changes were requested (by Red X mark), after addressing the request, get an approval from the
        developer requested those changes


We have status checks encoded in PRs, to ensure that this is taken care,
and the status checks should inform you if you are missing of these steps.

#### What are the other status checks?

Every PR triggers a chain of tests that will verify the quality of your change. We run integration tests
against various platforms that we support and ensure that the change that you are bringing in is "safe" to merge.

#### What happens when the status checks are successful?

It is an indicator that your PR is safe to merge, and mesosphere-mergebot applies a "Ship It" label to those PRs.

#### When does my PR get's merged, then?

Remember, we are dealing with two repos? To safely merge all the PRs that are ready in both open
source and enterprise repos, we need to create an integration train with all those "Ship It" labelled PRs.

Mergebot automatically creates the train integration branch and PR, and it does it every weekday at 12:00 UTC.
The Train integration PR is a autogenerated PR, which will include the individual "Ship-it" labelled PRs, will be
tested as a batch against the HEAD of the target branch, and merged.

#### Who are the committers, who can merge the PR?

We have concept of owners, called [dcos-owners](https://github.com/dcos/dcos/blob/1.11/owners.json) listed in this file.

They can issue a command like

```
@mesosphere-mergebot merge-it
```

to a PR that is ready, and this will merge the Open PR, update the reference
of Enterprise to the open merge commit, and merge the enterprise PR.

#### What if a status check failed?

If the status check failed due to a problem introduced by your change, you are responsible for fixing it.

If the status check failure is not related to your change, please involve `dcos-owners` by @mentioning them in
the PR. They can review the PR, review the failure, and can unblock you by doing an override of that status check

```
@mesosphere-mergebot override-status <status-check> JIRA-WHICH-IS-NOT-CLOSED
```

#### What do I do if I suspect there is a mergebot problem in the above process?

Please ping `#tools-infra` channel for support.


## dcos-owners

DC/OS has a concept of [dcos-owners](https://github.com/dcos/dcos/blob/1.11/owners.json), who
are the stewards for changes going into DC/OS, and have privileges to merge the pull requests.


* Owners have the ability to merge using `@mesosphere-mergebot merge-it` command.

* Owners have the ability to override a failure in a pull request status check. This can
  be utilized when we have get un-blocked due a flaky test or a infrastructure problem.

* Owners have a responsibility to review the automated train PRs, and help
  developers with review for PRs against dcos/dcos, mesosphere/dcos-enterprise.

* Owners also have the ability to manually add "ship-it" label to a PR to include it a merge train. This can
  be utilized for non-code PRs, like README or documentation changes after the review process is complete.
