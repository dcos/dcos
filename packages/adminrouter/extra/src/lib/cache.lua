local cjson_safe = require "cjson.safe"
local shmlock = require "resty.lock"
local http = require "resty.http"
local resolver = require "resty.resolver"
local util = require "util"

-- In order to make caching code testable, these constants need to be
-- configurable/exposed through env vars.
--
-- Values assigned to these variable need to fulfil following condition:
--
-- CACHE_FIRST_POLL_DELAY << CACHE_EXPIRATION < CACHE_POLL_PERIOD < CACHE_MAX_AGE_SOFT_LIMIT < CACHE_MAX_AGE_HARD_LIMIT
--
-- There are 3 requests (2xMarathon + Mesos) made to upstream components.
-- The cache should be kept locked for the whole time until
-- the responses are received from all the components. Therefore,
-- 3 * (CACHE_BACKEND_REQUEST_TIMEOUT + 2) <= CACHE_REFRESH_LOCK_TIMEOUT
-- The 2s delay between requests is choosen arbitrarily.
-- On the other hand, the documentation
-- (https://github.com/openresty/lua-resty-lock#new) says that the
-- CACHE_REFRESH_LOCK_TIMEOUT should not exceed the expiration time, which
-- is equal to 3 * (CACHE_BACKEND_REQUEST_TIMEOUT + 2). Taking into account
-- both constraints, we would have to set CACHE_REFRESH_LOCK_TIMEOUT =
-- 3 * (CACHE_BACKEND_REQUEST_TIMEOUT + 2). We set it to
-- 3 * CACHE_BACKEND_REQUEST_TIMEOUT hoping that the 2 requests to Marathon and
-- 1 request to Mesos will be done immediately one after another.
-- Before changing CACHE_POLL_INTERVAL, please check the comment for resolver
-- CACHE_BACKEND_REQUEST_TIMEOUT << CACHE_REFRESH_LOCK_TIMEOUT
--
-- Before changing CACHE_POLL_PERIOD, please check the comment for resolver
-- statement configuration in includes/http/master.conf
--
-- Initial timer-triggered cache update early after nginx startup:
-- It makes sense to have this initial timer-triggered cache
-- update _early_ after nginx startup at all, and it makes sense to make it
-- very early, so that we reduce the likelihood for an HTTP request to be slowed
-- down when it is incoming _before_ the normally scheduled periodic cache
-- update (example: the HTTP request comes in 15 seconds after nginx startup,
-- and the first regular timer-triggered cache update is triggered only 25
-- seconds after nginx startup).
--
-- It makes sense to have this time window not be too narrow, especially not
-- close to 0 seconds: under a lot of load there *will* be HTTP requests
-- incoming before the initial timer-triggered update, even if the first
-- timer callback is scheduled to be executed after 0 seconds.
-- There is code in place for handling these HTTP requests, and that code path
-- must be kept explicit, regularly exercised, and well-tested. There is a test
-- harness test that tests/exercises it, but it overrides the default values
-- with the ones that allow for testability. So the idea is that we leave
-- initial update scheduled after 2 seconds, as opposed to 0 seconds.
--
-- All are in units of seconds. Below are the defaults:
local _CONFIG = {}
local env_vars = {CACHE_FIRST_POLL_DELAY = 2,
                  CACHE_POLL_PERIOD = 25,
                  CACHE_EXPIRATION = 20,
                  CACHE_MAX_AGE_SOFT_LIMIT = 75,
                  CACHE_MAX_AGE_HARD_LIMIT = 259200,
                  CACHE_BACKEND_REQUEST_TIMEOUT = 60,
                  CACHE_REFRESH_LOCK_TIMEOUT = 180,
                  }

for key, value in pairs(env_vars) do
    -- yep, we are OK with key==nil, tonumber will just return nil
    local env_var_val = tonumber(os.getenv(key))
    if env_var_val == nil or env_var_val == value then
        ngx.log(ngx.DEBUG, "Using default ".. key .. " value: `" .. value .. "` seconds")
        _CONFIG[key] = value
    else
        ngx.log(ngx.NOTICE,
                key .. " overridden by ENV to `" .. env_var_val .. "` seconds")
        _CONFIG[key] = env_var_val
    end
end

local function cache_data(key, value)
    -- Store key/value pair to SHM cache (shared across workers).
    -- Return true upon success, false otherwise.
    -- Expected to run within lock context.

    local cache = ngx.shared.cache
    local success, err, forcible = cache:set(key, value)
    if success then
        return true
    end
    ngx.log(
        ngx.ERR,
        "Could not store " .. key .. " to state cache: " .. err
        )
    return false
end


local function request(url, accept_404_reply, auth_token)
    -- We need to make sure that Nginx does not reuse the TCP connection here,
    -- as i.e. during failover it could result in fetching data from e.g. Mesos
    -- master which already abdicated. On top of that we also need to force
    -- re-resolving leader.mesos address which happens during the setup of the
    -- new connection.
    local headers = {
        ["User-Agent"] = "Master Admin Router",
        ["Connection"] = "close",
        }
    if auth_token ~= nil then
        headers["Authorization"] = "token=" .. auth_token
    end

    -- Use cosocket-based HTTP library, as ngx subrequests are not available
    -- from within this code path (decoupled from nginx' request processing).
    -- The timeout parameter is given in milliseconds. The `request_uri`
    -- method takes care of parsing scheme, host, and port from the URL.
    local httpc = http.new()
    httpc:set_timeout(_CONFIG.CACHE_BACKEND_REQUEST_TIMEOUT * 1000)
    local res, err = httpc:request_uri(url, {
        method="GET",
        headers=headers,
        ssl_verify=true
    })

    if not res then
        return nil, err
    end

    if res.status ~= 200 then
        if accept_404_reply and res.status ~= 404 or not accept_404_reply then
            return nil, "invalid response status: " .. res.status
        end
    end

    ngx.log(
        ngx.NOTICE,
        "Request url: " .. url .. " " ..
        "Response Body length: " .. string.len(res.body) .. " bytes."
        )

    return res, nil
end

local function is_container_network(app)
  -- Networking mode for a Marathon application is defined in
  -- app["networks"][1]["mode"].
    local container = app["container"]
    local network = app["networks"][1]
    return container and network and (network["mode"] == "container")
end

local function fetch_and_store_marathon_apps(auth_token)
    -- Access Marathon through localhost.
    ngx.log(ngx.NOTICE, "Cache Marathon app state")
    local appsRes, err = request(UPSTREAM_MARATHON .. "/v2/apps?embed=apps.tasks&label=DCOS_SERVICE_NAME",
                                 false,
                                 auth_token)

    if err then
        ngx.log(ngx.NOTICE, "Marathon app request failed: " .. err)
        return
    end

    local apps, err = cjson_safe.decode(appsRes.body)
    if not apps then
        ngx.log(ngx.WARN, "Cannot decode Marathon apps JSON: " .. err)
        return
    end

    local svcApps = {}
    for _, app in ipairs(apps["apps"]) do
       local appId = app["id"]
       local labels = app["labels"]
       if not labels then
          ngx.log(ngx.NOTICE, "Labels not found in app '" .. appId .. "'")
          goto continue
       end

       -- Service name should exist as we asked Marathon for it
       local svcId = util.normalize_service_name(labels["DCOS_SERVICE_NAME"])

       local scheme = labels["DCOS_SERVICE_SCHEME"]
       if not scheme then
          ngx.log(ngx.NOTICE, "Cannot find DCOS_SERVICE_SCHEME for app '" .. appId .. "'")
          goto continue
       end

       local portIdx = labels["DCOS_SERVICE_PORT_INDEX"]
       if not portIdx then
          ngx.log(ngx.NOTICE, "Cannot find DCOS_SERVICE_PORT_INDEX for app '" .. appId .. "'")
          goto continue
       end

       local portIdx = tonumber(portIdx)
       if not portIdx then
          ngx.log(ngx.NOTICE, "Cannot convert port to number for app '" .. appId .. "'")
          goto continue
       end

       -- Lua arrays default starting index is 1 not the 0 of marathon
       portIdx = portIdx + 1

       local tasks = app["tasks"]

       -- Process only tasks in TASK_RUNNING state.
       -- From http://lua-users.org/wiki/TablesTutorial: "inside a pairs loop,
       -- it's safe to reassign existing keys or remove them"
       for i, t in ipairs(tasks) do
          if t["state"] ~= "TASK_RUNNING" then
             table.remove(tasks, i)
          end
       end

       -- next() returns nil if table is empty.
       local i, task = next(tasks)
       if i == nil then
          ngx.log(ngx.NOTICE, "No task in state TASK_RUNNING for app '" .. appId .. "'")
          goto continue
       end

       ngx.log(
          ngx.NOTICE,
          "Reading state for appId '" .. appId .. "' from task with id '" .. task["id"] .. "'"
          )

       local host_or_ip = task["host"] --take host  by default
       -- In "container" networking mode the task/container will get its own IP
       -- (ip-per-container).
       -- The task will be reachable:
       -- 1) through the container port defined in portMappings.
       -- If the app is using DC/OS overlay network
       -- it will be also reachable on
       -- 2) task["host"]:task["ports"][portIdx] (<private agent IP>:<hostPort>).
       -- However, in case of CNI networks (e.g. Calico), the task might not be
       -- reachable on task["host"]:task["ports"][portIdx], so we choose option 2)
       -- for routing.
       if is_container_network(app) then
          ngx.log(ngx.NOTICE, "app '" .. appId .. "' is in a container network")
          -- override with the ip of the task
          local task_ip_addresses = task["ipAddresses"]
          if task_ip_addresses then
             host_or_ip = task_ip_addresses[1]["ipAddress"]
          else
             ngx.log(ngx.NOTICE, "no ip address allocated yet for app '" .. appId .. "'")
             goto continue
          end
       end

       if not host_or_ip then
          ngx.log(ngx.NOTICE, "Cannot find host or ip for app '" .. appId .. "'")
          goto continue
       end

       -- In "container" mode we find the container port out from portMappings array
       -- for the case when container port is fixed (non-zero value specified).
       -- When container port is specified as 0 it will be set the same as the host port:
       -- https://mesosphere.github.io/marathon/docs/ports.html#random-port-assignment
       -- We do not override it with container port from the portMappings array
       -- in that case.
       -- In "container/bridge" and "host" networking modes we need to use the
       -- host port for routing (available via task's ports array)
       local port
       if is_container_network(app) then

           -- Special case, meaning no ports defined for app in container networking mode.
           if next(app["container"]["portMappings"]) == nil then
               goto continue
           end

           -- In every other case portMappings exist with at least the default.
           -- Skip routing if DCOS_SERVICE_PORT_INDEX points out of bounds of existing portMappings.
           if not app["container"]["portMappings"][portIdx] then
               ngx.log(ngx.NOTICE, "Cannot find port in container portMappings at Marathon port index '" .. (portIdx - 1) .. "' for app '" .. appId .. "'")
               goto continue
           end

           -- If the portMapping exists containerPort always exists.
           -- https://mesosphere.github.io/marathon/docs/networking.html#port-mappings
           -- For any other case route to the containerPort in container networking mode.
           -- NOTE(tweidner): I believe this is unnecessary, containerPort 0 is not a special case.
           if app["container"]["portMappings"][portIdx]["containerPort"] ~= 0 then
               port = app["container"]["portMappings"][portIdx]["containerPort"]
           end
       end

       -- If the containerPort was randomly assigned or any other networking mode is used
       -- try routing to the task ports assigned by Mesos for the given Marathon app.
       if not port then

           -- Skip routing if the Mesos task does not include the ports field.
           if not task["ports"] then
               ngx.log(ngx.NOTICE, "Task ports field is not defined for app '" .. appId .. "'")
               goto continue
           end

           -- Skip routing if DCOS_SERVICE_PORT_INDEX points out of bounds of existing task ports.
           if not task["ports"][portIdx] then
               ngx.log(ngx.NOTICE, "Cannot find port in task ports at Marathon port index '" .. (portIdx - 1) .. "' for app '" .. appId .. "'")
               goto continue
           end

           -- For any other case route to the task port assigned by Mesos.
           port = task["ports"][portIdx]
       end

       -- Details on how Admin Router interprets DCOS_SERVICE_REWRITE_REQUEST_URLS label:
       -- https://github.com/dcos/dcos/blob/master/packages/adminrouter/extra/src/README.md#disabling-url-path-rewriting-for-selected-applications
       local do_rewrite_req_url = labels["DCOS_SERVICE_REWRITE_REQUEST_URLS"]
       if do_rewrite_req_url == false or do_rewrite_req_url == 'false' then
          ngx.log(ngx.INFO, "DCOS_SERVICE_REWRITE_REQUEST_URLS for app '" .. appId .. "' set to 'false'")
          do_rewrite_req_url = false
       else
          -- Treat everything else as true, i.e.:
          -- * label is absent
          -- * label is set to "true" (string) or true (bool)
          -- * label is set to some random string
          do_rewrite_req_url = true
       end

       -- Details on how Admin Router interprets DCOS_SERVICE_REQUEST_BUFFERING label:
       -- https://github.com/dcos/dcos/blob/master/packages/adminrouter/extra/src/README.md#disabling-request-buffering-for-selected-applications
       local do_request_buffering = labels["DCOS_SERVICE_REQUEST_BUFFERING"]
       if do_request_buffering == false or do_request_buffering == 'false' then
          ngx.log(ngx.INFO, "DCOS_SERVICE_REQUEST_BUFFERING for app '" .. appId .. "' set to 'false'")
          do_request_buffering = false
       else
          -- Treat everything else as true, i.e.:
          -- * label is absent
          -- * label is set to "true" (string) or true (bool)
          -- * label is set to some random string
          do_request_buffering = true
       end

       local url = scheme .. "://" .. host_or_ip .. ":" .. port
       svcApps[svcId] = {
         scheme=scheme,
         url=url,
         do_rewrite_req_url=do_rewrite_req_url,
         do_request_buffering=do_request_buffering,
       }

       ::continue::
    end

    local svcApps_json = cjson_safe.encode(svcApps)

    ngx.log(ngx.DEBUG, "Storing Marathon apps data to SHM.")
    if not cache_data("svcapps", svcApps_json) then
        ngx.log(ngx.ERR, "Storing marathon apps cache failed")
        return
    end

    ngx.update_time()
    local time_now = ngx.now()
    if cache_data("svcapps_last_refresh", time_now) then
        ngx.log(ngx.INFO, "Marathon apps cache has been successfully updated")
    end

    return
end

function store_leader_data(leader_name, leader_ip)

    local mleader

    if HOST_IP == 'unknown' or leader_ip == 'unknown' then
        ngx.log(ngx.ERR,
        "Private IP address of the host is unknown, aborting cache-entry creation for ".. leader_name .. " leader")
        mleader = '{"is_local": "unknown", "leader_ip": null}'
    elseif leader_ip == HOST_IP then
        mleader = '{"is_local": "yes", "leader_ip": "'.. HOST_IP ..'"}'
        ngx.log(ngx.INFO, leader_name .. " leader is local")
    else
        mleader = '{"is_local": "no", "leader_ip": "'.. leader_ip ..'"}'
        ngx.log(ngx.INFO, leader_name .. " leader is non-local: `" .. leader_ip .. "`")
    end

    ngx.log(ngx.DEBUG, "Storing " .. leader_name .. " leader to SHM")
    if not cache_data(leader_name .. "_leader", mleader) then
        ngx.log(ngx.ERR, "Storing " .. leader_name .. " leader cache failed")
        return
    end

    ngx.update_time()
    local time_now = ngx.now()
    if cache_data(leader_name .. "_leader_last_refresh", time_now) then
        ngx.log(ngx.INFO, leader_name .. " leader cache has been successfully updated")
    end

    return
end


local function fetch_generic_leader(leaderAPI_url, leader_name, auth_token)
    local mleaderRes, err = request(leaderAPI_url, true, auth_token)

    if err then
        ngx.log(ngx.WARN, leader_name .. " leader request failed: " .. err)
        return nil
    end

    -- We need to translate 404 reply into a JSON that is easy to process for
    -- endpoints. I.E.:
    -- https://mesosphere.github.io/marathon/docs/rest-api.html#get-v2-leader
    local res_body
    if mleaderRes.status == 404 then
        -- Just a hack in order to avoid using gotos - create a substitute JSON
        -- that can be parsed and processed by normal execution path and at the
        -- same time passes the information of a missing Marathon leader.
        ngx.log(ngx.NOTICE, "Using empty " .. leader_name .. " leader JSON")
        res_body = '{"leader": "unknown:0"}'
    else
        res_body = mleaderRes.body
    end

    local mleader, err = cjson_safe.decode(res_body)
    if not mleader then
        ngx.log(ngx.WARN, "Cannot decode " .. leader_name .. " leader JSON: " .. err)
        return nil
    end

    return mleader['leader']:split(":")[1]
end


local function fetch_and_store_marathon_leader(auth_token)
    local leader_ip = fetch_generic_leader(
        UPSTREAM_MARATHON .. "/v2/leader", "marathon", auth_token)

    if leader_ip ~= nil then
        store_leader_data("marathon", leader_ip)
    end
end


local function fetch_and_store_state_mesos(auth_token)
    -- Fetch state JSON summary from Mesos. If successful, store to SHM cache.
    -- Expected to run within lock context.
    local response, err = request(UPSTREAM_MESOS .. "/master/state-summary",
                                  false,
                                  auth_token)

    if err then
        ngx.log(ngx.NOTICE, "Mesos state request failed: " .. err)
        return
    end

    local raw_state_summary, err = cjson_safe.decode(response.body)
    if not raw_state_summary then
        ngx.log(ngx.WARN, "Cannot decode Mesos state-summary JSON: " .. err)
        return
    end

    local parsed_state_summary = {}
    parsed_state_summary['f_by_id'] = {}
    parsed_state_summary['f_by_name'] = {}
    parsed_state_summary['agent_pids'] = {}

    for _, framework in ipairs(raw_state_summary["frameworks"]) do
        local f_id = framework["id"]
        local f_name = util.normalize_service_name(framework["name"])

        parsed_state_summary['f_by_id'][f_id] = {}
        parsed_state_summary['f_by_id'][f_id]['webui_url'] = framework["webui_url"]
        parsed_state_summary['f_by_id'][f_id]['name'] = f_name
        parsed_state_summary['f_by_name'][f_name] = {}
        parsed_state_summary['f_by_name'][f_name]['webui_url'] = framework["webui_url"]
    end

    for _, agent in ipairs(raw_state_summary["slaves"]) do
        local a_id = agent["id"]
        parsed_state_summary['agent_pids'][a_id] = agent["pid"]
    end

    local parsed_state_summary_json = cjson_safe.encode(parsed_state_summary)

    ngx.log(ngx.DEBUG, "Storing parsed Mesos state to SHM.")
    if not cache_data("mesosstate", parsed_state_summary_json) then
        ngx.log(ngx.WARN, "Storing parsed Mesos state to cache failed")
        return
    end

    ngx.update_time()
    local time_now = ngx.now()
    if cache_data("mesosstate_last_refresh", time_now) then
        ngx.log(ngx.INFO, "Mesos state cache has been successfully updated")
    end

    return
end


local function fetch_mesos_leader_state()
    -- Lua forbids jumping over local variables definition, hence we define all
    -- of them here.
    local r, err, answers

    -- We want to use Navstar's dual-dispatch approach and get the response
    -- as fast as possible from any operational MesosDNS. If we set it to local
    -- instance, its failure will break this part of the cache as well.
    --
    -- As for the DNS TTL - we're on purpose ignoring it and going with own
    -- refresh cycle period. Assuming that Navstar and MesosDNS do not do
    -- caching on their own, we just treat DNS as an interface to obtain
    -- current mesos leader data. How long we cache it is just an internal
    -- implementation detail of AR.
    --
    -- Also, see https://github.com/openresty/lua-resty-dns#limitations
    r, err = resolver:new{
        nameservers = {{"198.51.100.1", 53},
                       {"198.51.100.2", 53},
                       {"198.51.100.3", 53}},
        retrans = 3,  -- retransmissions on receive timeout
        timeout = 2000,  -- msec
    }

    if not r then
        ngx.log(ngx.ERR, "Failed to instantiate the resolver: " .. err)
        return nil
    end

    answers, err = r:query("leader.mesos")
    if not answers then
        ngx.log(ngx.ERR, "Failed to query the DNS server: " .. err)
        return nil
    end

    if answers.errcode then
        ngx.log(ngx.ERR,
            "DNS server returned error code: " .. answers.errcode .. ": " .. answers.errstr)
        return nil
    end

    if util.table_len(answers) == 0 then
        ngx.log(ngx.ERR,
            "DNS server did not return anything for leader.mesos")
        return nil
    end

    -- Yes, we are assuming that leader.mesos will always be just one A entry.
    -- AAAA support is a different thing...
    return answers[1].address
end


local function fetch_and_store_mesos_leader()
    local leader_ip = fetch_mesos_leader_state()

    if leader_ip ~= nil then
        store_leader_data("mesos", leader_ip)
    end
end


local function refresh_needed(ts_name)
    -- ts_name (str): name of the '*_last_refresh' timestamp to check
    local cache = ngx.shared.cache

    local last_fetch_time = cache:get(ts_name)
    -- Handle the special case of first invocation.
    if not last_fetch_time then
        ngx.log(ngx.INFO, "Cache `".. ts_name .. "` empty. Fetching.")
        return true
    end

    ngx.update_time()
    local cache_age = ngx.now() - last_fetch_time
    if cache_age > _CONFIG.CACHE_EXPIRATION then
        ngx.log(ngx.INFO, "Cache `".. ts_name .. "` expired. Refresh.")
        return true
    end

    ngx.log(ngx.DEBUG, "Cache `".. ts_name .. "` populated and fresh. NOOP.")

    return false
end


local function refresh_cache(from_timer, auth_token)
    -- Refresh cache in case when it expired or has not been created yet.
    -- Use SHM-based lock for synchronizing coroutines across worker processes.
    --
    -- This function can be invoked via two mechanisms:
    --
    --  * Via ngx.timer (in a coroutine), which is triggered
    --    periodically in all worker processes for performing an
    --    out-of-band cache refresh (this is the usual mode of operation).
    --    In that case, perform cache invalidation only if no other timer
    --    instance currently does so (abort if lock cannot immediately be
    --    acquired).
    --
    --  * During HTTP request processing, when cache content is
    --    required for answering the request but the cache was not
    --    populated yet (i.e. usually early after nginx startup).
    --    In that case, return from this function only after the cache
    --    has been populated (block on lock acquisition).
    --
    -- Args:
    --      from_timer: set to true if invoked from a timer

    -- Acquire lock.
    local lock
    -- In order to avoid deadlocks, we are relying on `exptime` param of
    -- resty.lock (https://github.com/openresty/lua-resty-lock#new)
    --
    -- It's value is maximum time it may take to fetch data from all the
    -- backends (ATM 2xMarathon + Mesos) plus an arbitrary two seconds period
    -- just to be on the safe side.
    local lock_ttl = 3 * (_CONFIG.CACHE_BACKEND_REQUEST_TIMEOUT + 2)

    if from_timer then
        ngx.log(ngx.INFO, "Executing cache refresh triggered by timer")
        -- Fail immediately if another worker currently holds
        -- the lock, because a single timer-based update at any
        -- given time suffices.
        lock = shmlock:new("shmlocks", {timeout=0, exptime=lock_ttl})
        local elapsed, err = lock:lock("cache")
        if elapsed == nil then
            ngx.log(ngx.INFO, "Timer-based update is in progress. NOOP.")
            return
        end
    else
        ngx.log(ngx.INFO, "Executing cache refresh triggered by request")
        -- Cache content is required for current request
        -- processing. Wait for lock acquisition, for at
        -- most _CONFIG.CACHE_REFRESH_LOCK_TIMEOUT * 3 seconds (2xMarathon +
        -- 1 Mesos request).
        lock = shmlock:new("shmlocks", {timeout=_CONFIG.CACHE_REFRESH_LOCK_TIMEOUT,
                                        exptime=lock_ttl })
        local elapsed, err = lock:lock("cache")
        if elapsed == nil then
            ngx.log(ngx.ERR, "Could not acquire lock: " .. err)
            -- Leave early (did not make sure that cache is populated).
            return
        end
    end

    if refresh_needed("mesosstate_last_refresh") then
        fetch_and_store_state_mesos(auth_token)
    end

    if refresh_needed("svcapps_last_refresh") then
        fetch_and_store_marathon_apps(auth_token)
    end

    if refresh_needed("marathon_leader_last_refresh") then
        fetch_and_store_marathon_leader(auth_token)
    end

    if refresh_needed("mesos_leader_last_refresh") then
        fetch_and_store_mesos_leader()
    end

    local ok, err = lock:unlock()
    if not ok then
        -- If this fails, an unlock happens automatically via `exptime` lock
        -- param described earlier.
        ngx.log(ngx.ERR, "Failed to unlock cache shmlock: " .. err)
    end
end


local function periodically_refresh_cache(auth_token)
  -- This function is invoked from within init_worker_by_lua code.
  -- ngx.timer.every() is called here, a more robust alternative to
  -- ngx.timer.at() as suggested by the openresty/lua-nginx-module
  -- documentation:
  -- https://github.com/openresty/lua-nginx-module/tree/v0.10.9#ngxtimerat
  -- See https://jira.mesosphere.com/browse/DCOS-38248 for details on the
  -- cache update problems caused by the recursive use of ngx.timer.at()

    timerhandler = function(premature)
      -- Handler for periodic timer invocation.

        -- Premature timer execution: worker process tries to shut down.
        if premature then
            return
        end

        -- Invoke timer business logic.
        refresh_cache(true, auth_token)
    end

    -- Trigger the initial cache update CACHE_FIRST_POLL_DELAY seconds after
    -- Nginx startup.
    local ok, err = ngx.timer.at(_CONFIG.CACHE_FIRST_POLL_DELAY, timerhandler)
    if not ok then
        ngx.log(ngx.ERR, "Failed to create timer: " .. err)
        return
    else
        ngx.log(ngx.INFO, "Created initial timer for cache updating.")
    end

    -- Trigger the timer, every CACHE_POLL_PERIOD seconds after
    -- Nginx startup.
    local ok, err = ngx.timer.every(_CONFIG.CACHE_POLL_PERIOD, timerhandler)
    if not ok then
        ngx.log(ngx.ERR, "Failed to create timer: " .. err)
        return
    else
        ngx.log(ngx.INFO, "Created periodic timer for cache updating.")
    end
end


local function get_cache_entry(name, auth_token)
    local cache = ngx.shared.cache
    local name_last_refresh = name .. "_last_refresh"

    -- Handle the special case of very early request - before the first
    -- timer-based cache refresh
    local entry_last_refresh = cache:get(name_last_refresh)
    if entry_last_refresh == nil then
        refresh_cache(false, auth_token)

        entry_last_refresh = cache:get(name .. "_last_refresh")
        if entry_last_refresh == nil then
            -- Something is really broken, abort!
            ngx.log(ngx.ERR, "Could not retrieve last refresh time for `" .. name .. "` cache entry")
            return nil
        end
    end

    -- Check the clock
    ngx.update_time()
    local cache_age = ngx.now() - entry_last_refresh

    -- Cache is too old, we can't use it:
    if cache_age > _CONFIG.CACHE_MAX_AGE_HARD_LIMIT then
        ngx.log(ngx.ERR, "Cache entry `" .. name .. "` is too old, aborting request")
        return nil
    end

    -- Cache is stale, but still usable:
    if cache_age > _CONFIG.CACHE_MAX_AGE_SOFT_LIMIT then
        ngx.log(ngx.NOTICE, "Cache entry `" .. name .. "` is stale")
    end

    local entry_json = cache:get(name)
    if entry_json == nil then
        ngx.log(ngx.ERR, "Could not retrieve `" .. name .. "` cache entry from SHM")
        return nil
    end

    local entry, err = cjson_safe.decode(entry_json)
    if entry == nil then
        ngx.log(ngx.ERR, "Cannot decode JSON for entry `" .. entry_json .. "`: " .. err)
        return nil
    end

    return entry
end


-- Expose Admin Router cache interface
local _M = {}
function _M.init(auth_token)
    -- At some point auth_token passing will be refactored out in
    -- favour of service accounts support.
    local res = {}

    if auth_token ~= nil then
        -- auth_token variable is needed by a few functions which are
        -- nested inside top-level ones. We can either define all the functions
        -- inside the same lexical block, or we pass it around. Passing it
        -- around seems cleaner.
        res.get_cache_entry = function (name)
            return get_cache_entry(name, auth_token)
        end
        res.periodically_refresh_cache = function()
            return periodically_refresh_cache(auth_token)
        end
    else
        res.get_cache_entry = get_cache_entry
        res.periodically_refresh_cache = periodically_refresh_cache
    end

    return res
end

return _M
