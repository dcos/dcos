<H2>Patches to cherry-pick from mesosphere/mesos on top of open source Apache Mesos</h2>
<H3>WebUI magic for DC/OS' reverse proxy</H3>
<li>[4f6515e6a92370a2bcd4cd1f45ef08056f45c88a] Mesos UI: Change paths, pailer, and logs to work with a reverse proxy.
<li>[cfbce38cd810e221b3fd1318fdb554857ef64a1d] Changed agent_host to expect a relative path.
<li>[c0da3d7468787edb93d4c79bcdf5d1d9e7de678a] Revert "Fixed the broken metrics information of master in WebUI."

<H3>LIBPROCESS_IP workaround</H3>
<li>[23f157a4bffad38b2829bf544e24f8d490cd7b5d] Set LIBPROCESS_IP into docker container.

<H3>Backports from master that are landing in Mesos 1.1.0</H3>
<li>[377bb78a1ca109447201f9d0909afcd91fdc8fda] Removed `O_SYNC` from StatusUpdateManager.
<li>[e8c81c1c5684079890dae24e0dce2806aff507a7] Added flag in logrotate module to control number of libprocess threads.
<li>[3dd498d797a44593d376b4d50a33e2b8214c0dd4] Split src/openssl.hpp adding include/process/ssl/flags.hpp.
<li>[f6581f2e8fcb07074fca9e72b3134476f6fc74ab] Updated includes to follow the SSL flag split.
<li>[a22b5dd552168a8dd925682f3b349059e10fc3d3] Modified network file setup in `network/cni` isolator.
<li>[3e703af02bc309a9d6653392d02627bf3d3ce930] Updated logrotation module to use `os::pagesize()`.
<li>[1d45ba9f4f7f943d24282e0a91fb01c68815d6c3] Fixed sign comparisons in logrotate module.
<li>[b546e7544c04a6d3e0da87cd6207ae8f4d827add] Added a way to set logrotate settings per executor.
<li>[2adcc49bb584f84b358b6edb78a975382e9f9feb] Modified the executor driver to always relink on agent failover.
<li>[52b4675a96858eac6b4709c5f46bd432cd6e20d9] Added new agent flag 'executor_reregistration_timeout'.
<li>[378e209c0e34c955e23505e2fb32b879794cdf8e] Added 'executor_reregister_timeout' agent flag to the tests.
<li>[815e9dd6620ad1f13d6a326079e9b61c2484294d] Introduced executor reconnect retries on the agent.
<li>[beb19ab9d6d42ae92e1868094af23f69ad553443] Made the executor driver drop some messages when not connected.

<H3>Critical backports from Mesos 1.1.x and 1.2.x branches</H3>
<li>[55899ec435a7cae1961c64f275a40d989d1ca8e3] Fixed a crash on the master upon receiving an invalid inverse offer.
<li>[bead9f592bc3b64b94b6b0019e11be0d200f20bf] Fixed health check bug when running agents with `docker_mesos_image`.
<li>[4cf39808a8d81e54b69258095e3185493d775544] Fixed the image signature check for Nexus Registry.
<li>[30d0e46ce0674a31477b804f850ad233287876e2] Fixed docker fetcher 3xx redirect errors by header attached.
<li>[1a403cce844b4a6ebf0ccee2591aeca0f05e4e99] Fixed provisioner recover blockage by non-existing rootfses dir.
<li>[6027f2621d1e6a59c1900b0ee56c0b6d417a385a] Don't crash when re-registering executor from an unknown framework.
<li>[67b6f2a8504277ade2b5e66305a3b3c1bbeaf8ba] Don't crash the agent when an unknown executor re-registers.
<li>[33de5301fc1f25de8c0e6fa88aa7604b9d088297] Added logging of executor re-registration messages.
<li>[faede67f2b46636df8c85c23a561743fc85d9e3d] Fixed a crash in libprocess when failing to decode a request path.
<li>[6ca32629de7e613a8ce208a8423caf4de0868499] Rejected libprocess HTTP requests with empty path.
<li>[47aa5275fdfb157f35f7ea530fa3c91c1591c4cb] Fixed cherry-pick build error.
<li>[e1c25310a3ac3aff1e4bf87d2c780bf2e2091c48] Fixed member access issue introduced by a cherry-pick.
<li>[6d8e86341f87a3bd210a145e7e351cf701355d2b] Preventing agent recovery failing from unsuccessful `docker rm`.
<li>[5e6f462e2d9ab0acde0834c3a94aa8141037a148] Set the `LIBPROCESS_IP` env variable before starting the fetcher.
<li>[6413b3ff5340c333959b2266a1a5c98ae4a7adbb] Added logging in docker executor on `docker stop` failure.
<li>[97d3f4eadced34e03b93bd01e203cd47b480ee36] Enabled retries for `killTask` in docker executor.
<li>[59e719a82e4739bd7de6de6afce0ec8c8a46be0d] Created staging dir only when needed.
<li>[0a581996f37d53cd346b4bafd4324ec72b0488aa] Fixed an OOM due to a send loop for SSL sockets.
