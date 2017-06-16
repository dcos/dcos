# Admin Router

Admin Router is an open-source NGINX configuration created by
Mesosphere that provides central authentication and proxy to DC/OS services
within the cluster.

<img src="docs/admin-router.png" alt="" width="100%" align="middle">

## Routes

Admin Router runs on both master and agent nodes, each with different configurations. From these NGINX config files, [Ngindox](https://github.com/karlkfi/ngindox) is used to generates swagger-like docs:

**Master Routes:**

- NGINX: [nginx.master.conf](nginx.master.conf)
- YAML: [docs/api/nginx.master.yaml](docs/api/nginx.master.yaml)
- HMTL: [docs/api/nginx.master.html](docs/api/nginx.master.html)
- Rendered: <https://rawgit.com/dcos/dcos/master/packages/adminrouter/extra/src/docs/api/nginx.master.html>

**Agent Routes:**

- NGINX: [nginx.agent.conf](nginx.agent.conf)
- YAML: [docs/api/nginx.agent.yaml](docs/api/nginx.agent.yaml)
- HMTL: [docs/api/nginx.agent.html](docs/api/nginx.agent.html)
- Rendered: <https://rawgit.com/dcos/dcos/master/packages/adminrouter/extra/src/docs/api/nginx.agent.html>

Use `make api-docs` to regenerate the YAML and HTML files.

Use `make check-api-docs` to validate that the YAML and HTML files are up to date.

## Ports summary
<img src="docs/admin-router-table.png" alt="" width="100%" align="middle">

## Repository structure

There are two Admin Router "flavours" residing in DC/OS repos:
  * Opensource version or `Open` in short
  * Enterprise version or `EE` in short

The `Open` version is the base on top of which `EE` version is built. `EE` is in
fact an overlay on top of `Open`, it re-uses some of its components.

### Complexity vs. code re-use
It is crucial to understand that the more generalised the AR repositories
are, the more complicated they will become. Increased complexity will result in
people making mistakes and/or situations where complex rules are violated in
favour of development speed and thus copypasting code. It's all about striking
the right balance so sometimes code *is* duplicated between repositories in order
to make it easier for contributors to work with repositories.

### Nginx includes
All AR code, both Lua and non-Lua, can be divided into following groups:

 * common code for masters and agents, both EE and Open
 * agent-specific code, both EE and Open
 * master-specific code, both EE and Open
 * Open-specific code, both agent and master
 * EE-specific code, both agent and master
 * EE agent specific code
 * EE master specific code
 * Open agent specific code
 * Open master specific code

on top of that, Nginx-specific configuration is divided into three sections:

 * main
 * http
 * server

This gives us in total 27 possible "buckets" for Nginx directives. The
differentiation between sections could be avoided if we decide to use some more
advanced templating but this would further complicate configuration and
make it more difficult for people to test, and develop AR on live clusters.

Directly from it, stems the idea how the NGINX includes can be structured:

* open:

```
includes
├── http
│   ├── agent.conf
│   ├── common.conf
│   ├── master.conf
│   └── open
│       ├── common.conf
│       └── master.conf
├── main
│   ├── common.conf
│   └── open
│       └── common.conf
├── server
│   ├── common.conf
│   ├── master.conf
│   └── open
│       ├── agent.conf
│       └── master.conf
├── snakeoil.crt
└── snakeoil.key
```

* ee:

```
includes
├── http
│   └── ee
│       ├── common.conf
│       └── master.conf
├── main
│   └── ee
│       └── common.conf
└── server
    └── ee
        ├── agent.conf
        ├── common.conf
        └── master.conf
```

All Nginx related configuration directives reside in the `includes` directory which
contains directories reflecting all the sections present in NGINX configuration
(http|main|server). Because they are always present, no
matter the flavour/server type, they are chosen as top-level directories
in the `includes` dir. The `common.conf`, `agent.conf` and `master.conf`
files are flavour-agnostic thus they reside in each section's main dir
and are present/included only in the Open AR repository. EE repository re-uses them
after being applied on top of the Open repository. Contents of each of the
files are as follows:
 * `common.conf` contains all the things that are common across all flavours
   and server types for given section
 * `agent.conf` contains all the things that are common for all agents across
   all flavours
 * `master.conf` contains all the things that are common for all masters across
   all flavours

Each section can have either `ee` or `open` directories, but never both. `ee`
directory is only present in EE repo, Open repository contains only `open` directories.
Contents of these directories may be as follows:
 * `common.conf` contains all the things that are common for given flavour, no
   matter the server type
 * `agent.conf` contains all the things that are common for agents in given
   flavour
 * `master.conf` contains all the things that are common for masters in given
   flavour

The order of includes is for the time being hard-coded in nginx.\*.conf files.
Within particular section though it does not matter that much as:
 * [nginx by default orders the imports while globbing](https://serverfault.com/questions/361134/nginx-includes-config-files-not-in-order)
 * location blocks *MUST NOT* rely on the order in which they appear
   in the config file and define matching rules precise enough to avoid ambiguity.

All the includes are bound together by `nginx.(master|agent).conf` files.
`nginx.master.conf` for `Open` master looks like at the time of writing:
```
include includes/main/common.conf;
include includes/main/open/common.conf;

http {
    include includes/http/common.conf;
    include includes/http/master.conf;
    include includes/http/open/common.conf;
    include includes/http/open/master.conf;

    server {
        server_name master.mesos leader.mesos;

        include includes/server/common.conf;
        include includes/server/master.conf;
        include includes/server/open/master.conf;

        include /opt/mesosphere/etc/adminrouter-listen-open.conf;
        include /opt/mesosphere/etc/adminrouter-upstreams-open.conf;
        include /opt/mesosphere/etc/adminrouter-tls.conf;
    }
}
```
and for the agent:
```
include includes/main/common.conf;
include includes/main/open/common.conf;

http {
    include includes/http/common.conf;
    include includes/http/agent.conf;
    include includes/http/open/common.conf;

    server {
        server_name agent.mesos;

        include includes/server/common.conf;
        include includes/server/open/agent.conf;

        include /opt/mesosphere/etc/adminrouter-listen-open.conf;
        include /opt/mesosphere/etc/adminrouter-tls.conf;
    }
}
```

### Enforcing code reuse
The EE repository contains only EE directories, all common/agent-common/master-common
code resides in Open repository. This way EE repository becomes an overlay on
top of Open. Only `nginx.(master|agent).conf` are overwritten while applying EE
repository on top of Open during DC/OS image build. EE DC/OS image build scripts
remove all open directories from the Open repository before applying EE repository on
top of it.

This is not a bulletproof solution for preventing code
duplication (developers can simply start putting copies of code to both
`open/` and `ee/` directories) but it makes it easier to reuse the
code and encourages good behaviours.

### Lua code deduplication
It is not strictly required to provide the same level of flexibility for Lua code
as it is the case for Nginx includes and thus it's possible to simplify the code
a bit. It is sufficient to just differentiate Lua code basing on the repository flavour.
Both agents and masters can share the same Lua code.

There are two possible reasons that may be preventing Lua code from being
shared:
* the same code is executed but with different call arguments. An example to
  this may be `auth.validate_jwt_or_exit()` function. In the Open it takes no arguments,
  in EE it takes more than one.
* the code differs between EE and open but shares some common libraries/functions.
  Great example for this is `auth.check_acl_or_exit()` which internally, among
  many other things, calls argument-less `auth.check_jwt_or_exit()`.

In order to address these issues, a couple of patterns were selected:
 * modules which have flavour-specific function arguments export argument-less
   functions for the NGINX configuration. They translate the original call into
   a call with correct arguments. This approach requires splitting the module into
   `ee.lua|open.lua|common.lua` parts which is described in next bullet point.
   Depending on the flavour, either `ee.lua` or `open.lua` is imported and correct
   argument-less function is used. This approach also enables to share some of
   the NGINX `location` blocks between flavours - `location` code is the same,
   even though the Lua code used by the block differs.
 * some libraries/functions are structured in a way that extracts parts common for
   both flavours and `ee/open` parts that are included only in EE and Open repos
   respectively. An example of this approach is auth library which is splitted
   into three parts:
    * `lib/auth/common.lua` - present only in Open repository, with functions
      shared by both EE and Open code.
    * `lib/auth/ee.lua` - present only in EE repository, with functions specific
      to EE that use boilerplate from lib/auth/common.lua.
    * `lib/auth/open.lua` - as above but for Open repository.
   `init_by_lua` OpenResty call in `includes/http/(open|ee)/common.conf` imports
   `auth.open` or `auth.ee` modules as auth respectively.  The module is registered in
   the global namespace so all other Lua code uses it. This approach also allows
   for some degree of code separation enforcement as Open lua libs are removed
   during EE repository apply.

A special case of the "same code path, different call arguments"
problem is when a module needs to be initialized differently depending
on the flavour. A great example of it is `cache.lua` module which in Open
does not require any extra authentication data. To solve it, modules are
required to provide `.init()` function which is returned by require
`<module-name>` statement. The init function accepts arguments which
reconfigure module instance according to the flavour requirements.

Modules that do not require any customization in regards of flavour are left
as-is/usually do not follow any of these patterns. It is possible to standardise
it, but it does not seem to be justified. For example:
 * `util.lua` directly exposes its functions as they are stateless and shared
   between both flavours
 * `lib/auth/open.lua` uses the `.init()` pattern in order to achive different
   behaviour depending on the flavour.

## Service Endpoints

Admin Router allows Marathon tasks to define custom service UI and HTTP endpoints, which are made available via `<dcos-cluster>/service/<service-name>`. This can be achieved by setting the following Marathon task labels:

```
"labels": {
    "DCOS_SERVICE_NAME": "service-name",
    "DCOS_SERVICE_PORT_INDEX": "0",
    "DCOS_SERVICE_SCHEME": "http"
  }
```

In this case `http://<dcos-cluster>/service/service-name` would be forwarded to the host running the task using the first port allocated to the task.

In order for the forwarding to work reliably across task failures, we recommend co-locating the endpoints with the task. This way, if the task is restarted on a potentially other host and with different ports, Admin Router will pick up the new labels and update the routing. NOTE: Due to caching there might be an up to 30-second delay until the new routing is working.

We would recommend having only a single task setting these labels for a given `service-name`.
In the case of multiple task instances with the same `service-name` label, Admin Router will pick one of the tasks instances deterministically, but this might make debugging issues more difficult.

The endpoint should only use relative links for links and referenced assets such as .js and .css files. This is due to the fact, that the linked resources will be reachable only in their relative location `<dcos-cluster>/services/<service-name><link>`.

Tasks running in nested [Marathon app groups](https://mesosphere.github.io/marathon/docs/application-groups.html) will be available only using their service name (i.e, `<dcos-cluster>/service/<service-name>`) and not considering the marathon app group name (i.e., `<dcos-cluster>/service/app-group/<service-name>`).

## Authorization and authentication

DC/OS uses JWT at the core of its authentication and authorization features and
Admin Router performs a vital role in facilitating it. Lots of services which
constitute DC/OS do not have their own authorizers and rely on Admin Router to
provide them with authn/authn+authz enforcement.

Authn and authz code differs considerably between Open Source and Enterprise
versions of Admin Router. This documentation focuses on describing common and
Open Source related code. For EE features documentation please consult
README.md in EE Admin Router repository.

### Authentication

For Admin Router to establish the identity of the subject issuing a
request, it looks for JWT token in the request. It may be present in following
places:
* request headers: client needs to set `Authorization` header with
  `token=<token payload>` value.
* client sets `dcos-acs-auth-cookie` cookie with the token payload as a value

In the case when both request header and the cookie is set, request header token takes
priority. Admin Router does not issue JWT tokens itself as this is the task of
the IAM service. Please consult DC/OS documentation for more details.

Currently, DC/OS uses/sets following mandatory claims:
* `uid` which is ID of the user/subject making the request as defined in IAM
* `exp` claim as defined in section 4.1.4 of RFC7519

If the JWT signature is valid and token has not expired, then uid claim is used
while communicating with IAM to make authz decisions.

The way tokens are validated is shared between EE and Open, with the only
difference being the signing algorithm used by the tokens. In case of Open it's
`HS256` and in case of EE: `RS256`

In case when authentication was not successful, Admin Router responds with 401
error page with `WWW-Authenticate` header set to authentication process type
that is required to finish the authn.

### Authorization

Open Source Admin Router performs authorization basing on the sole fact that
user identity was transferred to Open Source IAM. This is done in by checking if
the user with given `uid` extracted from JWT claim is present and active in the
IAM using the `do_authn_and_authz_or_exit` LUA auth module method.

### Parameter-less interface

Authz differs significantly between EE and Open Source Admin Router,
but the location blocks in `nginx.*.conf` files not necessarily. So to
be able to share as much code as possible between EE and Open, there has to be
a common interface for EE and Open LUA auth code that location blocks can use.

This is the reason why LUA code responsible for auth exposes thin
parameter-less wrappers around all the functions, for example:

```
res.access_lashupkey_endpoint = function()
    return res.do_authn_and_authz_or_exit()
end
```

This way by importing EE LUA auth module instead of Open, location block can
use EE features immediately without any extra reconfiguration and the
additional parameters that are required in EE are coded directly in the LUA
module.

More information about EE-Open code sharing and code layout that stems from it
can be found in `Code sharing` section of this readme.

## Caching

In order to serve some of the requests, Admin Router relies on the information
 that can be obtained from Marathon and  Mesos. This includes:
* Mesos agents - e.g. `/agent/.*` location
* Marathon leader - e.g. `/system/v1/leader/marathon/.*` location
* Tasks/Frameworks running in the cluster - e.g. `/service/.*` location

Due to scalability reasons, it's impossible to obtain this data on each and
every request to given endpoint as it will overload Mesos/Marathon. So
the idea was born to pre-fetch this data and store it in shared memory where
each NGINX worker process can access it.

### Architecture

Due to the nature of NGINX, there are some limitations when it comes to Lua
code that OpenResty can run. For example:
* threading is unavailable, it's recommended to use recursive timers (http://stackoverflow.com/a/19060625/145400) for asynchronous tasks
* it's impossible to hold back NGINX request processing machinery from within
  certain initialization hooks as workers work independently.
* Using ngx.timer API in `init_by_lua` is not possible because init_by_lua runs
  in the NGINX master process instead of the worker processes which does the
  real request processing, etc. (https://github.com/openresty/lua-nginx-module/issues/330#issuecomment-33622121)

So a decision was made to periodically poll Mesos and Marathon for relevant data
using recursive timers. There are two variables that control this behaviour:
* `CACHE_FIRST_POLL_DELAY` - first poll for Mesos and Marathon occurs after this
  amount of time passed since worker initialization
* `CACHE_POLL_PERIOD` - after the first poll is done, every other is scheduled
  every this number of seconds.
Obviously `CACHE_FIRST_POLL_DELAY` should be much smaller than `CACHE_POLL_PERIOD`.

Cache refresh can also be triggered by a request coming in during
<0, `CACHE_FIRST_POLL_DELAY`> period. In this case, cache refresh will not occur
during the `CACHE_FIRST_POLL_DELAY` timer execution as the contents of the
shared memory will still be considered fresh.

### Cache timers

The `freshness` of the cache is governed by few variables:
* `CACHE_EXPIRATION` - if the age of the cached data is smaller than
  `CACHE_EXPIRATION` seconds, then the cache refresh will not occur if it's
  ngx.timer context and request processing code will use the data stored in shared memory.
* `CACHE_MAX_AGE_SOFT_LIMIT` - between `CACHE_EXPIRATION` seconds and
  `CACHE_MAX_AGE_SOFT_LIMIT` seconds, cache is still considered "usable" in
  request context, but the ngx.timer context will try to update it with fresh
  data fetched from Mesos and Marathon
* `CACHE_MAX_AGE_HARD_LIMIT` - between `CACHE_MAX_AGE_SOFT_LIMIT` and
  `CACHE_MAX_AGE_HARD_LIMIT` cache is still usable in request context, but
  with each access to it, a warning message is written to the NGINX log.
  Timer context will try to update the cache.
* beyond `CACHE_MAX_AGE_HARD_LIMIT` age, cache is considered unusable and
  every request made to the location that uses it will fail with 503 status.

The relation between these is:
`CACHE_EXPIRATION` < `CACHE_MAX_AGE_SOFT_LIMIT` << `CACHE_MAX_AGE_HARD_LIMIT`

The reason why we put `<<` in front of `CACHE_MAX_AGE_HARD_LIMIT` is to make
the cache a bit of a "best-effort" one - In the case when Mesos and/or Marathon
dies, the cache should still be able to serve data for a reasonable amount of time
and thus give the operator some time to solve the underlying issue. For example
Mesos tasks do not move that often and the data stored in NGINX should still be
usable, at least partially.

### Locking and error handling

Each worker tries to perform cache updates independently. On top of that during
the early stage of Admin Router operation, a request can trigger the update as
well. In order to coordinate it, locking was introduced.

There are two different locking behaviours, depending on the context from which
the update was triggered:
* for timer-based refreshes, the lock is non-blocking. If there is an update already
  in progress, execution is aborted, and next timer-based refresh is scheduled.
* in case of request-triggered update, lock is blocking and the lock timeout
  is equal to `CACHE_REFRESH_LOCK_TIMEOUT` seconds. This way, during
  `<0, CACHE_FIRST_POLL_DELAY>` period, requests are queued while waiting for the
  first, refresh to succeed.

Request to Mesos/Marathon can take at most `CACHE_BACKEND_REQUEST_TIMEOUT` seconds.
After that, the request is considered failed, and it is retried during the next
update.

Worth noting is that NGINX reload resets all the timers. Cache is left intact
though.

## Testing

Admin Router repository includes a test harness that is meant to make
testing easier and in some cases - possible. It's written in Python and
uses pytest fixtures and custom modules to mock out all relevant DC/OS
features and control NGINX startup and termination.

All the tests are executed in a Docker container which is controlled by the
Makefile. Inside the container pytest command is started which in turn pulls
in all the relevant fixtures, such as Syslog mock, mocker (DC/OS endpoints
mock), DNS mock, etc... Finally, an NGINX is spawned using the configuration
bind-mounted from the developer's repository. Tests may launch NGINX multiple
times, in different configurations, depending on what is needed. After the
tests runner finishes, all the processes and the environment is cleaned up
by pytest.

Below, there is a general overview of all the components of the test harness.
More detailed documentation can be found in docstrings and comments in the code
itself. If in doubt, it also may be very helpful to look for examples among
existing tests.

### Quickstart
To execute all the tests, just issue:

	make test

In order have fine-grained control over the pytest command, execute:

	make shell

This command will launch an interactive environment inside the container that
has all the dependencies installed. The developer may now run the `pytest`
command as need, debug the environment and temporarily add/change
the dependencies.

### Makefile
Makefile provides an easy way to start the testing environment without the need
to worry about the correct docker commands. Its core concept is `adminrouter-devkit`
container which is contains all the dependencies that are needed to run
Admin Router, and inside which all tests-related commands are run.

It exposes a couple of targets:
* `make clean` - remove all containers created by the test harness. It does not
  remove the images themselves though as the layer cache may be useful later
  on and the user may remove them themselves.
* `make devkit` - creates the `adminrouter-devkit` container. By default other
   targets execute this step automatically if devkit container image does not
   exist yet.
* `make update-devkit` - updates `adminrouter-devkit`. Should be run every time
   the Dockerfile or its dependencies change.
* `make tests` - launch all the tests. Worth noting is the fact that McCabe
   complexity of the code is also verified, and an error is raised if it's
   equal to or above 10.
* `make shell` - launch an interactive shell within the devkit container. Should
  be used when fine grained control of the tests is necessary or during debugging.
* `make flake8` - launch flake8 which will check all the tests and test-harness
  files by default.

### Docker container
As mentioned earlier, all the commands are executed inside the `adminrouter-devkit`
container. It follows the same build process for NGINX that happens during
DC/OS build with the exception of setting the  `--with-debug` flag. It also
contains some basic debugging tools, pytest related dependencies and
files that help pytest mimic the DC/OS environment. Their location is then
exported via environment variables to the pytest code, so changing their location
can be done by edition only the Dockerfile.

Due to some issues with overlayfs on older kernels, the container links
/tmp directory to /dev/shm.

### Repository flavours
Admin Router repository can come in two variants/flavours - Enterprise and Opensource.
Tests determine it basing on the directory structure - if tests contain
`test-harness/tests/open/` directory then the repo is treated as Opensource one,
and in case when `test-harness/tests/ee/` directory is present - as the
enterprise one. Pytest fixture `repo_is_ee` takes care of it and is pulled in
as dependencies by all the fixtures that need this information.

### Service startup ordering and cleanup
Mocking out DC/OS is a complex task, and a huge part in it have pytest
fixtures. They take care of proper ordering of mocks and subprocess start/stop and
cleanup and the cleanup ordering itself.

Tracking the chain of fixtures and how they use each other may provide better
understanding of how the test harness works.

### JWT
DC/OS IAM relies on JSON Web Tokens for transmitting security information between DC/OS
components. Open repository flavour uses HS256 tokens, while EE relies on RS256.
Test harness needs to have a way to create them for use in the tests. This is
done by `test-harness/modules/mocker/jwt.py` module, which together with
`repo_is_ee` fixture provides abstracts away the type of the
token used by Admin Router itself.

### Mocker
Mocker takes care of simulating DC/OS HTTP endpoints that Admin Router uses. It's
basically just a thin management layer on top of multiple python-based
HTTP servers, each one of them mocking out particular component/upstream of DC/OS.

It exposes the `.send_command()` method that allows to reconfigure endpoints
the way the tests need it. It calls a getattr on the endpoint
instance to execute the given function and pass it attributes as specified
by the `.send_command()` call arguments. Please see the function signature in
the file `test-harness/modules/mocker/common.py` for details.

#### Endpoints
Endpoints are threading HTTP servers based on http.server python module. Because
of the fact that there are many different kinds of endpoints that need to be
employed by mocker, and that there is a lot of shared behaviour between them,
they follow inheritance tree as below:

<img src="docs/endpoint_class_hierarchy.png" alt="" width="100%" align="middle">

* `ReflectingUnixSocketEndpoint`, `ReflectingTCPIPEndpoint`: both of them send back
  the request data in the response body to the client for inspection. The only
  difference between them is that the former is listening on Unix Socket
  and the latter is listening on TCP/IP socket. They are useful for very simple
  tests that only check if the request is hitting the right upstream and the
  headers are correct.
* `IAMEndpoint`, `MarathonEndpoint`, `MesosEndpoint`: specialized endpoints that
  are mimicking IAM, Marathon and Mesos respectively. Apart from the basic
  functionality (reset, bork, etc...), they are also capable of recording requests
  sent to them, and then returning them through mockers `send_command` back to the
  tests code.
* all remaining endpoints depicted in the hierarchy are not directly usable but
  can be inherited from and extended if necessary for the purposes of testing.

Each endpoint has an id, that it basically it's http address (i.e.
`http://127.0.0.1:8080` or `http:///run/dcos/dcos-metrics-agent.sock`). It's
available via the `.id()` method. They are started and stopped via `.start()`
and `.stop()` methods during the start and stop of mocker instance
respectively. Each endpoint can be set to respond to each and every request
with an error (`500 Internal server error`).

#### DNS mock

The AR requires a working DNS server that responds correctly to the following
queries:

* `leader.mesos` - `A`: current Mesos leader instance
* `master.mesos` - `A`: any Mesos master instance
* `agent.mesos` - `A`: any Mesos agent
* `slave.mesos` - `A`: any Mesos agent

Mocking library comes with a simple DNS in-memory programmable server that
can be used to mock various DNS query responses and also to simulate leader
instance changes.

#### Subprocess management
Pytest fixture starts an `Admin Router` subprocess.

The subprocess doesn't always log to stderr/stdout, so a very simple syslog mock
is also provided. All the stdouts and stderrs are piped into the central log
processing class LogCatcher.

##### LogCatcher
As mentioned in the previous paragraph, all the stdout/stderr file descriptors
and syslog messages are piped into this class. It uses `poll()` call to monitor
all the sources for new information and push it into:
* standard python logging module
* logs located in `test-harness/logs/`
* internal buffer which can be used by tests for logging-based testing

The internal buffer is available through
`stdout_line_buffer`/`stderr_line_buffer` methods of AR object and Syslog
object(available through a fixture). The buffer itself is implemented as a
plain python list where each log line represents a single entry. This list is
shared across all the objects that are groking the buffer, and there is no
extra protection from manipulating it from within tests so extra care needs
to be taken.

In order to simplify handling of the log lines buffers, `LineBufferFilter` class
has been created. It exposes two interfaces:
* context manager that allows for groking the buffer entries that were created
  while executing the context:

  ```
    filter_regexp = 'validate_jwt_or_exit\(\): User not found: `{}`'.format(uid)
    lbf = LineBufferFilter(filter_regexp,
                           line_buffer=master_ar_process.stderr_line_buffer)
    with lbf:
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=header)
    assert lbf.extra_matches == {}

  ```
* `scan_log_buffer()` method that scans all the entries, since the subprocess
  start.
  ```
    filter_regexp = 'Secret key not set or empty string.'

    lbf = LineBufferFilter(filter_regexp,
                           line_buffer=ar_process_without_secret_key.stderr_line_buffer)

    lbf.scan_log_buffer()

    assert lbf.extra_matches == {}

  ```
Separation of the log entries stemming from different instances of a given
Subprocess class in the logfile is done by placing the following line in the log
file:
```
✄✄✄✄✄✄✄✄✄✄ Logging of this instance ends here ✄✄✄✄✄✄✄✄✄✄

```

##### Syslog mock
Syslog mock is a very simple Python hack - a DGRAM Unix Socket is created and
added to LogWatcher. LogWatcher itself takes care of draining data from it,
with the line length limit hard-coded to 4096 bytes.

##### NGINX
The NGINX subprocess is different from others in regard to its lifetime. Pytest
fixture that pulls it into the test is module-scoped by default. If there is a
need to have custom lifetime or just single-test scoped lifetime, then it's
necessary to use `nginx_class` fixture instead of simple `master_ar_process` or
`agent_ar_process` ones.

NGINX instances have the `.make_url_from_path` method which is a convenient way
to generate AR URLs for tests. It uses exhibitor endpoint as it's present in
all DC/OS configurations and uses auth features as well.

#### pytest tests
Directly from the fact that Admin Router subprocess fixture is module scoped,
stems some of the current structure of the tests directory. There are three
different files where tests reside:
* `test_agent.py`: all the tests related to agent Admin Router, which do not
  require custom AR fixtures
* `test_master.py`: all the tests related to master Admin Router, which do not
  require custom AR fixtures
* `test_boot_envvars.py`: tests that verify adminrouter startup variables

`test_agent.py` and `test_master.py` may be splitted apart into smaller units,
but with each unit an extra start and stop of AR master or agent is required.
This slows down the tests. Running session-scoped AR is impossible. For now,
each endpoint has tests grouped on class level.

Test files are grouped into repository flavour directories, which
group the tests that are specific for given version:
* `test-harness/modules/ee/test_*.py` for Enterprise
* `test-harness/modules/open/test_*.py` for Open
* `test-harness/tests/test_*.py` common for both variants

#### Tooling
Code uses some extra tooling in order to enforce coding standards.

Currently it's only `isort` together with flake8-isort plugin. In order to
properly distinguish between 2nd party and 3rd party modules, the `.isort.cfg`
file lists all local modules in `known_first_party` config parameter.

#### Debugging threads-related issues
The fixtures, mocks, and all other features make the code heavily threaded. In
order to simplify debugging a special signal handler is installed. It launches a
pdb sessions when USR1 signal is received.

Code also relies on thread safety/atomicity of some of Python's
expressions/statements:

    https://docs.python.org/3.6/faq/library.html#what-kinds-of-global-value-mutation-are-thread-safe

This is why the context of each endpont is not protected by locks, in
case when it's only about fetching a single value from context dict or
storing/appending one there.
