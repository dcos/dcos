#!/opt/mesosphere/bin/python3

import os
import subprocess
import sys

class IsolatorDiscoveryException(Exception):
    pass

def has_nvidia():
  """
  Test if we have nvidia available
  """
  nvidia_smi_binary = '/bin/nvidia-smi'

  # Make sure file is there and with correct permissions
  if not os.path.isfile(nvidia_smi_binary):
    return False
  if not os.access(nvidia_smi_binary, os.X_OK):
    return False

  # Try to run it
  proc = subprocess.Popen([ nvidia_smi_binary, '-L' ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

  # Wait for stdout/err
  (stdout, stderr) = proc.communicate()
  proc.wait()

  # Test for lack of errors
  if proc.returncode != 0:
    return False

  # Everything looks good
  return True

def main(output_env_file):
  """
  This script detects if nVidia driver is available
  and if yes, it appends the gpu/nvidia isolator
  """

  # Get current environment variable value
  isolators = os.environ.get('MESOS_ISOLATION', '')

  # Append isolators
  if has_nvidia():

    # Add ',' if we have other isolators
    if isolators:
      isolators += ','

    # Append gpu/nvidia
    isolators += 'gpu/nvidia'

  # Create environment script
  with open(output_env_file, 'w') as f:
    f.write('MESOS_ISOLATION=%s\n' % isolators)

if __name__ == '__main__':
    try:
        main(sys.argv[1])
    except KeyError as e:
        print('ERROR: Missing key {}'.format(e), file=sys.stderr)
        sys.exit(1)
    except IsolatorDiscoveryException as e:
        print('ERROR: {}'.format(e), file=sys.stderr)
        sys.exit(1)
