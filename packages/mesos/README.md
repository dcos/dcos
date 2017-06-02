<H2>Patches to cherry-pick on top of open source Apache Mesos before building in DC/OS</h2>
These commits can be found in the repository at <a href="https://github.com/mesosphere/mesos/">https://github.com/mesosphere/mesos/</a>:
<li>[742df849b15c328edc555a8852d633524062b117] Set LIBPROCESS_IP into docker container.
<li>[f3d57cb43c2d56391527d61ac954154d906b1707] Changed agent_host to expect a relative path.
<li>[601f3b2810442c09d8b509cf9f50ad7d216f1351] Mesos UI: Change paths, pailer, and logs to work with a reverse proxy.
<li>[960aec18ad2689d5b64b1fd062683e4274a0ba6d] Revert "Fixed the broken metrics information of master in WebUI."
<li>[13783195d6ea8e34f528022cd13a5dba4bd32c62] Updated mesos containerizer to ignore GPU isolator creation failure.
<li>[c0a93bec85707de09f3618dc9f5009f099186804] Updated the UI to fix maintenance in DC/OS.
<li>[f219b2e4f6265c0b6c4d826a390b67fe9d5e1097] Added '--filter_gpu_resources' flag to the mesos master.
