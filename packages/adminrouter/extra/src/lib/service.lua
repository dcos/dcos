local url = require "url"
local cjson_safe = require "cjson.safe"
local util = require "util"


RESOLVE_LIMIT = 10


local function resolve_srv_entry(service_name)
    -- Try to resolve SRV entry for given framework name using MesosDNS
    --
    -- Arguments:
    --   service_name (str): name of the framework to resolve
    --
    -- Returns:
    --   List of records as provided by the MesosDNS API. If the record was not
    --   found, MesosDNS by default returns "empty" record:
    --
    --   {
    --       "service": "",
    --       "host": "",
    --       "ip": "",
    --       "port": "",
    --   }
    --
    --   Such case is/should be handled in the calling function. In case of an
    --   error, nil is returned.
    --
    local res = ngx.location.capture(
        "/internal/mesos_dns/v1/services/_" .. service_name .. "._tcp.marathon.mesos")

    if res.truncated then
        -- Remote connection dropped prematurely or timed out.
        ngx.log(ngx.ERR, "Request to Mesos DNS failed.")
        return nil
    end
    if res.status ~= 200 then
        ngx.log(ngx.ERR, "Mesos DNS response status: " .. res.status)
        return nil
    end

    local records, err = cjson_safe.decode(res.body)
    if not records then
        ngx.log(ngx.ERR, "Cannot decode JSON: " .. err)
        return nil
    end
    return records
end

local function upstream_url_from_srv_query(service_name)
    -- Create upstream_url basing on the data from MesosDNS SRV entries and
    -- given service_name
    --
    -- Argument:
    --   service_name (str): name of the service to build
    --
    -- Returns:
    --  A list with:
    --  - upstream_scheme - for now hardcoded to http
    --  - upstream_url
    --  - err_code, err_text - if an error occured these will be HTTP status
    --    and error text that should be sent to the client. `nil` otherwise
    local upstream_url = nil
    local upstream_scheme = 'http' -- Hardcoded in case of MesosDNS

    local records = resolve_srv_entry(service_name)

    if records == nil then
        return nil, nil, ngx.HTTP_SERVICE_UNAVAILABLE, "503 Service Unavailable: MesosDNS request has failed"
    end

    if records[1]['ip'] == "" then
        return nil, nil, nil, nil
    end

    local first_ip = records[1]['ip']
    local first_port = records[1]['port']
    upstream_url = "http://" .. first_ip .. ":" .. first_port

    return upstream_scheme, upstream_url, nil, nil
end

local function resolve_via_marathon_apps_state(service_name, marathon_cache)
    -- Try to resolve upstream for given service name basing on
    -- Marathon apps DB
    --
    -- Arguments:
    --   service_name (string): service name that should be resolved
    --
    -- Returns:
    --  A list with:
    --  - true/false depending on whether resolving service name was successful
    --    or not.
    --  - err_code, err_text - if an error occured these will be HTTP status
    --    and error text that should be sent to the client. `nil` otherwise
    if marathon_cache == nil then
        return nil, ngx.HTTP_SERVICE_UNAVAILABLE, "503 Service Unavailable: invalid Marathon svcapps cache"
    end

    if marathon_cache[service_name] == nil then
        return false, nil, nil
    end

    ngx.log(ngx.NOTICE, "Resolved via Marathon, service id: `".. service_name .. "`")
    ngx.var.upstream_url = marathon_cache[service_name]["url"]
    ngx.var.upstream_scheme = marathon_cache[service_name]["scheme"]
    return true, nil, nil
end

local function resolve_via_mesos_dns(service_name)
    -- Try to resolve upstream for given service name basing on
    -- MesosDNS SRV entries
    --
    -- Arguments:
    --   service_name (string): service name that should be resolved
    --
    -- Returns:
    --  A list with:
    --  - true/false depending on whether resolving service name was successful
    --    or not.
    --  - err_code, err_text - if an error occured these will be HTTP status
    --    and error text that should be sent to the client. `nil` otherwise
    upstream_scheme, upstream_url, err_code, err_text = upstream_url_from_srv_query(
        service_name)

    if err_code ~= nil then
        return nil, err_code, err_text
    end

    if upstream_url == nil then
        return false, nil, nil
    end

    ngx.log(ngx.NOTICE, "Resolved via MesosDNS, service id: `".. service_name .. "`")
    ngx.var.upstream_scheme = upstream_scheme
    ngx.var.upstream_url = upstream_url
    return true, nil, nil
end

