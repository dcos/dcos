local authcommon = require "auth.common"
local jwt = require "resty.jwt"
local util = require "util"


local AUTH_TOKEN_VERIFICATION_KEY = nil


local key_file_path = os.getenv("AUTH_TOKEN_VERIFICATION_KEY_FILE_PATH")
if key_file_path == nil then
    ngx.log(ngx.WARN, "AUTH_TOKEN_VERIFICATION_KEY_FILE_PATH not set.")
else
    ngx.log(ngx.NOTICE, "Reading auth token verification key from `" .. key_file_path .. "`.")
    AUTH_TOKEN_VERIFICATION_KEY = util.get_file_content(key_file_path)
    if (AUTH_TOKEN_VERIFICATION_KEY == nil or AUTH_TOKEN_VERIFICATION_KEY == '') then
        -- Normalize to nil, for simplified subsequent per-request check.
        AUTH_TOKEN_VERIFICATION_KEY = nil
        ngx.log(ngx.WARN, "Auth token verification key not set or empty string.")
    end
    -- Note(JP): by the end of this project set this to RS256 only.
    jwt:set_alg_whitelist({RS256=1,HS256=1})
end


local function validate_jwt_or_exit(proto)
    local uid, err = authcommon.validate_jwt(AUTH_TOKEN_VERIFICATION_KEY)
    if err ~= nil then
        if err == 401 then
            if proto == "grpc" then
                return authcommon.exit_grpc(16, "access denied - not authenticated")
            else
                return authcommon.exit_401("oauthjwt")
            end
        end

        -- Catch-all, normally not reached:
        ngx.log(ngx.ERR, "Unexpected result from validate_jwt()")
        if proto == "grpc" then
            return authcommon.exit_grpc(13, "internal error occurred")
        else
            ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
            return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
        end
    end
    ngx.log(ngx.INFO, "uid=" .. uid)
    return uid
end


local function do_authn_and_authz_or_exit_http()
    -- Here, only do authentication, i.e. require
    -- valid authentication token to be presented.
    -- Downstream, this function can be replaced
    -- with more complex business logic.
    validate_jwt_or_exit("http")
end


local function do_authn_and_authz_or_exit_grpc()
    -- Here, only do authentication, i.e. require
    -- valid authentication token to be presented.
    -- Downstream, this function can be replaced
    -- with more complex business logic.
    validate_jwt_or_exit("grpc")
end


local function do_authn_or_exit(object)
    validate_jwt_or_exit("http")
end


-- Initialise and return the module.
local _M = {}
function _M.init(use_auth)
    local res = {}

    if use_auth == "false" then
        ngx.log(
            ngx.NOTICE,
            "ADMINROUTER_ACTIVATE_AUTH_MODULE set to `false`. " ..
            "Deactivate authentication module."
            )
        res.do_authn_and_authz_or_exit_http = function() return end
        res.do_authn_or_exit = function() return end
    else
        ngx.log(ngx.NOTICE, "Activate authentication module.");
        res.do_authn_and_authz_or_exit_http = do_authn_and_authz_or_exit_http
        res.do_authn_and_authz_or_exit_grpc = do_authn_and_authz_or_exit_grpc
        res.do_authn_or_exit = do_authn_or_exit
    end

    -- /mesos/
    res.access_mesos_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /(slave|agent)/(?<agentid>[0-9a-zA-Z-]+)(?<url>.+)
    res.access_agent_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /acs/api/v1
    res.access_acsapi_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /navstar/lashup/key
    res.access_lashupkey_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /net/
    res.access_net_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /service/.+
    res.access_service_endpoint = function(service_path)
        -- service_path is unused here, kept just for compatibility with EE
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /pkgpanda/active.buildinfo.full.json
    -- /dcos-metadata/
    res.access_misc_metadata_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /metadata
    res.access_metadata_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /mesos_dns/
    res.access_mesosdns_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /system/checks/v1
    res.access_system_checks_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /system/health/v1
    res.access_system_health_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /system/v1/logs/
    res.access_system_logs_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /system/v1/metrics/
    res.access_system_metrics_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /pkgpanda/
    res.access_pkgpanda_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /exhibitor/
    res.access_exhibitor_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /marathon/
    res.access_marathon_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /package/
    res.access_package_endpoint = function(package_path)
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /capabilities/
    res.access_capabilities_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /cosmos/service/
    res.access_cosmosservice_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /system/v1/leader/mesos(?<url>.*)
    res.access_system_mesosleader_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /system/v1/leader/marathon(?<url>.*)
    res.access_system_marathonleader_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /system/v1/agent/(?<agentid>[0-9a-zA-Z-]+)(?<type>(/logs|/metrics/v0))
    res.access_system_agent_endpoint = function()
        return res.do_authn_and_authz_or_exit_http()
    end

    -- /dcos-ui-update-service/api/v1/version/
    res.access_dcos_ui_update_service_version_api_endpoint = function()
        return res.do_authn_and_authz_or_exit_http();
    end

    -- /dcos-ui-update-service/api/
    res.access_dcos_ui_update_service_api_endpoint = function()
        return res.do_authn_and_authz_or_exit_http();
    end

    -- gRPC etcd endpoint
    res.access_grpc_etcd_endpoint = function()
        return res.do_authn_and_authz_or_exit_grpc();
    end

    return res
end

return _M
