#!/opt/mesosphere/bin/python
import os
import sys

import requests


EXHIBITOR_STATUS_URL = 'http://127.0.0.1:8181/exhibitor/v1/cluster/status'

# delete all proxy environment variables to never use it in requests
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('https_proxy', None)
os.environ.pop('NO_PROXY', None)
os.environ.pop('no_proxy', None)

cluster_size = int(open('/opt/mesosphere/etc/master_count').read().strip())

resp = requests.get(EXHIBITOR_STATUS_URL)
if resp.status_code != 200:
    print('Could not get exhibitor status: {}, Status code: {}'.format(
          EXHIBITOR_STATUS_URL, resp.status_code), file=sys.stderr)
    sys.exit(1)

data = resp.json()

serving = 0
leaders = 0
for node in data:
    if node['isLeader']:
        leaders += 1
    if node['description'] == 'serving':
        serving += 1

if serving != cluster_size or leaders != 1:
    print('Expected {} servers and 1 leader, got {} servers and {} leaders'.format(
        cluster_size, serving, leaders), file=sys.stderr)
    sys.exit(1)

sys.exit(0)