local function resolve_via_mesos_state(service_name, mesos_cache)
    -- Try to resolve upstream for given service name basing on
    -- Mesos state-summary endpoint data.
    --
    -- In case when framework is registered, but relevant data is unavailable,
    -- MesosDNS SRV entries are used.
    --
    -- Arguments:
    --   service_name (string): service name that should be resolved
    --
    -- Returns:
    --  A list with:
    --  - true/false depending on whether resolving service name was successful
    --    or not.
    --  - err_code, err_text - if an error occured these will be HTTP status
    --    and error text that should be sent to the client. `nil` otherwise
    local webui_url = nil
    local service_name_bymesos = nil

    if mesos_cache == nil then
        return nil, ngx.HTTP_SERVICE_UNAVAILABLE, "503 Service Unavailable: invalid Mesos state cache"
    end

    -- Even though frameworks will be resolved much more often using their name
    -- than ID, we cannot optimize this and change the order as we may break
    -- services/software relying on that.
    if mesos_cache['f_by_id'][service_name] ~= nil then
        webui_url = mesos_cache['f_by_id'][service_name]['webui_url']
        -- This effectivelly resolves framework ID into human-friendly service
        -- name.
        service_name = mesos_cache['f_by_id'][service_name]['name']
    elseif mesos_cache['f_by_name'][service_name] ~= nil then
        webui_url = mesos_cache['f_by_name'][service_name]['webui_url']
    end

    if webui_url == nil then
        return false, nil, nil
    end

    if webui_url == "" then
        return resolve_via_mesos_dns(service_name)
    end

    local parsed_webui_url = url.parse(webui_url)
    if parsed_webui_url.path == "/" then
        parsed_webui_url.path = ""
    end

    ngx.log(ngx.NOTICE, "Resolved via Mesos state-summary, service id: `".. service_name .. "`")
    ngx.var.upstream_url = parsed_webui_url:build()
    ngx.var.upstream_scheme = parsed_webui_url.scheme
    return true, nil, nil
end

local function resolve(service_name, mesos_cache, marathon_cache)
    -- Resolve given service name using DC/OS cluster data.
    --
    -- Arguments:
    --   service_name (string): service name that should be resolved
    --
    -- Returns:
    --  A list with:
    --  - true/false depending on whether resolving service name was successful
    --    or not.
    --  - err_code, err_text - if an error occured these will be HTTP status
    --    and error text that should be sent to the client. `nil` otherwise
    ngx.log(ngx.DEBUG, "Resolving service `".. service_name .. "`")
    res, err_code, err_text = resolve_via_marathon_apps_state(
        service_name, marathon_cache)

    if err_code ~= nil then
        return nil, err_code, err_text
    end

    if res == false then
        res, err_code, err_text = resolve_via_mesos_state(
            service_name, mesos_cache)
    end

    return res, err_code, err_text
end

local function recursive_resolve(auth, path)
    -- Resolve given service path using DC/OS cluster data.
    --
    -- This function tries to determine the service name component of the path
    -- used to query `/service` endpoint and resolve it to correct upstream.
    --
    -- Arguments:
    --   auth: auth module, already in an initialised state
    --   path (string): service path that should be resolved
    --
    -- Returns:
    -- Nothing, it sets nginx variables directly.

    local resolved = false
    local more_segments = true
    local service_realpath = ""
    local err_code = nil
    local err_text = nil

    -- Acquire cache data:
    -- On one hand we want to fetch cache only once no matter the number of
    -- resolving attempts, on the other hand - we want to treat each cache
    -- entry independently - if i.e. Marathon is borked but Mesos ``
    -- Marathon-specific, we should still handle the request. This is the
    -- reason why error checking is done in a different place than actually
    -- fetching the cache data.
    local marathon_cache = cache.get_cache_entry("svcapps")
    local mesos_cache = cache.get_cache_entry("mesosstate")

    -- Resolve all the services!
    for i = 1, RESOLVE_LIMIT do
        if err_code ~= nil or resolved or not more_segments then
            break
        end

        service_name, service_realpath, more_segments = util.extract_service_path_component(
            path, i)
        resolved, err_code, err_text = resolve(
            service_name, mesos_cache, marathon_cache)
    end

    if resolved == false or err_code ~= nil then
        -- First, let's make sure that user has correct permissions to see
        -- error messages:
        auth.access_service_endpoint(nil)

        if err_code ~= nil then
            -- Send the error message to the user:
            ngx.status = err_code
            ngx.say(err_text)
            return ngx.exit(err_code)
        end

        ngx.status = ngx.HTTP_NOT_FOUND
        ngx.say("404 Not Found: service not found.")
        return ngx.exit(ngx.HTTP_NOT_FOUND)
    end

    -- Authorize the request:
    auth.access_service_endpoint(service_realpath)

    -- Trim the URI prefix:
    prefix = "/service/" .. service_realpath
    adjusted_prefix = string.sub(ngx.var.uri, string.len(prefix) + 1)
    if adjusted_prefix == "" then
        adjusted_prefix = "/"
    end
    ngx.req.set_uri(adjusted_prefix)

    -- Will be used for HTTP Location header adjustements:
    ngx.var.service_realpath = service_realpath
end

-- Initialise and return the module:
local _M = {}
function _M.init()
    local res = {}

    res.recursive_resolve = recursive_resolve

    return res
end

return _M
