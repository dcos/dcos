# Contributing

 - Pull Requests (PR) for small fixes / typos / etc. are very welcome, just make a PR with the fix and it should land quickly.
 - If a PR check fails on your PR, most of the CI logs are open and viewable without an account (login as guest using the button on the login screen). If you can't see it, ask in DC/OS community or the PR and someone will forward the needed information.
 - PRs will get reviewed independently, then landed in groups called "trains". This makes it so we don't have to endlessly rebase PRs in master. Trains depart regularly, so don't worry about missing one. It'll get in.
 - [PR labels](docs/github-pr-labels.md) are used to track the status of a PR. New PRs which have tests failing will generally get a "Work in Progress" label. Ones with all tests passing will get a first label of "Ready for Review"
 - For bigger PRs / changes where you want to get feedback from the CI system before it gets reviewed, make the PR and put `WIP` in the title. When you're ready for review or want comments abou the approach, just ask in the comment thread on the PR.
 - For big changes, it's good to get some feedback before commiting a lot of time to working on building something. This is best done via the mailing list for inital questions / proposal, and DCOSJIRA for actually tracking the tasks / proposals over time.
 - There are more detailed rules around different things like [reliable usage of systemd](docs/systemd-rules.md), [adding packages](docs/package-rules.md), and updating packages (see below). More things have rules around them, just open up a PR and comments / review will let you know what all needs to happen (And a doc might get written that can be pointed to next time). Even better than a doc is tools which enforce things. These are steadily growing.


## Package Update Guidelines / Requirements
 - Overview of the changes being included
 - Link to the code changes / commits / PRs included in the change
 - Link to the build that made the artifact being updated (or upstream release page)
 - Link to Unit Test Results, Code Coverage, etc of the project. Things that give confidence bumping this component version won't create unexpected instability.
 - Snippets for the Docs / Release Notes about major
