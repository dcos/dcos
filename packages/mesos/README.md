<H2>Patches to cherry-pick from mesosphere/mesos on top of open source Apache Mesos 0.28 or later:</h2>
<li>[4f6515e6a92370a2bcd4cd1f45ef08056f45c88a] Mesos UI: Change paths, pailer, and logs to work with a reverse proxy.
<li>[cfbce38cd810e221b3fd1318fdb554857ef64a1d] Changed agent_host to expect a relative path.
<li>[23f157a4bffad38b2829bf544e24f8d490cd7b5d] Set LIBPROCESS_IP into docker container.

<H2>Patches to cherry-pick from mesosphere/mesos on top of open source Apache Mesos 1.0:</h2>
<li>[377bb78a1ca109447201f9d0909afcd91fdc8fda] Removed `O_SYNC` from StatusUpdateManager. (landing in 1.1.0)
<li>[e8c81c1c5684079890dae24e0dce2806aff507a7] Added flag in logrotate module to control number of libprocess threads. (landing in 1.1.0)
<li>[e444edd6e7d45eb842fe223ac484a4bc4c1a327a] Allowed all flags load methods to specify a prefix. (landing in 1.1.0)
<li>[3dd498d797a44593d376b4d50a33e2b8214c0dd4] Split src/openssl.hpp adding include/process/ssl/flags.hpp. (landing in 1.1.0)
<li>[f6581f2e8fcb07074fca9e72b3134476f6fc74ab] Updated includes to follow the SSL flag split. (landing in 1.1.0)
