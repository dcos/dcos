#!/usr/bin/env python3
# import argparse
import json
import sys

telegraf_template = '''
[[processors.override]]
  [processors.override.tags]
    fault_domain_region = "{region}"
    fault_domain_zone = "{zone}"
'''

fd = {}
region = ""
zone = ""
try:
    fd = json.load(sys.stdin).get("fault_domain", {})
    region = fd.get("region", {}).get("name", "")
    zone = fd.get("zone", {}).get("name", "")
except:
    exit("Could not parse fault domain json")

print(telegraf_template.format(zone=zone, region=region))
