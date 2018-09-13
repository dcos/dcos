<h2>Mesos Patches</h2>

We need to apply some patches on top of upstream Apache Mesos before building in
DC/OS.  The patches are stored in the [extra/patches] directory and applied as part of [build] script.

Here are the instructions to add/remove/update one or more patches:
* Checkout the upstream Mesos SHA.
* Apply all the cherry-picks that you need.
* Create patch files using `git format-patch -N <upstream-SHA>`
* Replace existing files in [extra/patches] with the new patch files.
