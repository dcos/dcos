# Generates setup / config files for DC/OS

Generates the files which need to be put on individual hosts in order to install DC/OS with the given configuration, with platform / combo specific quirks.

## Debugging a cluster / watching it come up
```
ssh into the desired node
Watch using the journal `journalctl -f`

Things are more or less up when the nginx starts / finds leader.mesos. Should take 15 minutes or less.
