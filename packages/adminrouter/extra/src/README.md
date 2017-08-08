# Admin Router

Admin Router is an open-source NGINX configuration created by
Mesosphere that provides central authentication and proxy to DC/OS services
within the cluster.

<img src="docs/admin-router.png" alt="" width="100%" align="middle">

## Routes

Admin Router runs on both master and agent nodes, each with different NGINX
configurations. From these NGINX config files,
[ngindox](https://github.com/karlkfi/ngindox) is used to generates Swagger-like
documentation:

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


## Endpoints documentation

All Admin Router endpoints are documented using the
[ngindox](https://github.com/karlkfi/ngindox) tool, which uses specially
formatted comments in order to describe endpoint configurations, and
automatically parses them into HTML documents. Please check the project's
documentation for more details.

Admin Router's CI automatically checks if the endpoint documentation generated
using `ngindox` and embedded into the repository is up to date. If not, the CI
job fails and the user needs to regenerate the docs and re-submit the PR.

The check is done by generating the documentation during the build stage.
If, after the `ngindox` run, `git` detects uncommitted changes, then this means
that the Admin Router configuration differs from the HTML documents that
are committed into repository. This is done using `make check-api-docs` target.

In order to regenerate the documentation files, one needs to execute the
`make api-docs` target and commit the changes into the repository.

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

### NGINX includes
All AR code, both Lua and non-Lua, can be divided into the following groups:

 * common code for masters and agents, both EE and Open
 * agent-specific code, both EE and Open
 * master-specific code, both EE and Open
 * Open-specific code, both agent and master
 * EE-specific code, both agent and master
 * EE agent specific code
 * EE master specific code
 * Open agent specific code
 * Open master specific code

on top of that, NGINX-specific configuration is divided into three sections:

 * main
 * http
 * server

This gives us in total 27 possible "buckets" for NGINX directives. The
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

All the NGINX related configuration directives reside in the `includes`
directory which contains directories reflecting all the sections present in
NGINX configuration (http|main|server). Because they are always present, no
matter the flavour/server type, they are chosen as top-level directories in the
`includes` directory. The `common.conf`, `agent.conf` and `master.conf` files
are flavour-agnostic, thus they reside in each section's main directory and are
present only in the Open DC/OS repository. The EE repository re-uses them after
being applied on top of the Open DC/OS repository. Contents of each of the
files are as follows:
 * `common.conf` contains all the things that are common across all flavours
   and server types for given section
 * `agent.conf` contains all the things that are common for all agents across
   all flavours
 * `master.conf` contains all the things that are common for all masters across
   all flavours

Each section can have either `ee` or `open` directories, but never both. `ee`
directory is only present in EE repository, Open repository contains only `open`
directories. Contents of these directories may be as follows:
 * `common.conf` contains all the things that are common for given flavour, no
   matter the server type
 * `agent.conf` contains all the things that are common for agents in given
   flavour
 * `master.conf` contains all the things that are common for masters in given
   flavour

The order of includes is for the time being hard-coded in `nginx.\*.conf` files.
Within particular section though it does not matter that much as:
 * [nginx by default orders the imports while globing](https://serverfault.com/questions/361134/nginx-includes-config-files-not-in-order)
 * location blocks *MUST NOT* rely on the order in which they appear in the
   config file and define matching rules precise enough to avoid ambiguity.

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
The EE repository contains only EE directories, all
common/agent-common/master-common code resides in Open repository. This way EE
repository becomes an overlay on top of Open. Only `nginx.(master|agent).conf`
are overwritten while applying EE repository on top of Open during DC/OS image
build. EE DC/OS image build scripts remove all open directories from the Open
repository before applying the EE repository on top of it.

This is not a bulletproof solution for preventing code
duplication (developers can simply start putting copies of code to both
`open/` and `ee/` directories) but it makes it easier to reuse the
code and encourages good behaviours.

### Lua code deduplication
It is not required to provide the same level of flexibility for Lua code as it
is the case for NGINX includes and thus it's possible to simplify the code a
bit. It is sufficient to just differentiate Lua code basing on the repository
flavour.  Both agents and masters can share the same Lua code.

There are two possible reasons that may be preventing Lua code from being
shared:
* the same code is executed but with different call arguments. An example to
  this may be `auth.validate_jwt_or_exit()` function. In the Open repository it
  takes no arguments, in EE it takes more than one.
* the code differs between EE and open but shares some common libraries/functions.
  Great example for this is `auth.check_acl_or_exit()` which internally, among
  many other things, calls argument-less `auth.check_jwt_or_exit()`.

In order to address these issues, a couple of patterns were selected:
 * modules which have flavour-specific function arguments export argument-less
   functions for the NGINX configuration. They translate the original call into
   a call with correct arguments. This approach requires splitting the module
   into `ee.lua|open.lua|common.lua` parts which is described in the next
   bullet point.  Depending on the flavour, either `ee.lua` or `open.lua` is
   imported and the correct argument-less function is used. This approach also
   enables to share some of the NGINX `location` blocks between flavours -
   `location` code is the same, even though the Lua code used by the block
   differs.
 * some libraries/functions are structured in a way that extracts parts common
   among both flavours and `ee/open` parts that are included only in EE and
   Open repos respectively. An example of this approach is `auth.lua` library
   which is splitted into three parts:
    * `lib/auth/common.lua` - present only in Open repository, with functions
      shared by both EE and Open code.
    * `lib/auth/ee.lua` - present only in EE repository, with functions specific
      to EE that use boilerplate from lib/auth/common.lua.
    * `lib/auth/open.lua` - as above but for Open repository.
   `init_by_lua` OpenResty call in `includes/http/(open|ee)/common.conf`
   imports `auth.open` or `auth.ee` modules as auth respectively.  The module
   is registered in the global namespace so all other Lua code uses it. This
   approach also allows for some degree of code separation enforcement as lua
   libs from Open DC/OS repository are removed during the application of EE
   DC/OS repository.

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
 * `lib/auth/open.lua` uses the `.init()` pattern in order to achieve different
   behaviour depending on the flavour.

## Service Endpoint
Admin Router offers the `/service` endpoint which enables users to easily
access some of the tasks launched on DC/OS. AR internally pre-fetches data from
Mesos and root Marathon and stores it in the internal cache for later use when
routing an incoming request.

Marathon tasks can be accessed by application ID, Mesos frameworks can be
accessed by application ID or by framework ID. For example - let's deploy a
SchmetterlingDB framework with application ID of
`/group1/group2/schmetterlingA`. It will be accessible using its framework ID
(let's assume that Mesos assigned it a framework ID of
`819aed93-4143-4291-8ced-5afb5c726803-0000`):
```
/service/819aed93-4143-4291-8ced-5afb5c726803-0000/
```
and using its application ID:
```
/service/group1/group2/schmetterlingA/
```

The `/service` endpoint supports WebSockets. By default, it disables NGINX
request and response buffering. All redirects from services are rewritten in
order to support the `/service` URL path prefix clients are using.

### Intended use
It is important to remember that the `/service` endpoint was designed to work
with root Marathon only. Tasks launched by Marathon-on-Marathon instances will
not be reachable via it.

In the case of Mesos frameworks, this becomes a bit more complex - all the
frameworks are visible in Mesos' `/state-summary` endpoint output so in theory
it is possible to access a framework launched using Marathon-on-Marathon or by
hand.  Unfortunately, Mesos as of now does not enforce framework name
uniqueness and thus it is possible to launch multiple frameworks with the same
name. AR in such case will route in a non-deterministic manner. Root Marathon
by default enforces unique names for all the tasks and frameworks it has under
control.

Please check the [Limitations](#limitations) section for more details.

### Operation
Under the hood, the `/service` endpoint implementation uses non-trivial logic in
order to resolve the cluster-internal socket address to route the HTTP request
to.

#### Iterative resolving
There is no way to tell which part of the path is the application ID and
which one is just a resource address. For example, assuming that the request
path is `/foo/bar/baz/picture.jpg` we can have:
* application ID: `foo`, resource address: `/bar/baz/picture.jpg`
* application ID: `foo/bar`, resource address: `/baz/picture.jpg`
* application ID: `foo/bar/baz`, resource address: `/picture.jpg`
* application ID: `foo/bar/baz/picture.jpg`, resource address: `/`

So the algorithm iteratively tries to resolve each "candidate" namespace and
name and assumes that first-match wins.

Assuming that we deployed an NGINX task with application ID `foo/bar`, we will
see two iterations:
* The first one with `foo` candidate application ID, which is not present in
  the cluster
* The second one with `foo/bar` candidate application ID, which results in the
  request being routed to the correct backend. In the case when user is trying
  to access a non-existent service, there are going to be four iterations, each
  one unsuccessful. After the fourth one the code will give up.

There is a limit on the number of iterations that AR makes. At the time of
writing, it is set to `10`. This means that an application ID cannot nest more
than ten times and that everything after the tenth segment is always treated as
a resource component.

#### Resolving individual components
During each iteration described in [previous paragraph](#iterative-resolving),
AR tries to resolve the component using the data stored in the cache and if
necessary - from MesosDNS:
* first step is to:
  * check if a root Marathon task has the following labels set:
    * `DCOS_SERVICE_NAME` label contents is equal to given application ID string
    * `DCOS_SERVICE_SCHEME` label is set
    * `DCOS_SERVICE_PORT_INDEX` label is set
  * task is in the state `TASK_RUNNING`.
  If all the conditions are met then the request is routed using root Marathon
  data. Please check the [section below](#recommended-way-to-expose-services)
  for details on the meaning of these labels.
* if the name of the service couldn't be resolved using root Marathon data, AR
  scans the list of Mesos frameworks in search for the one with either
  framework ID (higher priority) or framework name(lower priority) equal to
  application ID string. If found, the next steps depend on the value of
  `webui_url` field:
  * field contains an empty string - algorithm tries to resolve the application
    ID using MesosDNS
  * field is `null` - resolving process for given application ID ends, MesosDNS
    step is NOT executed
  * field contains a valid address - request is proxied to the address pointed
    by the field contents
* resolving via MesosDNS relies on issuing an HTTP SRV query to MesosDNS. For
  application ID string equal to `foo/bar/baz`, the request that is going to be
  made to MesosDNS is:
  ```
  http://localhost:8123/baz.bar.foo._tcp.marathon.mesos
  ```
  In the case where MesosDNS returns no results, AR assumes that there is no
  task nor framework with the given application ID running on DC/OS.

#### Stale cache/broken cache cases
The `/service` endpoint internally uses the AR cache, so a failure to refresh
the cache has the same effects on the `/service` endpoint like any other
endpoint. Please check the [Cache timers](#cache-timers) section for details.

The thing worth remembering though, is that this endpoint uses more than one
cache entry. Because of that, if for example root Marathon fails, and Mesos is
fine, requests will not be routed. This is because there has to be a strict
priority enforcement, and without root Marathon, it is impossible to decide
whether AR should use Mesos data or not and request routing becomes ambiguous.
The reverse is possible though - a failed Mesos cache update will not prevent
requests from being routed as long as they can be handled *only* using Marathon
data.

### Limitations
Apart from the one mentioned earlier - that the `/service` endpoint should be
routing only to the tasks launched by root Marathon, there is one more
limitation that needs to be kept in mind.

To properly remove a framework, a cleanup procedure needs to be followed:
* the framework needs to be removed from root Marathon
* it needs to be unregistered with Mesos
* ZooKeeper state has to be cleaned up
* Mesos reservations (if any), need to be deleted

Without this cleanup, the Mesos framework will still be present in the output of
`/state-summary` endpoint and thus Admin Router will try to route it instead of
simply replying with a 404. It is impossible for AR to differentiate between
frameworks that:
* have been removed by root Marathon
* become disconnected from Mesos for some reason, but *MAY* come back at some
  point

What is more - continuous installation and removal of a framework using the same
name will cause Mesos to keep entries for them in `/state-summary`. There is no
enforcement of unique framework names, and thus AR will try to route to one of
the frameworks (not necessarily the one that is *really* alive) in an undefined
manner.

Until unique service names are implemented, or a proper cleanup is done by the
client, a workaround is to launch frameworks always with a different name, for
example:
* `/hello-world-1`
* `/hello-world-2`
* `/hello-world-3`
* `/hello-world-4`
* ...

### Recommended way to expose services
Admin Router allows Marathon tasks to define custom service UI and HTTP
endpoints, which are made available via `<dcos-cluster>/service/<application ID>`.
This can be achieved by setting the following Marathon task labels:

```
"labels": { "DCOS_SERVICE_NAME": "application ID", "DCOS_SERVICE_PORT_INDEX": "0", "DCOS_SERVICE_SCHEME": "http" }
```

When your container/task has its own IP (typically when running in a virtual
network), `http://<dcos-cluster>/service/<application ID>` is forwarded to the
container/task's IP using one of the ports in the port mapping or port
definition when USER networking is enabled or one of the discovery ports
otherwise. When your task/container is mapped to the host, it is forwarded to
the host running the task using the one of the ports allocated to the task.
The chosen port is defined by the `DCOS_SERVICE_PORT_INDEX` label.

In order for the forwarding to work reliably across task failures, we recommend
co-locating the endpoints with the task. This way, if the task is restarted on
a potentially different host and with different ports, Admin Router will pick
up the new labels and update the routing. Due to caching there might be an up
to 30-second delay before the new routing is working.

We recommend having only a single task setting these labels for a given
application ID. In the case of multiple task instances with the same
application ID label, Admin Router will pick one of the task instances
deterministically, but this might make debugging issues more difficult.

The endpoint should only use relative links for links and referenced assets such
as `.js` and `.css` files. This is due to the fact that the linked resources will
be reachable only in their relative location
`<dcos-cluster>/services/<application ID><link>`.

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

For Admin Router to establish the identity of the subject issuing a request, it
looks for JWT in the request. It may be present in the following places:
* request headers: client needs to set `Authorization` header with
  `token=<token payload>` value.
* client sets `dcos-acs-auth-cookie` cookie with the token payload as a value

In the case when both request header and the cookie is set, request header
token takes priority. Admin Router does not issue JWT itself as this is
the task of the IAM service. Please consult DC/OS documentation for more
details.

Currently, DC/OS uses/sets the following mandatory claims:
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
  ngx.timer context and request processing code will use the data stored in
  shared memory.
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
dies, the cache should still be able to serve data for a reasonable amount of
time and thus give the operator some time to solve the underlying issue. For
example Mesos tasks do not move that often and the data stored in NGINX should
still be usable, at least partially.

### Locking and error handling

Each worker tries to perform cache updates independently. On top of that during
the early stage of Admin Router operation, a request can trigger the update as
well. In order to coordinate it, locking was introduced.

There are two different locking behaviours, depending on the context from which
the update was triggered:
* for timer-based refreshes, the lock is non-blocking. If there is an update
  already in progress, execution is aborted, and next timer-based refresh is
  scheduled.
* in case of request-triggered update, lock is blocking and the lock timeout is
  equal to `CACHE_REFRESH_LOCK_TIMEOUT` seconds. This way, during `<0,
  CACHE_FIRST_POLL_DELAY>` period, requests are queued while waiting for the
  first, refresh to succeed.

Request to Mesos/Marathon can take at most `CACHE_BACKEND_REQUEST_TIMEOUT`
seconds.  After that, the request is considered failed, and it is retried
during the next update.

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
itself.

### Running tests
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
to worry about the correct docker commands. Its core concept is
`adminrouter-devkit` container which is contains all the dependencies that are
needed to run Admin Router, and inside which all tests-related commands are
run.

It exposes a couple of targets:
* `make clean` - remove all containers created by the test harness. It does not
  remove the images themselves though as the layer cache may be useful later
  on and the user may remove them themselves.
* `make devkit` - creates the `adminrouter-devkit` container. By default other
  targets execute this step automatically if the devkit container image does not
  exist yet.
* `make update-devkit` - updates `adminrouter-devkit`. This should be run every
  time the Dockerfile or its dependencies (e.g. requirements.txt fields)
  change.
* `make tests` - launch all the tests. Worth noting is the fact that McCabe
  complexity of the code is also verified, and an error is raised if it's
  equal to or above 10.
* `make shell` - launch an interactive shell within the devkit container. Should
  be used when fine grained control of the tests is necessary or during debugging.
* `make lint` - launch linters which will check the tests code and test-harness
  code by default.

### Docker container
As mentioned earlier, all the commands are executed inside the
`adminrouter-devkit` container. It follows the same build process for NGINX
that happens during DC/OS build with the exception of setting the
`--with-debug` flag. It also contains some basic debugging tools, pytest
related dependencies and files that help pytest mimic the DC/OS environment.
Their location is then exported via environment variables to the pytest code,
so changing their location can be done by edition only the Dockerfile.

### Repository flavours
Admin Router repository can come in two variants/flavours - Enterprise and
Opensource.  Tests determine it basing on the directory structure - if tests
contain `test-harness/tests/open/` directory then the repo is treated as
Opensource one, and in case when `test-harness/tests/ee/` directory is present
- as the enterprise one. Pytest fixture `repo_is_ee` takes care of it and is
pulled in as dependencies by all the fixtures that need this information.

### Service startup ordering and cleanup
Mocking out DC/OS is a complex task, and a huge part in it have pytest
fixtures. They take care of proper ordering of mocks and subprocess start/stop and
cleanup and the cleanup ordering itself.

Tracking the chain of fixtures and how they use each other may provide better
understanding of how the test harness works.

### JWT
The DC/OS IAM relies on JSON Web Tokens (JWTs) for transmitting authentication
data between DC/OS components. Open repository flavour uses JWTs of type HS256,
while EE relies on JWTs of type RS256. Test harness needs to have a way to
create them for use in the tests. This is done by
`test-harness/modules/mocker/jwt.py` module, which together with the
`repo_is_ee` fixture, provides abstracts away the type of the token used by
Admin Router itself.

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
  NGINX upstream request headers are correct.
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
shared across all the objects that are grokking the buffer, and there is no
extra protection from manipulating it from within tests so extra care needs
to be taken.

In order to simplify handling of the log lines buffers, `LineBufferFilter` class
has been created. It exposes two interfaces:
* context manager that allows for grokking the buffer entries that were created
  while executing the context:

  ```python
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
  ```python
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
need to have custom lifetime, then it's necessary to use `nginx_class`
fixture which provides maximum flexibility.

NGINX instances have the `.make_url_from_path` method which is a convenient way
to generate AR URLs for tests. Users do not have to worry whether this is an
agent or master instance nor know the TCP port that given instance listens on.

#### AR instance reuse
Some of the tests can share the same AR instance as it is not being mutated by
them. There are currently at least three files which contain tests which share
AR instance:
* `test_agent.py`: all the tests related to agent Admin Router, which do not
  require custom AR fixtures
* `test_master.py`: all the tests related to master Admin Router, which do not
  require custom AR fixtures
* `test_boot_envvars.py`: tests that verify Admin Router's startup variables

`test_agent.py` and `test_master.py` may be splitted apart into smaller units,
but with each unit an extra start and stop of AR master or agent is required.
This slows down the tests so a compromise has been made and per-class and
per-test AR instances are launched only if necessary.

#### pytest tests
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

This is why the context of each endpoint is not protected by locks, in
case when it's only about fetching a single value from context dict or
storing/appending one there.
