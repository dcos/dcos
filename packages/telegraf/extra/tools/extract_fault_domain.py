#!/usr/bin/env python3
# This file is a utility for adding fault domain tags to metrics produced by
# telegraf. It expects a JSON input corresponding to the format detailed here:
# https://docs.mesosphere.com/1.12/deploying-services/fault-domain-awareness/
#
# It outputs the name of either the fault domain's region or zone, according to
# its argument. These are then included in the global tags in the telegraf
# config, so adding a fault_domain_region and fault_domain_zone tag to every
# metric which passes through the telegraf pipeline.
#
# If the input is not valid JSON, or is not structured as expected, nothing
# will be output and an error message will be logged.

import json
import sys


if len(sys.argv) != 2 or sys.argv[1] not in ['region', 'zone']:
    print("usage: {} <region|zone>".format(sys.argv[0]), file=sys.stderr)
    sys.exit(1)

try:
    obj = json.load(sys.stdin)
except Exception as exc:
    print("Error parsing json input: {}".format(exc), file=sys.stderr)
    sys.exit(1)

try:
    name = obj['fault_domain'][sys.argv[1]]['name']
except KeyError as exc:
    print("Invalid fault domain json. Missing key: {}".format(exc), file=sys.stderr)
    sys.exit(1)

print(name)
