#!/usr/bin/env python3
# This file is a utility for adding fault domain tags to metrics produced by
# telegraf. It expects a JSON input corresponding to the format detailed here:
# https://docs.mesosphere.com/1.12/deploying-services/fault-domain-awareness/
#
# It outputs a shell script which sets two environment variables called
# FAULT_DOMAIN_REGION and FAULT_DOMAIN_ZONE. These are then included in the
# global tags in the telegraf config, so adding a fault_domain_region and
# fault_domain_zone tag to every metric which passes through the telegraf
# pipeline.
#
# If the input is not valid JSON, or is not structured as expected, nothing
# will be output and an error message will be logged.

import json
import sys

env_var_template = '''
export FAULT_DOMAIN_REGION="{region}"
export FAULT_DOMAIN_ZONE="{zone}"
'''

fd = {}
try:
    fd = json.load(sys.stdin).get("fault_domain", {})
except:
    exit("Could not parse fault domain json")

region = fd.get("region", {}).get("name", "")
zone = fd.get("zone", {}).get("name", "")

print(env_var_template.format(zone=zone, region=region))
