local function resolve()
    local mleader = cache.get_cache_entry("mesos_leader")
    if mleader == nil then
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.say("503 Service Unavailable: cache is invalid")
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end

    if mleader['is_local'] == "unknown" then
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.say("503 Service Unavailable: Mesos leader is unknown.")
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end


    if mleader['is_local'] == 'yes' then
        -- Let's adjust the URI we send to the upstream service/remove the
        -- `/dcos-history-service` prefix:
        ngx.req.set_uri(string.sub(ngx.var.uri, 22))
        ngx.var.historyservice_upstream = "http://127.0.0.1:15055"
    else
        -- Let's prevent infinite proxy loops during failovers when the `leader.mesos`
        -- can't be reliably determined. Prefixing custom headers with `X-`
        -- is no longer recommended:
        -- http://stackoverflow.com/questions/3561381/custom-http-headers-naming-conventions
        if ngx.req.get_headers()["DCOS-Forwarded"] == "true" then
            ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
            ngx.say("503 Service Unavailable: Mesos leader is unknown")
            return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
        else
            ngx.req.set_header("DCOS-Forwarded", "true")
        end
        ngx.var.historyservice_upstream = DEFAULT_SCHEME .. mleader['leader_ip']
    end


    ngx.log(ngx.DEBUG, "Mesos leader addr from cache: " .. ngx.var.historyservice_upstream)
end

-- Initialise and return the module:
local _M = {}
function _M.init()
    local res = {}

    res.resolve = resolve

    return res
end

return _M
