<h2>Patches to cherry-pick on top of open source Apache Mesos before building in DC/OS</h2>

These commits can be found in the repository at <a href="https://github.com/mesosphere/mesos/">https://github.com/mesosphere/mesos/</a>:

<li>[20e5654a294f599b637efadf32206e7b15398081] Set LIBPROCESS_IP into docker container.
<li>[098743933a99925cfccb19f132393fa9f236c31e] Mesos UI: Change paths, pailer, and logs to work with a reverse proxy.
<li>[f01e1ecc7ee9e9879d7059f8862a389f9f9c25c6] Revert "Fixed the broken metrics information of master in WebUI."
<li>[17979fea307b7c094c2bac8e5a3f25af33208a0c] Updated mesos containerizer to ignore GPU isolator creation failure.

<h2>Patches to cherry-pick on top of Mesos 1.4.0 only</h2>
<li>[2f3a182d91952f0db30883acda0ef222affa6477] Included nested command check output in the executor logs.
<li>[86ee162326172bffcf7f264c5e46ce3d155c1636] Made the log output handling of TCP and HTTP checks consistent.
<li>[b0fd885dbf02a61b5635184df19905695b4bba96] Raised the logging level of some check and health check messages.
