# PR Reviews

There are two different kinds of PRs: code / individual change PRs and trains. Individual PRs are pulled into a train, where they are tested together, bad / conflicting prs can be kicked off the train, then the whole train lands at once. Ocassionally an individual train is merged wihtout a train, but most the time trains are used to make it so everything doesn't have to be rebased all the time to guarantee it all actually works together.

## General PR Reviews (WIP)

WIP list of Things to Verify:
1. all tests are passing (things with non-passing tests won't get reviewed, if a author requests will do basic comment path about the general direction or helping fix why tests don't pass)
2. Code is pythonic
3. Doesn't introduce a lot of complexity / is as simple as possible
4. All systemd changes follow [Systemd Rules](systemd-rules.md)
5. All package changes follow [Package Rules](package-rules.md)


## Merge Train PR Reviews

Things to verify
1. All the PRs referenced have :ship: from me / seb / albert / jeremy after the last change
2. The github message includes all the PRs
3. a quick high level review that there isn't anything i don't expect in there
