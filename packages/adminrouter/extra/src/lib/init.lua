util = require "util"

DEFAULT_SCHEME = os.getenv("DEFAULT_SCHEME")
if DEFAULT_SCHEME == nil then
    DEFAULT_SCHEME = "http://"
end
ngx.log(ngx.NOTICE, "Default scheme: " .. DEFAULT_SCHEME)

HOST_IP = os.getenv("HOST_IP")
if HOST_IP == nil or util.verify_ip(HOST_IP) == false then
    if HOST_IP ~= nil then
        ngx.log(ngx.ERR, "HOST_IP var is not a valid ipv4: " .. HOST_IP)
    end
    -- This will cause Lua logic to always respond with 5XX status to the
    -- requests that rely on this variable.
    HOST_IP = "unknown"
end
ngx.log(ngx.NOTICE, "Local Mesos Master IP: " .. HOST_IP)

UPSTREAM_MESOS = os.getenv("UPSTREAM_MESOS")
if UPSTREAM_MESOS == nil then
    UPSTREAM_MESOS = "http://leader.mesos:5050"
end
ngx.log(ngx.NOTICE, "Mesos upstream: " .. UPSTREAM_MESOS)

UPSTREAM_MARATHON = os.getenv("UPSTREAM_MARATHON")
if UPSTREAM_MARATHON == nil then
    UPSTREAM_MARATHON = "http://127.0.0.1:8080"
end
ngx.log(ngx.NOTICE, "Marathon upstream: " .. UPSTREAM_MARATHON)

SERVICE_AUTH_TOKEN = os.getenv("SERVICE_AUTH_TOKEN")
if SERVICE_AUTH_TOKEN ~= nil then
    ngx.log(ngx.NOTICE, "Picked up service authentication token from env.")
end

EXHIBITOR_ADMIN_HTTPBASICAUTH_CREDS = os.getenv(
    "EXHIBITOR_ADMIN_HTTPBASICAUTH_CREDS")
if EXHIBITOR_ADMIN_HTTPBASICAUTH_CREDS ~= nil then
    ngx.log(
        ngx.NOTICE,
        "Picked up EXHIBITOR_ADMIN_HTTPBASICAUTH_CREDS from env."
        )
end

-- Initialise and return the module:
local _M = {}
function _M.init()
    local res = {}

    res.DEFAULT_SCHEME = DEFAULT_SCHEME
    res.HOST_IP = HOST_IP
    res.UPSTREAM_MESOS = UPSTREAM_MESOS
    res.UPSTREAM_MARATHON = UPSTREAM_MARATHON
    res.SERVICE_AUTH_TOKEN = SERVICE_AUTH_TOKEN
    res.EXHIBITOR_ADMIN_HTTPBASICAUTH_CREDS = EXHIBITOR_ADMIN_HTTPBASICAUTH_CREDS

    return res
end

return _M
