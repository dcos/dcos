import json


with open('/opt/mesosphere/etc/expanded.config.json', 'r') as f:
    expanded_config = json.load(f)
