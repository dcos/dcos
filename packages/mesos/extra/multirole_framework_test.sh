#!/usr/bin/env bash

# FIXME(bbannier): module docstring

set -e
set -o pipefail

### BEGIN support/atexit.sh ##

# Array of commands to eval.
declare -a __atexit_cmds

# Helper for eval'ing commands.
__atexit() {
    for cmd in "${__atexit_cmds[@]}"; do
        eval ${cmd} &> /dev/null || true
    done
}

# Usage: atexit command arg1 arg2 arg3
atexit() {
    # Determine the current number of commands.
    local length=${#__atexit_cmds[*]}

    # Add this command to the end.
    __atexit_cmds[${length}]="${*}"

    # Set the trap handler if this was the first command added.
    if [[ ${length} -eq 0 ]]; then
        trap __atexit EXIT
    fi
}

### END support/atexit.sh ##

function random_port {
  # Generate a random port number.
  echo $((RANDOM + 2000))
}

function timeout_ {
  TIME=30 # seconds
  if hash timeout 2>/dev/null; then
    timeout "${TIME}" "$@"
  else
    gtimeout "${TIME}" "$@"
  fi
}

function mkdtemp_ {
  if [ -z "${1// }" ]; then
    echo "Argument required"
    exit
  fi

  mktemp -d "${PWD:-/tmp}"/"${1}".XXXXXX
}

function setup_env {
  # export LD_LIBRARY_PATH=${MESOS_BUILD_DIR}/src/.libs

  MESOS_SBIN_DIR=/opt/mesosphere/packages/mesos--257d0712c2ea3b4e467a958cce5bc91a929800b8/bin/
  MASTER=${MESOS_SBIN_DIR}/mesos-master
  AGENT=${MESOS_SBIN_DIR}/mesos-agent

  MESOS_HELPER_DIR=/opt/mesosphere/packages/mesos--257d0712c2ea3b4e467a958cce5bc91a929800b8/libexec/mesos/tests/
  MULTIROLE_FRAMEWORK=${MESOS_HELPER_DIR}/multirole-framework
}

function cleanup {
  rm -f framework_id
}

function start_master {
  MESOS_WORK_DIR=$(mkdtemp_ mesos-master)
  atexit rm -rf "${MESOS_WORK_DIR}"

  MASTER_PORT=$(random_port)

  ACLS=${1:-\{\"permissive\": true\}}

  ${MASTER} \
    --ip=127.0.0.1 \
    --port="$MASTER_PORT" \
    --acls="${ACLS}" \
    --work_dir="${MESOS_WORK_DIR}" &> "${MESOS_WORK_DIR}.log" &
  MASTER_PID=${!}

  atexit rm -rf "${MESOS_WORK_DIR}.log"

  echo "${GREEN}Launched master at ${MASTER_PID}${NORMAL}"

  sleep 2

  # Check the master is still running after 2 seconds.
  kill -0 ${MASTER_PID} >/dev/null 2>&1
  STATUS=${?}
  if [[ ${STATUS} -ne 0 ]]; then
    echo "${RED}Master crashed; failing test${NORMAL}"
    exit 2
  fi

  atexit kill ${MASTER_PID}
}

function start_agent {
  # Disable support for systemd as this test does not run as root.
  # This flag must be set as an environment variable because the flag
  # does not exist on non-Linux builds.
  export MESOS_SYSTEMD_ENABLE_SUPPORT=false

  MESOS_WORK_DIR=$(mkdtemp_ mesos-agent)
  atexit rm -rf "${MESOS_WORK_DIR}"

  MESOS_RUNTIME_DIR=$(mkdtemp_ mesos-agent-runtime)
  atexit rm -rf "${MESOS_RUNTIME_DIR}"

  AGENT_PORT=$(random_port)

  RESOURCES=${1:-cpus:1;mem:96;disk:50}

  ${AGENT} \
    --work_dir="${MESOS_WORK_DIR}" \
    --runtime_dir="${MESOS_RUNTIME_DIR}" \
    --master=leader.mesos:5050 \
    --port="$AGENT_PORT" \
    --resources="${RESOURCES}" &> "${MESOS_WORK_DIR}.log" &
  AGENT_PID=${!}

  atexit rm -rf "${MESOS_WORK_DIR}.log"

  echo "${GREEN}Launched agent at ${AGENT_PID}${NORMAL}"

  sleep 2

  # Check the agent is still running after 2 seconds.
  kill -0 ${AGENT_PID} >/dev/null 2>&1
  STATUS=${?}
  if [[ ${STATUS} -ne 0 ]]; then
    echo "${RED}Slave crashed; failing test${NORMAL}"
    exit 2
  fi

  atexit kill ${AGENT_PID}
}

function run_framework {
  echo "${GREEN}Running framework${NORMAL}"
  ROLES=${1:-\[\"roleA\", \"roleB\"\]}
  DEFAULT_TASKS='
      {
        "tasks": [
          {
            "role": "roleA",
            "task": {
              "command": { "value": "sleep 1" },
              "name": "task1",
              "task_id": { "value": "task1" },
              "resources": [
                {
                  "name": "cpus",
                  "scalar": {
                    "value": 0.5
                  },
                  "type": "SCALAR"
                },
                {
                  "name": "mem",
                  "scalar": {
                    "value": 48
                  },
                  "type": "SCALAR"
                }
              ],
              "slave_id": { "value": "" }
            }
          },
          {
            "role": "roleB",
            "task": {
              "command": { "value": "sleep 1" },
              "name": "task2",
              "task_id": { "value": "task2" },
              "resources": [
                {
                  "name": "cpus",
                  "scalar": {
                    "value": 0.5
                  },
                  "type": "SCALAR"
                },
                {
                  "name": "mem",
                  "scalar": {
                    "value": 48
                  },
                  "type": "SCALAR"
                }
              ],
              "slave_id": { "value": "" }
            }
          }
        ]
      }'

  MESOS_TASKS=${MESOS_TASKS:-$DEFAULT_TASKS}

  echo "Tasks"
  echo "-----"
  echo "${MESOS_TASKS}" | jq .

  timeout_ ${MULTIROLE_FRAMEWORK} \
    --master=leader.mesos:5050 \
    --roles="$ROLES" \
    --max_unsuccessful_offer_cycles=3 \
    --tasks="${MESOS_TASKS}"
}

setup_env

function test_multirole_framework_registration {
  echo "${BOLD}"
  echo "********************************************************************************************"
  echo "* A framework can be in two roles and start tasks on resources allocated for either role.  *"
  echo "********************************************************************************************"
  echo "${NORMAL}"
  start_agent
  run_framework
  __atexit
}

function test_quota {
  echo "${BOLD}"
  echo "********************************************************************************************"
  echo "* Frameworks in multiple roles can use quota.                                              *"
  echo "********************************************************************************************"
  echo "${NORMAL}"
  start_agent

  echo "${BOLD}"
  echo "Quota'ing all of the agent's resources for 'roleA'."
  echo "${NORMAL}"
  QUOTA='
  {
    "role": "roleA",
    "force": true,
    "guarantee": [
    {
      "name": "cpus",
      "type": "SCALAR",
      "scalar": { "value": 1}
    },
    {
      "name": "mem",
      "type": "SCALAR",
      "scalar": { "value": 96}
    },
    {
      "name": "disk",
      "type": "SCALAR",
      "scalar": { "value": 50}
    }
    ]
  }'

  curl --silent -d"${QUOTA}" http://leader.mesos:5050/quota

  echo "${BOLD}"
  echo The framework will not get any resources to run tasks with 'roleB'.
  echo "${NORMAL}"

  ! run_framework

  echo "${BOLD}"
  echo If we make more resources available, the framework will also be offered resources for 'roleB'.
  echo "${NORMAL}"
  start_agent

  run_framework

  __atexit
}

function test_reserved_resources {
  echo "${BOLD}"
  echo "********************************************************************************************"
  echo "* Reserved resources.                                                                      *"
  echo "********************************************************************************************"
  echo "${NORMAL}"

  echo "${BOLD}"
  RESOURCES="cpus(roleA):0.5;cpus(roleB):0.5;mem(roleA):48;mem(roleB):48;disk(roleA):25;disk(roleB):25"
  echo Starting agent with reserved resources: $RESOURCES.
  echo We expect a framework in both roles to be able to launch tasks on resources from either role.
  echo "${NORMAL}"
  start_agent "${RESOURCES}"
  run_framework
  __atexit
}

function test_fair_share {
  echo "${BOLD}"
  echo "********************************************************************************************"
  echo "* Fair share.                                                                              *"
  echo "********************************************************************************************"
  echo "Starting a cluster with two frameworks: one framework is in two roles"
  echo "['roleA', 'roleB'] with one task in each, the other is only ['roleA']"
  echo "with two tasks."
  echo "We also start three agents which fit exactly one workload of the"
  echo "frameworks. We expect one framework to be able to launch both of its tasks immediately,"
  echo "while the other one will have to wait."
  echo "${NORMAL}"

  MESOS_TASKS='
  {
    "tasks": [
    {
      "role": "roleA",
      "task": {
        "command": { "value": "sleep 1" },
        "name": "task1",
        "task_id": { "value": "task1" },
        "resources": [
          {
            "name": "cpus",
            "scalar": { "value": 0.5 },
            "type": "SCALAR"
          },
          {
            "name": "mem",
            "scalar": { "value": 48 },
            "type": "SCALAR"
          }
        ],
        "slave_id": { "value": "" }
        }
      }, {
      "role": "roleB",
      "task": {
        "command": { "value": "sleep 1" },
        "name": "task2",
        "task_id": { "value": "task2" },
        "resources": [
          {
            "name": "cpus",
            "scalar": { "value": 0.5 },
            "type": "SCALAR"
          },
          {
            "name": "mem",
            "scalar": { "value": 48 },
            "type": "SCALAR"
          }
        ],
        "slave_id": { "value": "" }
      }}
    ]
  }'

  start_agent "cpus:0.5;mem:48;disk:25"
  start_agent "cpus:0.5;mem:48;disk:25"
  start_agent "cpus:0.5;mem:48;disk:25"


  echo "${BOLD}"
  echo Starting a framework in two roles which will consume the bulk on the resources.
  echo "${NORMAL}"
  run_framework &

  echo "${BOLD}"
  echo "Starting a framework in just one role which will be offered not enough"
  echo "resources initially since the earlier one will be below fair share in"
  echo "that role ('taskX_one_role' will finish last)."
  echo "${NORMAL}"

  # TODO(bbannier): Make this more testable. We expect this second framework to
  # finish last.
  cleanup
  (MESOS_TASKS=$(echo ${MESOS_TASKS} | sed 's/roleB/roleA/g' | sed 's/task1/task1_one_role/g' | sed 's/task2/task2_one_role/g') run_framework '["roleA"]')

  __atexit
}

function test_framework_authz {
  echo "${BOLD}"
  echo "********************************************************************************************"
  echo "* Framework authorization.                                                                 *"
  echo "********************************************************************************************"
  echo "${NORMAL}"

  ACLS='
  {
    "permissive": false,
    "register_frameworks": [
      {
        "principals": { "values": ["'${DEFAULT_PRINCIPAL}'"] },
        "roles": { "values": ["roleA", "roleB"] }
      },
      {
        "principals": { "values": ["OTHER_PRINCIPAL"] },
        "roles": { "values" : ["roleB"] }
      }
    ],
    "run_tasks": [
      {
        "principals" : { "values": ["'${DEFAULT_PRINCIPAL}'"] },
        "users": { "type": "ANY" }
      }
    ]
  }
  '

  CREDENTIALS='
  {
    "credentials": [
    {
      "principal": "'$DEFAULT_PRINCIPAL'",
      "secret": "'$DEFAULT_SECRET'"
    },
    {
      "principal": "OTHER_PRINCIPAL",
      "secret": "secret"
    }
    ]
  }'

  echo "${CREDENTIALS}" > credentials.json
  MESOS_CREDENTIALS=file://$(realpath credentials.json)
  export MESOS_CREDENTIALS

  echo "${BOLD}"
  echo "Using the following ACLs:"
  echo "${ACLS}" | jq .
  echo "${NORMAL}"

  start_master "${ACLS}"
  start_agent

  echo "${BOLD}"
  echo "Attempting to register a framework in role 'roleB' with a"
  echo "principal authorized for the role succeeds."
  echo "${NORMAL}"
  (DEFAULT_PRINCIPAL='OTHER_PRINCIPAL' DEFAULT_SECRET='secret' MESOS_TASKS='{"tasks": []}' run_framework '["roleB"]')

  echo "${BOLD}"
  echo "Attempting to register a framework in roles ['roleA', 'roleB'] with a principal authorized only for 'roleB' fails."
  echo "${NORMAL}"
  cleanup
  ! (DEFAULT_PRINCIPAL='OTHER_PRINCIPAL' DEFAULT_SECRET='secret' MESOS_TASKS='{"tasks": []}' run_framework)

  echo "${BOLD}"
  echo "Attempting to register a framework in roles ['roleA', 'roleB'] with a"
  echo "principal authorized for both roles succeeds. The framework can"
  echo "run tasks."
  cleanup
  echo "${NORMAL}"
  run_framework
}

function test_failover {
  echo "${BOLD}"
  echo "********************************************************************************************"
  echo "* A framework changing its roles can learn about its previous tasks.                       *"
  echo "********************************************************************************************"
  echo "${NORMAL}"
  start_agent

  TASKS='
  {
    "tasks": [
    {
      "role": "roleA",
      "await": false,
      "task": {
        "command": { "value": "sleep 2" },
        "name": "task1",
        "task_id": { "value": "task1" },
        "resources": [
          {
            "name": "cpus",
            "scalar": { "value": 0.5 },
            "type": "SCALAR"
          },
          {
            "name": "mem",
            "scalar": { "value": 48 },
            "type": "SCALAR"
          }
        ],
        "slave_id": { "value": "" }
        }
      }, {
      "role": "roleB",
      "await": false,
      "task": {
        "command": { "value": "sleep 2" },
        "name": "task2",
        "task_id": { "value": "task2" },
        "resources": [
          {
            "name": "cpus",
            "scalar": { "value": 0.5 },
            "type": "SCALAR"
          },
          {
            "name": "mem",
            "scalar": { "value": 48 },
            "type": "SCALAR"
          }
        ],
        "slave_id": { "value": "" }
      }}
    ]
  }'

  (MESOS_TASKS="${TASKS}" run_framework '["roleA", "roleB"]')

  echo "${BOLD}"
  echo "Restarting framework dropping 'roleA'. We can reconcile tasks started with dropped roles."
  echo "${NORMAL}"
  (MESOS_TASKS='{"tasks": []}' run_framework '["roleB"]')

  __atexit
}

function test_hrole_fairness {
  echo "${BOLD}"
  echo "********************************************************************************************"
  echo "* Hierarchical roles lead to expected fair share semantics                                 *"
  echo "********************************************************************************************"
  echo "${NORMAL}"

  echo "${BOLD}"
  echo "When working with hierarchical roles, fair share is determined at each level of the tree."
  echo "We start three tasks running in roles 'ops/a', 'ops/b', 'dev', and 'biz'. Since tasks under 'ops/' share resources we expect the task in 'ops/b' to run last."
  echo "${NORMAL}"

  start_agent

  TASK1='
  {
    "command": { "value": "touch task1" },
    "name": "task1",
    "task_id": { "value": "task1" },
    "resources": [
      {
        "name": "cpus",
        "scalar": { "value": 0.5 },
        "type": "SCALAR"
      },
      {
        "name": "mem",
        "scalar": { "value": 48 },
        "type": "SCALAR"
      }
    ],
    "slave_id": { "value": "" }
  }
  '

  TASKS='{
    "tasks": [
      {
        "role": "ops/a",
        "task": '${TASK1}'
      },
      {
        "role": "ops/b",
        "task": '${TASK1//task1/task2}'
      },
      {
        "role": "dev",
        "task": '${TASK1//task1/task3}'
      },
      {
        "role": "biz",
        "task": '${TASK1//task1/task4}'
      }
    ]
  }'

  cleanup
  MESOS_TASKS="${TASKS}" run_framework '["ops/a", "ops/b", "dev", "biz"]'

  echo "${BOLD}"
  echo "The task in role 'ops/b' ('task2') will have been run last."
  echo "${NORMAL}"
  LAST_TASK=$(basename $(ls -t $(find "${MESOS_WORK_DIR}" -name 'task?' -type f) | head -1))
  [ "${LAST_TASK}" = 'task2' ]

  __atexit
}

function test_hrole_quota_sum_rule {
  echo "${BOLD}"
  echo "********************************************************************************************"
  echo "* Quotas on parent roles provide a limit on the sum over leaf role quotas.                 *"
  echo "********************************************************************************************"
  echo "${NORMAL}"

  echo "${BOLD}"
  echo "A quota on a parent role provides a limit on the sum its leaf roles can have."
  echo "This test sets up a quota on a parent role, and the same quota on one of its leaf roles, thereby consuming the whole available quota in the hierarchy. Setting a quota on another leaf role fails."
  echo "${NORMAL}"

  start_agent

  # Make sure no quotas are set.
  for role in `curl --silent http://leader.mesos:5050/quota | jq .'infos[].role' || true`; do
      curl -X DELETE http://leader.mesos:5050/quota/`echo $role | sed 's/"//g'`;
  done

  QUOTA='
  {
      "guarantee": [
          {
              "name": "cpus",
              "scalar": {
                  "value": 0.1
              },
              "type": "SCALAR"
          }
      ],
      "role": "ROLE"
  }'

  echo "${BOLD}"
  echo "Setting quota for 'dev/' parent role"
  echo ${QUOTA//ROLE/dev} | jq .
  echo "${NORMAL}"
  curl -v -d"${QUOTA//ROLE/dev}" http://leader.mesos:5050/quota 2>&1 | grep -q 'HTTP/1.1 200 OK'

  echo "${BOLD}"
  echo "Setting quota for 'dev/a' leave role"
  echo ${QUOTA//ROLE/dev\/a} | jq .
  echo "${NORMAL}"
  curl -v -d"${QUOTA//ROLE/dev\/a}" http://leader.mesos:5050/quota 2>&1 | grep -q 'HTTP/1.1 200 OK'

  echo "${BOLD}"
  echo "Attemting to set quota for 'dev/b' leave role. This fails since the quota set by the parent role is already exhausted."
  echo ${QUOTA//ROLE/dev\/b} | jq .
  echo "${NORMAL}"
  ! (curl -v -d"${QUOTA//ROLE/dev\/b}" http://leader.mesos:5050/quota 2>&1 | grep -q 'HTTP/1.1 200 OK')

  __atexit

  # Make sure no quotas remain set.
  for role in `curl --silent http://leader.mesos:5050/quota | jq .'infos[].role' || true`; do
      curl -X DELETE http://leader.mesos:5050/quota/`echo $role | sed 's/"//g'`;
  done

}

function test_hrole_updates {
  echo "${BOLD}"
  echo "********************************************************************************************"
  echo "* New subroles can be created.                                                             *"
  echo "********************************************************************************************"
  echo "${NORMAL}"

  start_agent
  cleanup
  MESOS_TASKS='{"tasks": []}' run_framework '["a"]'
  cleanup
  MESOS_TASKS='{"tasks": []}' run_framework '["a/b"]'
  cleanup

  TASKS='
  {
    "tasks": [{
      "role": "a/b/c",
      "task": {
        "command": { "value": "echo OK" },
        "name": "task",
        "task_id": { "value": "task" },
        "resources": [
        {
          "name": "cpus",
          "scalar": { "value": 0.5 },
          "type": "SCALAR"
        },
        {
          "name": "mem",
          "scalar": { "value": 48 },
          "type": "SCALAR"
        }
        ],
        "slave_id": { "value": "" }
      }
    }]
  }'
  MESOS_TASKS="${TASKS}" run_framework '["a/b/c"]'

  __atexit
}

# Multirole-phase I demos
# -----------------------

test_multirole_framework_registration
cleanup

test_fair_share
cleanup

test_reserved_resources
cleanup

test_quota
cleanup

test_framework_authz
cleanup


# # Multirole-phase II demos
# # ------------------------

test_failover
cleanup

# # Hierarchical roles demos
# # ------------------------

test_hrole_updates
cleanup

test_hrole_fairness
cleanup

test_hrole_quota_sum_rule
cleanup
