# Deployer Module

Perform tasks/call endpoints on every machine, query machine state to determine deployment status. Aggregates status pings from the Restart Helper to monitor rollout progress / provide better insights. Has an endpoint `halt` which can have HTTP requests made to it by any sort of SLA monitoring setup an organization has in order to stop the deploy  module from taking further action without explicit clearing from and admin.

## Special Powers
 - Wiping out work_dir and all running tasks vs. soft restart of mesos slave
 - halt endpoint
 - Use the maintenance primitives for hard restarts. "soft" maintenance to say "I'm doing things".
 - Rolling deployment / time delay between servers
