local cjson_safe = require "cjson.safe"
local shmlock = require "resty.lock"
local http = require "resty.http"
local resolver = require "resty.resolver"


local _M = {}

-- In order to make caching code testable, these constants need to be
-- configurable/exposed through env vars.
--
-- Values assigned to these variable need to fufil following condition:
--
-- CACHE_FIRST_POLL_DELAY << CACHE_EXPIRATION < CACHE_POLL_PERIOD < CACHE_MAX_AGE_SOFT_LIMIT < CACHE_MAX_AGE_HARD_LIMIT
--
-- CACHE_BACKEND_REQUEST_TIMEOUT << CACHE_REFRESH_LOCK_TIMEOUT
--
-- All are in units of seconds. Below are the defaults:
local _CONFIG = {}
local env_vars = {CACHE_FIRST_POLL_DELAY = 2,
                  CACHE_POLL_PERIOD = 25,
                  CACHE_EXPIRATION = 20,
                  CACHE_MAX_AGE_SOFT_LIMIT = 75,
                  CACHE_MAX_AGE_HARD_LIMIT = 259200,
                  CACHE_BACKEND_REQUEST_TIMEOUT = 10,
                  CACHE_REFRESH_LOCK_TIMEOUT = 20,
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
    local headers = {}
    if auth_token ~= nil then
        headers = {["Authorization"] = "token=" .. auth_token}
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
       local svcId = labels["DCOS_SERVICE_NAME"]

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

       local host = task["host"]
       if not host then
          ngx.log(ngx.NOTICE, "Cannot find host for app '" .. appId .. "'")
          goto continue
       end

       local ports = task["ports"]
       if not ports then
          ngx.log(ngx.NOTICE, "Cannot find ports for app '" .. appId .. "'")
          goto continue
       end

       local port = ports[portIdx]
       if not port then
          ngx.log(ngx.NOTICE, "Cannot find port at Marathon port index '" .. (portIdx - 1) .. "' for app '" .. appId .. "'")
          goto continue
       end

       local url = scheme .. "://" .. host .. ":" .. port
       svcApps[svcId] = {scheme=scheme, url=url}

       ::continue::
    end

    svcApps_json = cjson_safe.encode(svcApps)

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


local function fetch_and_store_marathon_leader(auth_token)
    -- Fetch Marathon leader address. If successful, store to SHM cache.
    -- Expected to run within lock context.
    local mleaderRes, err = request(UPSTREAM_MARATHON .. "/v2/leader",
                                    true,
                                    auth_token)

    if err then
        ngx.log(ngx.WARN, "Marathon leader request failed: " .. err)
        return
    end

    -- We need to translate 404 reply into a JSON that is easy to process for
    -- endpoints:
    -- https://mesosphere.github.io/marathon/docs/rest-api.html#get-v2-leader
    local res_body
    if mleaderRes.status == 404 then
        -- Just a hack in order to avoid using gotos - create a substitute JSON
        -- that can be parsed and processed by normal execution path and at the
        -- same time passes the information of a missing Marathon leader.
        ngx.log(ngx.NOTICE, "Using empty Marathon leader JSON")
        res_body = '{"leader": "not elected:0"}'
    else
        res_body = mleaderRes.body
    end

    local mleader, err = cjson_safe.decode(res_body)
    if not mleader then
        ngx.log(ngx.WARN, "Cannot decode Marathon leader JSON: " .. err)
        return
    end

    local split_mleader = mleader['leader']:split(":")
    local parsed_mleader = {}
    parsed_mleader["address"] = split_mleader[1]
    parsed_mleader["port"] = split_mleader[2]
    local mleader = cjson_safe.encode(parsed_mleader)

    ngx.log(ngx.DEBUG, "Storing Marathon leader to SHM")
    if not cache_data("marathonleader", mleader) then
        ngx.log(ngx.ERR, "Storing Marathon leader cache failed")
        return
    end

    ngx.update_time()
    local time_now = ngx.now()
    if cache_data("marathonleader_last_refresh", time_now) then
        ngx.log(ngx.INFO, "Marathon leader cache has been successfully updated")
    end

    return
end


local function fetch_and_store_state_mesos(auth_token)
    -- Fetch state JSON summary from Mesos. If successful, store to SHM cache.
    -- Expected to run within lock context.
    local mesosRes, err = request(UPSTREAM_MESOS .. "/master/state-summary",
                                  false,
                                  auth_token)

    if err then
        ngx.log(ngx.NOTICE, "Mesos state request failed: " .. err)
        return
    end

    ngx.log(ngx.DEBUG, "Storing Mesos state to SHM.")
    if not cache_data("mesosstate", mesosRes.body) then
        ngx.log(ngx.WARN, "Storing mesos state cache failed")
        return
    end

    ngx.update_time()
    local time_now = ngx.now()
    if cache_data("mesosstate_last_refresh", time_now) then
        ngx.log(ngx.INFO, "Mesos state cache has been successfully updated")
    end

    return
end


local function fetch_and_store_mesos_leader_state()
    -- Lua forbids jumping over local variables definition, hence we define all
    -- of them here.
    local res_body, r, err, answers

    if HOST_IP == 'unknown' then
        ngx.log(ngx.ERR,
        "Local Mesos Master IP address is unknown, cache entry is unusable")
        res_body = '{"is_local": "unknown", "leader_ip": null}'
        goto store_cache
    end

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
        return
    end

    answers, err = r:query("leader.mesos")
    if not answers then
        ngx.log(ngx.ERR, "Failed to query the DNS server: " .. err)
        return
    end

    if answers.errcode then
        ngx.log(ngx.ERR,
            "DNS server returned error code: " .. answers.errcode .. ": " .. answers.errstr)
        return
    end

    if util.table_len(answers) == 0 then
        ngx.log(ngx.ERR,
            "DNS server did not return anything for leader.mesos")
        return
    end

    -- Yes, we are assuming that leader.mesos will always be just one A entry.
    -- AAAA support is a different thing...

    if answers[1].address == HOST_IP then
        res_body = '{"is_local": "yes", "leader_ip": "'.. HOST_IP ..'"}'
        ngx.log(ngx.INFO, "Mesos Leader is local")
    else
        res_body = '{"is_local": "no", "leader_ip": "'.. answers[1].address ..'"}'
        ngx.log(ngx.INFO, "Mesos Leader is non-local: `" .. answers[1].address .. "`")
    end

    ::store_cache::
    if not cache_data("mesos_leader", res_body) then
        ngx.log(ngx.ERR, "Storing `Mesos Leader` state cache failed")
        return
    end

    ngx.update_time()
    local time_now = ngx.now()
    if cache_data("mesos_leader_last_refresh", time_now) then
        ngx.log(ngx.INFO, "`Mesos Leader` state cache has been successfully updated")
    end

    return

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
        -- most 20 seconds.
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

    if refresh_needed("marathonleader_last_refresh") then
        fetch_and_store_marathon_leader(auth_token)
    end

    if refresh_needed("mesos_leader_last_refresh") then
        fetch_and_store_mesos_leader_state()
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
    -- ngx.timer.at() can be called here, whereas most of the other ngx.*
    -- API is not available.

    timerhandler = function(premature)
        -- Handler for recursive timer invocation.
        -- Within a timer callback, plenty of the ngx.* API is available,
        -- with the exception of e.g. subrequests. As ngx.sleep is also not
        -- available in the current context, the recommended approach of
        -- implementing periodic tasks is via recursively defined timers.

        -- Premature timer execution: worker process tries to shut down.
        if premature then
            return
        end

        -- Invoke timer business logic.
        refresh_cache(true, auth_token)

        -- Register new timer.
        local ok, err = ngx.timer.at(_CONFIG.CACHE_POLL_PERIOD, timerhandler)
        if not ok then
            ngx.log(ngx.ERR, "Failed to create timer: " .. err)
        else
            ngx.log(ngx.INFO, "Created recursive timer for cache updating.")
        end
    end

    -- Trigger initial timer, about CACHE_FIRST_POLL_DELAY seconds after
    -- Nginx startup.
    local ok, err = ngx.timer.at(_CONFIG.CACHE_FIRST_POLL_DELAY, timerhandler)
    if not ok then
        ngx.log(ngx.ERR, "Failed to create timer: " .. err)
        return
    else
        ngx.log(ngx.INFO, "Created initial recursive timer for cache updating.")
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
        ngx.log(ngx.NOTICE, "Using stale `" .. name .. "` cache entry to fulfill the request")
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
