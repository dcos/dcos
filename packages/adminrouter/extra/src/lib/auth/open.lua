local authcommon = require "auth.common"
local jwt = require "resty.jwt"
local util = require "util"

local SECRET_KEY = nil

local key_file_path = os.getenv("SECRET_KEY_FILE_PATH")
if key_file_path == nil then
    ngx.log(ngx.WARN, "SECRET_KEY_FILE_PATH not set.")
else
    ngx.log(ngx.NOTICE, "Reading secret key from `" .. key_file_path .. "`.")
    SECRET_KEY = util.get_stripped_first_line_from_file(key_file_path)
    if (SECRET_KEY == nil or SECRET_KEY == '') then
        -- Normalize to nil, for simplified subsequent per-request check.
        SECRET_KEY = nil
        ngx.log(ngx.WARN, "Secret key not set or empty string.")
    end
    jwt:set_alg_whitelist({HS256=1})
end

local function validate_jwt_or_exit()
    uid, err = authcommon.validate_jwt(SECRET_KEY)
    if err ~= nil then
        if err == 401 then
            return authcommon.exit_401("oauthjwt")
        end

        -- Other error statuses go here...

        -- Catch-all, normally not reached:
        ngx.log(ngx.ERR, "Unexpected result from validate_jwt()")
        ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
        return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
    end
    return uid
end


local function do_authn_and_authz_or_exit()
    local uid = validate_jwt_or_exit()

    -- Authz using authn :)
    res = ngx.location.capture("/acs/api/v1/users/" .. uid)
    if res.status == ngx.HTTP_NOT_FOUND then
        ngx.log(ngx.ERR, "User not found: `" .. uid .. "`")
        return authcommon.exit_401()
    end

    if res.status == ngx.HTTP_OK then
        return
    end

    -- Catch-all, normally not reached:
    ngx.log(ngx.ERR, "Unexpected response from IAM: " .. res.status)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

-- Initialise and return the module:
local _M = {}
function _M.init(use_auth)
    local res = {}

    if use_auth == "false" then
        ngx.log(
            ngx.NOTICE,
            "ADMINROUTER_ACTIVATE_AUTH_MODULE set to `false`. " ..
            "Deactivate authentication module."
            )
        res.do_authn_and_authz_or_exit = function() return end
    else
        ngx.log(ngx.NOTICE, "Activate authentication module.");
        res.do_authn_and_authz_or_exit = do_authn_and_authz_or_exit
    end

    -- /mesos/
    res.access_mesos_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /(slave|agent)/(?<agentid>[0-9a-zA-Z-]+)(?<url>.+)
    res.access_agent_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /acs/api/v1
    res.access_acsapi_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /navstar/lashup/key
    res.access_lashupkey_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /service/(?<serviceid>[0-9a-zA-Z-.]+)/(?<url>.*)
    res.access_service_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /metadata
    -- /pkgpanda/active.buildinfo.full.json
    -- /dcos-metadata/
    res.access_metadata_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /dcos-history-service/
    res.access_historyservice_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /mesos_dns/
    res.access_mesosdns_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /system/health/v1
    res.access_system_health_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /system/v1/logs/v1/
    res.access_system_logs_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /system/v1/metrics/
    res.access_system_metrics_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /pkgpanda/
    res.access_pkgpanda_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /exhibitor/
    res.access_exhibitor_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /marathon/
    res.access_marathon_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /package/
    res.access_package_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /capabilities/
    res.access_capabilities_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /cosmos/service/
    res.access_cosmosservice_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /system/v1/leader/mesos(?<url>.*)
    res.access_system_mesosleader_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /system/v1/leader/marathon(?<url>.*)
    res.access_system_marathonleader_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    -- /system/v1/agent/(?<agentid>[0-9a-zA-Z-]+)(?<type>(/logs/v1|/metrics/v0))
    res.access_system_agent_endpoint = function()
        return res.do_authn_and_authz_or_exit()
    end

    return res
end

return _M
