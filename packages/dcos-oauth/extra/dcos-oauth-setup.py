#!/opt/mesosphere/bin/python3
import random
import string
import subprocess

possible_auth_token = ''.join(random.choice(string.ascii_letters) for _ in range(64))

auth_proc = subprocess.Popen([
    '/opt/mesosphere/bin/zk-value-consensus',
    '/dcos/auth-token-secret'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE)

consensus_auth_token, _ = auth_proc.communicate(input=possible_auth_token.encode())
consensus_auth_token = consensus_auth_token.decode().strip()

consensus_auth_token
# TODO(cmaloney): Create the file with chmod 600 rather than doing it post-hoc.
with open('/var/lib/dcos/dcos-oauth/auth-token-secret', 'w') as f:
    f.write(consensus_auth_token)

subprocess.check_call(['chmod', '600', '/var/lib/dcos/dcos-oauth/auth-token-secret'])
