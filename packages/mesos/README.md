<H2>Patches to cherry-pick on top of open source Apache Mesos before building in DC/OS</h2>
All commits can be found in the repository at <a href="https://github.com/mesosphere/mesos/">https://github.com/mesosphere/mesos/</a>.

<h3>Critical backports that are not in Mesos 1.2.3</h3>
<li>[8594503910fc35a8cbf33d4c270d6d0e33276b03] Promoted log level to warning for disconnected events in exec.cpp.
<li>[e0889bf81890202cc3c55ce36c5f0e037f720761] Ensured command executor always honors shutdown request.
<li>[59d17c833bd464e2e16d1cd685193f4f3277a925] Ensured executor adapter propagates error and shutdown messages.
<li>[13a07821db91c8e2787421a63abcb422aaa171f4] Terminated driver-based executors if kill arrives before launch task.
<li>[d566462f8af1739d718a994885334ad7063dce86] Reaped the container process directly in Docker executor.
<li>[f03e2a1545ef1e70269c33245503c3efb215b7c5] Windows: Fixed flaky Docker command health check test.
<li>[c5479b6e1a140728e60390ae77f5430dcacc014c] Prevented Docker library from terminating incorrect processes.
<li>[2d17e0b9098c3f455eac5ceb82ac5021b23e55ce] Updated discard handling for Docker 'stop' and 'pull' commands.
<li>[e7c9c1da92be006c161ccfba6e3ae6bfc5b46276] Ensured that Docker containerizer returns a failed Future in one case.
<li>[721dee01bce444b06f71b68a68eb741dd331ed9f] Updated discard handling in `Docker::inspect()`.
<li>[088498968dadef1b98e0d98d02044b7172dc1a56] Avoided orphan subprocess in the Docker library.
<li>[a28a0daacb20b9acd68c0bd1ed86cb51afc66ff1] Handled hanging docker `stop`, `inspect` commands in docker executor.
<li>[fa7106d947300d9eebe0dbeea3bed84dac187419] Added overload of process::await that takes and returns single future.
<li>[314a117446f9f7f6e05d319a53c1eb9235cbe247] Fixed compile issue for backporting by removing 'AwaitSingleAbandon'.
<li>[89a430b525c4612606af419ab88f7383217464ab] Added inspect retries to the Docker executor.
<li>[abfa0229c5017e1644c301192c877e36ba7fe177] Added inspect retries to the docker containerizer in `update` method.
<li>[1d104c8584dbcc398d709ced6271971593471991] Fixed an issue with the scheduler driver subscribe backoff time.
<li>[4a0d0de518b71330667a186f0c01846a82922135] Libprocess: Fixed a crash in the presence of request/response trailers.
<li>[563f24caba5c3dd07350bd8f6f1aef2dbfb87bb5] Stout: Ensured exceptions are caught for `picojson::parse()`.

<h3>WebUI magic for DC/OS' reverse proxy</h3>
<li>[9659ca424cbc9bd7c3942e6f48dc1bbd1b2f27cc] Mesos UI: Change paths, pailer, and logs to work with a reverse proxy.
<li>[0e61b936bf383572d2613b5ff8af045339f8c633] Revert "Fixed the broken metrics information of master in WebUI."

<h3>LIBPROCESS_IP workaround</h3>
<li>[04e5fc463bd4cba4d3480eb2584146424dfbf1cd] Set LIBPROCESS_IP into docker container.

<h3>GPU-related workarounds</h3>
<li>[cdec8ecded25db8c8d8ac0a4838b9f7e3d9285d1] Updated mesos containerizer to ignore GPU isolator creation failure.
<li>[bd983e54c7d941db4a67c1d5659a60014b3fec71] Added '--filter_gpu_resources' flag to the mesos master.
