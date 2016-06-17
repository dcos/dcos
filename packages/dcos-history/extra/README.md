dcos-history-service
===================
Overview
--------
Collects and keeps old mesos /state-summary

This enables UIs around Mesos to have historical data from the past n seconds so
they can display graphs with earlier datapoints when first loaded rather than
having first page load be the start of time

API
---
* GET: localhost:$PORT/ - returns basic API usage
* GET: localhost:$PORT/ping - returns 'pong' to verify server is up
* GET: localhost:$PORT/history/last - returns last state-summary.json from master
* GET: localhost:$PORT/history/minute - returns a JSON array of state-summary.json for the previous minute. The period of updating is currently hard-coded to 2 seconds, so this array will have at most 30 entries. '{}' entries represent absent data from a gap after a shutdown or inability to successfully query leader.mesos/state-summary
* GET: localhost:$PORT/history/hour - returns a JSON array of state-summary.json for the previous hour at minute resolution (60 entries max)

NOTE: On first startup, the arrays in /history/minute and /history/hour will be length 1 and will eventually reach their final size as data is added

LOGGING
-------
dcos-history-service stores the current state in memory, but also replicates the state-summaries to disk in /var/lib/mesosphere/dcos/history-service. This directory is trimmed on each update and is currently hardcoded to only store as much data on disk as is currently in memory.
