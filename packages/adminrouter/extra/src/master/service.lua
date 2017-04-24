local util = require "master.util"
local url = require "master.url"


local function resolve_srv_entry(framework_name)
    -- Try to resolve SRV entry for given framework name using MesosDNS
    --
    -- Arguments:
    --   framework_name (str): name of the framework to resolve
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
        "/internal/mesos_dns/v1/services/_" .. framework_name .. "._tcp.marathon.mesos")

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

local function serviceurl_from_srv_query(service_name)
    -- Create serviceurl basing on the data from MesosDNS SRV entries and
    -- given service_name
    --
    -- Argument:
    --   service_name (str): name of the service to build
    --
    -- Returns:
    --  A list with (scheme, serviceurl) elements. Scheme by default is
    --  hardcoded to 'http'. If SRV resolving was unsuccessful, 503 response
    --  is triggered directly.
    local serviceurl = nil
    local scheme = 'http' -- Hardcoded 

    local records = resolve_srv_entry(service_name)

    if records == nil then
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.say("503 Service Unavailable: MesosDNS request has failed")
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end

    if records[1]['ip'] == "" then
        return nil, nil
    end

    local first_ip = records[1]['ip']
    local first_port = records[1]['port']
    serviceurl = "http://" .. first_ip .. ":" .. first_port

    return scheme, serviceurl
end

local function resolve_via_marathon_apps_state(service_name)
    -- Try to resolve upstream for given service name basing on
    -- Marathon apps DB
    --
    -- Arguments:
    --   service_name (string): service name that should be resolved
    --
    -- Returns:
    --   True/False depending on whether resolving service name was successful
    --   or not.
    local svcapps = cache.get_cache_entry("svcapps")

    if svcapps == nil then
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.say("503 Service Unavailable: cache state is invalid")
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end

    if svcapps[service_name] == nil then
        return false
    end

    ngx.var.serviceurl = svcapps[service_name]["url"]
    ngx.var.servicescheme = svcapps[service_name]["scheme"]
    return true
end

local function resolve_via_mesos_dns(serviceurl_id)
    -- Try to resolve upstream for given service name basing on
    -- MesosDNS SRV entries
    --
    -- Arguments:
    --   service_name (string): service name that should be resolved
    --
    -- Returns:
    --   True/False depending on whether resolving service name was successful
    --   or not.
    scheme, serviceurl = serviceurl_from_srv_query(serviceurl_id)

    if serviceurl == nil then
        return false
    end

    ngx.var.servicescheme = scheme
    ngx.var.serviceurl = serviceurl
    return true
end

local function resolve_via_mesos_state(service_name)
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
    --   True/False depending on whether resolving service name was successful
    --   or not.
    local webui_url = nil
    local serviceurl_id = nil
    local state = cache.get_cache_entry("mesosstate")

    if state == nil then
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.say("503 Service Unavailable: invalid Mesos state cache")
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end

    if state['f_by_id'][service_name] ~= nil then
        webui_url = state['f_by_id'][service_name]['webui_url']
        serviceurl_id = state['f_by_id'][service_name]['name']
    elseif state['f_by_name'][service_name] ~= nil then
        webui_url = state['f_by_name'][service_name]['webui_url']
        serviceurl_id = state['f_by_name'][service_name]['name']
    end

    if webui_url == nil then
        return false
    end

    if webui_url == "" then
        return resolve_via_mesos_dns(serviceurl_id)
    end

    local parsed_webui_url = url.parse(webui_url)
    if parsed_webui_url.path == "/" then
        parsed_webui_url.path = ""
    end

    ngx.var.serviceurl = parsed_webui_url:build()
    ngx.var.servicescheme = parsed_webui_url.scheme
    return true
end

local function resolve(service_name)
    -- Resolve given service name using DC/OS cluster data.
    --
    -- Arguments:
    --   service_name (string): service name that should be resolved
    --
    -- Returns:
    --   True/False depending on whether resolving service name was successful
    --   or not.
    ngx.log(ngx.NOTICE, "Resolving service `".. service_name .. "`")
    res = resolve_via_marathon_apps_state(service_name)

    if res == false then
        res = resolve_via_mesos_state(service_name)
    end

    return res
end

local function recursive_resolve(serviceid)

    -- TODO (prozlach): Add recursive resolving here
    local resolved = resolve(serviceid)
    -- TODO (prozlach): Recursive resolving ends here

    if resolved == false then
        ngx.status = ngx.HTTP_NOT_FOUND
        ngx.say("404 Not Found: service `" .. ngx.var.serviceid .. "` not found.")
        return ngx.exit(ngx.HTTP_NOT_FOUND)
    end

end

-- Initialise and return the module:
local _M = {}
function _M.init()
    local res = {}

    res.recursive_resolve = recursive_resolve

    return res
end

return _M
