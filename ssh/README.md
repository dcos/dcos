# SSH Library
This library implements a SSH runner capable of running multiple SSH processes for parallel remote execution. It also includes SCP functionality for both local to remote, remote to local and recursive copy to remote targets.

## API

**Basic Example**:

```python
ssh = SSHRunner()
ssh.user = 'ubuntu'
ssh.key_path = '/home/ubuntu/key.pem'
ssh.targets = ['127.0.0.1', '127.0.0.2']
ssh.log_directory = '/tmp'
ssh.use_cache = False

output = ssh.execute_cmd('hostname')

copy_out = ssh.copy_cmd('/tmp/file.txt', '/tmp')
copy_recursive_out = ssh.copy_cmd('/usr', '/', recursive=True)

print(output)
print(copy_out)
print(copy_recursive_out)
```

### SSHRunner()

#### Parameters

##### `.user` *string*
The user to SSH to the remote target as.

##### `.key_path` *string*
The path to the private key.

##### `.targets` *list*
A list of target IP addresses: IPv4 or IPv6.

##### `.log_directory` *string*
The path to the directory to dump SSH logs to. Currently required.

##### `.use_cache` *bool*
Use cache to retry failed SSH sessions.

##### `.execute_cmd()` *string*
Execute remote commands on target hosts.

##### `.copy_cmd()` *string* *string* recursive=*bool*
Copy local_path to remote_path on target hosts.

##### `.validate()` throw_if_errors=*bool*
Validate this class and exit or not exit on errors. Useful when implementing this library in a parent program and you do not want SSH library to exit on failures.

### Pretty Print
The pretty printer provides a nice way to print colored output for success and failures to the console for a given run. It's purely optional.

**Basic Example**:

```python
from ssh.prettyprint import SSHPrettyPrint
output = ssh.execute_cmd('hostname')

pretty_out = SSHPrettyPrint(output)
output.beautify()
```

#### Parameters

##### `.output` *dictionary* *output from SSHRunner*
Pass the output from SSHRunner to .output.

##### `.beautify()` *None*
Print the output from SSHRunner in a pretty way :)


