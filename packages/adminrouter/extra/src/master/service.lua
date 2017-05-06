local util = require "master.util"
local url = require "master.url"

function gen_serviceurl(service_name)
    local records = util.mesos_dns_get_srv(service_name)
    if records == nil then
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.say("503 Service Unavailable: MesosDNS request has failed")
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end

    local first_ip = records[1]['ip']
    local first_port = records[1]['port']
    ngx.var.servicescheme = "http"
    return "http://" .. first_ip .. ":" .. first_port
end

-- Get (cached) Marathon app state.
local svcapps = cache.get_cache_entry("svcapps")
if svcapps == nil then
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.say("503 Service Unavailable: cache state is invalid")
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end

local svc = svcapps[ngx.var.serviceid]
if svc then
    ngx.var.serviceurl = svc["url"]
    ngx.var.servicescheme = svc["scheme"]
    return
end

-- Get (cached) Mesos state.
local state = cache.get_cache_entry("mesosstate")
if state == nil then
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.say("503 Service Unavailable: invalid Mesos state cache")
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end

for _, framework in ipairs(state["frameworks"]) do
  if framework["id"] == ngx.var.serviceid or framework['name'] == ngx.var.serviceid then
    local webui_url = framework["webui_url"]
    if webui_url == "" then
      ngx.var.serviceurl = gen_serviceurl(framework['name'])
      return
    else
      local parsed_webui_url = url.parse(webui_url)

      if parsed_webui_url.path == "/" then
        parsed_webui_url.path = ""
      end
      ngx.var.serviceurl = parsed_webui_url:build()
      ngx.var.servicescheme = parsed_webui_url.scheme
      ngx.log(ngx.DEBUG, ngx.var.serviceurl)
      return
    end
  end
end
