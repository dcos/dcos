# DC/OS Installer

# REST API

#### / -redirects-> /api/v1
**GET**: Loads application

#### /assets
**GET**: Serves assets in dcos_installer/assets/

Return headers are self informed. In example, if the file is foo.js the header to return will be ```application/javascript```.

#### /api/v1/configure/
**GET**: Get currently stored configuration and validation messages.

```json
{
  "ssh_config": {
    "ssh_user": null,
    "target_hosts": [
      null
    ],
    "log_directory": "/genconf/logs",
    "ssh_key_path": "/genconf/ssh_key",
    "ssh_port": 22
  },
  "cluster_config": {
    "docker_remove_delay": "1hrs",
    "resolvers": [
      "8.8.8.8",
      "8.8.4.4"
    ],
    "roles": "slave_public",
    "exhibitor_storage_backend": "zookeeper",
    "ip_detect_path": "/genconf/ip-detect",
    "exhibitor_zk_hosts": "127.0.0.1:2181",
    "cluster_name": "Mesosphere: The Data Center Operating System",
    "weights": "slave_public=1",
    "num_masters": null,
    "master_discovery": "static",
    "master_list": null,
    "bootstrap_url": "file:///opt/dcos_install_tmp",
    "exhibitor_zk_path": "/exhibitor",
    "gc_delay": "2days"
  },
}
```

**POST**: Read config from disk, overwrite the POSTed values, validate, write to disk if no errors, only return errors if there are any.

Example POST data structure:

```json
{
  "master_ips": ["...", "..."],
  "agent_ips": ["...", "..."],
  "ssh_username": "...",
  "ssh_port": 22,
  "ssh_key": "...",
  "username": "...",
  "password": "...",
  "upstream_dns_servers": "..."
  "zk_exhibitor_port": ".." # Yes, it's a string please!
  "zk_exhibitor_hosts": ["...", "..."]
  "ip_detect_script": "..."
}
```

```
curl -H 'Content-Type: application/json' -XPOST -d '{"ssh_config":{"ssh_user": "some_new_user"}}' localhost:5000/api/v1/configure | json
```

**SUCCESS** - 200, empty body

**FAILURE** - 400, errors
```json
{ "errors": {
   "ssh_user": "None is not a valid string. Is of type <class 'NoneType'>.",
   "target_hosts": "[None] is not valid IPv4 address.",
   "ssh_key_path": "File does not exist /genconf/ssh_key",
   "master_list": "None is not of type list."
  }
}
```

#### /api/v1/configure/status
**GET**: Get the current configuration validation

```
curl -H 'Content-Type: application/json' -XGET localhost:5000/api/v1/configure | json
```

```json
{
  "success": {
    "docker_remove_delay": "1hrs is a valid string.",
    "resolvers": "['8.8.8.8', '8.8.4.4'] is a valid list of IPv4 addresses.",
    "ssh_port": "22 is a valid integer.",
    "ip_detect_path": "File exists /genconf/ip-detect",
    "exhibitor_storage_backend": "exhibitor_storage_backend is valid.",
    "roles": "slave_public is a valid string.",
    "exhibitor_zk_hosts": "127.0.0.1:2181 is valid exhibitor ZK hosts format.",
    "cluster_name": "Mesosphere: The Data Center Operating System is a valid string.",
    "bootstrap_url": "file:///opt/dcos_install_tmp is a valid string.",
    "master_discovery": "master_discovery method is valid.",
    "weights": "slave_public=1 is a valid string.",
    "ssh_user": "some_new_user is a valid string.",
    "exhibitor_zk_path": "/exhibitor is a valid string.",
    "gc_delay": "1hrs is a valid string."
  },
  "warning": {},
  "errors": {
    "target_hosts": "[None] is not valid IPv4 address.",
    "ssh_key_path": "File does not exist /genconf/ssh_key",
    "master_list": "None is not of type list."
  }
}
```

Notice that the ssh_user is no longer ```None``` and the validation for it now passes since it is a string.


#### /api/v1/configure/type
**GET**: Get the current configuration type, advanced or minimal.

If minimal is found:
```json
{
  "configuration_type": "minimal",
  "message": "Configuration looks good!",
}
```

If advanced is found:
```json
{
  "configuration_type": "advanced",
  "message": "Advanced configuration detected in genconf/config.yaml. Please backup or remove genconf/config.yaml to use the UI installer."
}
```

#### /api/v1/action/preflight/
**GET**:  RETURN preflight_status.json

```
curl localhost:5000/api/v1/preflight | json
```
```json
{
  "chain_name": "preflight",
  "total_hosts": 2,
  "hosts_failed": 2,
  "hosts": {
    "10.33.2.21:22": {
      "host_status": "failed",
      "commands": [
        {
          "date": "2016-01-22 23:51:37.324109",
          "stdout": [
            ""
          ],
          "stderr": [
            "ssh: connect to host 10.33.2.21 port 22: No route to host\r",
            ""
          ],
          "pid": 3364,
          "cmd": [
            "/usr/bin/ssh",
            "-oConnectTimeout=10",
            "-oStrictHostKeyChecking=no",
            "-oUserKnownHostsFile=/dev/null",
            "-oBatchMode=yes",
            "-oPasswordAuthentication=no",
            "-p22",
            "-i",
            "/genconf/ssh_key",
            "-tt",
            "vagrant@10.33.2.21",
            "sudo",
            "mkdir",
            "-p",
            "/opt/dcos_install_tmp"
          ],
          "returncode": 255
        }
      ]
    },
    "10.33.2.22:22": {
      "host_status": "failed",
      "commands": [
        {
          "date": "2016-01-22 23:51:37.325893",
          "stdout": [
            ""
          ],
          "stderr": [
            "ssh: connect to host 10.33.2.22 port 22: No route to host\r",
            ""
          ],
          "pid": 3365,
          "cmd": [
            "/usr/bin/ssh",
            "-oConnectTimeout=10",
            "-oStrictHostKeyChecking=no",
            "-oUserKnownHostsFile=/dev/null",
            "-oBatchMode=yes",
            "-oPasswordAuthentication=no",
            "-p22",
            "-i",
            "/genconf/ssh_key",
            "-tt",
            "vagrant@10.33.2.22",
            "sudo",
            "mkdir",
            "-p",
            "/opt/dcos_install_tmp"
          ],
          "returncode": 255
        }
      ]
    }
  }
}
```

**POST**: Execute preflight on target hosts. Returns state.json

#### /api/v1/action/preflight/logs/
**GET**: Get *_preflight logs for download (this is a .tar file)

#### /api/v1/action/deploy/
**GET**:  RETURN state.json

**POST**: Execute install DC/OS on target hosts. Return state.json.

#### /api/v1/action/deploy/logs/
**GET**: Get *_deploy.log data for download (this is a .tar file)

#### /api/v1/action/postflight/
**GET**: RETURN state.json

**POST**:  Execute postflight on target hosts, return state.json.

#### /api/v1/action/postflight/logs/
**GET**:  RETURN *_postflight.log files for download

#### /api/v1/action/current/
**GET**: RETURN current_action_name

```json
{
  "current_action": "postflight"
}
```

#### /api/v1/success/
**GET**: RETURN url to DC/OS UI

```
curl localhost:5000/api/v1/success
```
```json
{
  "dcosUrl": "http://foobar.com",
  "master_count": 3,
  "agent_count": 400
}
```
