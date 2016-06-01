# Rules for using systemd reliably

These are coding style guidelines for our systemd units, based on bugs we've run into in production previously.

 - `Requires=`, `Wants=` are not allowed. If something that is depended upon fails, the thing depending on it will never try to be started again.
 - `Before=`, `After=` are discouraged. They are not strong guarantees, software needs to check that pre-requisites are up and working correctly
 - `Restart=always` should be used for all long-running services
 - Timer units need a non-zero OnBootSec (Some versions of systemd segfault with 0). We default to `5sec`.
 - No using 'BindsTo' (Same reason as Requires/Wants)
 - All Exec and ExecStart lines must be trivial. If you're starting bash to do some computation, or a python interpreter with an embedded script which is doing something it will be rejected. Make a simple helper script. One-liners aren't cool to maintain.
 - `Description=` is used by the diagnostics service.  Should be of the form `$SERVICE_NAME: $DESCRIPTION`
 - All new services must run as non-root `User=` must be set in their service files.

Note some of the units do not follow these guidelines. They're being updated.
