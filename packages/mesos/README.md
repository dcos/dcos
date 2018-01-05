<H2>Patches to cherry-pick on top of open source Apache Mesos before building in DC/OS</h2>
All commits can be found in the repository at <a href="https://github.com/mesosphere/mesos/">https://github.com/mesosphere/mesos/</a>.

<h3>WebUI magic for DC/OS' reverse proxy</h3>
<li>[9659ca424cbc9bd7c3942e6f48dc1bbd1b2f27cc] Mesos UI: Change paths, pailer, and logs to work with a reverse proxy.
<li>[0e61b936bf383572d2613b5ff8af045339f8c633] Revert "Fixed the broken metrics information of master in WebUI."

<h3>LIBPROCESS_IP workaround</h3>
<li>[04e5fc463bd4cba4d3480eb2584146424dfbf1cd] Set LIBPROCESS_IP into docker container.

<h3>GPU-related workarounds</h3>
<li>[cdec8ecded25db8c8d8ac0a4838b9f7e3d9285d1] Updated mesos containerizer to ignore GPU isolator creation failure.
<li>[bd983e54c7d941db4a67c1d5659a60014b3fec71] Added '--filter_gpu_resources' flag to the mesos master.

<h3>Critical backports that are not in Mesos 1.2.3</h3>
<li>[13a07821db91c8e2787421a63abcb422aaa171f4] Terminated driver-based executors if kill arrives before launch task.
<li>[59d17c833bd464e2e16d1cd685193f4f3277a925] Ensured executor adapter propagates error and shutdown messages.
<li>[e0889bf81890202cc3c55ce36c5f0e037f720761] Ensured command executor always honors shutdown request.
<li>[8594503910fc35a8cbf33d4c270d6d0e33276b03] Promoted log level to warning for disconnected events in exec.cpp.