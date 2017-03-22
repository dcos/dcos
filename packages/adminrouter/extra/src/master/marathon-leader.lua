local mleader = cache.get_cache_entry("marathonleader")
if mleader == nil then
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.say("503 Service Unavailable: cache is invalid")
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end

-- check the comment in cache.lua lib, fetch_and_store_marathon_leader() func
if mleader['address'] == "not elected" then
    ngx.status = ngx.HTTP_NOT_FOUND
    ngx.say("404 Not Found: Marathon leader is unknown.")
    return ngx.exit(ngx.HTTP_NOT_FOUND)
end

ngx.var.mleader_host = DEFAULT_SCHEME .. mleader['address']

ngx.log(ngx.DEBUG, "Marathon leader addr from cache: " .. ngx.var.mleader_host)

return
