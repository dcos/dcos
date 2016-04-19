# Rules for using systemd reliably

These are coding style guidelines for our systemd units, based on bugs we've run into in production previously.

 - `Requires=`, `Wants=` are not allowed. If something that is depended upon fails, the thing depending on it will never try to be started again.
 - `Before=`, `After=` are discouraged. They are not strong guarantees, software needs to check that pre-requisites are up and working correctly
 - `Restart=always` should be used for all long-running services
 - Timer units need a non-zero OnBootSec (Some versions of systemd segfault with 0). We default to `5sec`.
