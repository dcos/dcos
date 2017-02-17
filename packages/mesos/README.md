<H2>Patches to cherry-pick on top of open source Apache Mesos before building in DC/OS</h2>
These commits can be found in the repository at <a href="https://github.com/mesosphere/mesos/">https://github.com/mesosphere/mesos/</a>:
<li>[42e4e19d0d7e54d5e361e1dd2d6afbd24d1928d1] Set LIBPROCESS_IP into docker container.
<li>[09975e642168a47c466e211f02a590b6e3e1e40c] Changed agent_host to expect a relative path.
<li>[d2cf9ac1dfa0d7d2b5ebcf8f9da86190706bb5cd] Mesos UI: Change paths, pailer, and logs to work with a reverse proxy.
<li>[3d042bae0431da237d2c109525ea81fe8eb9943c] Revert "Fixed the broken metrics information of master in WebUI."
<li>[7fdf195b5f3bb4d4a0bd155d1663a96f9eaf4da1] Fixed fetcher to not pick up environment variables it should not see.
<li>[dc01a78680410d7fe49e096508b64e94d991471c] Updated mesos containerizer to ignore GPU isolator creation failure.
