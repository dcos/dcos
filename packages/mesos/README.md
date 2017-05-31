<H2>Patches to cherry-pick on top of open source Apache Mesos before building in DC/OS</h2>
These commits can be found in the repository at <a href="https://github.com/mesosphere/mesos/">https://github.com/mesosphere/mesos/</a>:
<li>[3d64f669c5e34162844345a6a923e7b3cdb79a4td] Set LIBPROCESS_IP into docker container.
<li>[03e8c27aa5ad6bf6e4f15b781f126d274ec41d7f] Changed agent_host to expect a relative path.
<li>[44eec8e7935d6de83afe80f22bdd4fd979b63fc7] Mesos UI: Change paths, pailer, and logs to work with a reverse proxy.
<li>[dbd3bc2947efe0a1f66bb645f6bc48c154a9f130] Revert "Fixed the broken metrics information of master in WebUI."
<li>[9cc627d9f32d56f14f277e823a759183ef4b234d] Updated mesos containerizer to ignore GPU isolator creation failure.
<li>[f2b490010136c4eb8e2e3055a2549d6cbf3429ac] Added '--filter_gpu_resources' flag to the mesos master.
