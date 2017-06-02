local cjson = require "cjson"
local cookiejar = require "resty.cookie"
local jwt = require "resty.jwt"
local jwt_validators = require "resty.jwt-validators"

local util = require "util"


local errorpages_dir_path = os.getenv("AUTH_ERROR_PAGE_DIR_PATH")
if errorpages_dir_path == nil then
    ngx.log(ngx.WARN, "AUTH_ERROR_PAGE_DIR_PATH not set.")
else
    local p = errorpages_dir_path .. "/401.html"
    ngx.log(ngx.NOTICE, "Reading 401 response from `" .. p .. "`.")
    BODY_401_ERROR_RESPONSE = util.get_file_content(p)
    if (BODY_401_ERROR_RESPONSE == nil or BODY_401_ERROR_RESPONSE == '') then
        -- Normalize to '', for sending empty response bodies.
        BODY_401_ERROR_RESPONSE = ''
        ngx.log(ngx.WARN, "401 error response is empty.")
    end
    local p = errorpages_dir_path .. "/403.html"
    ngx.log(ngx.NOTICE, "Reading 403 response from `" .. p .. "`.")
    BODY_403_ERROR_RESPONSE = util.get_file_content(p)
    if (BODY_403_ERROR_RESPONSE == nil or BODY_403_ERROR_RESPONSE == '') then
        -- Normalize to '', for sending empty response bodies.
        BODY_403_ERROR_RESPONSE = ''
        ngx.log(ngx.WARN, "403 error response is empty.")
    end
end

local function exit_401(authtype)
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "text/html; charset=UTF-8"
    ngx.header["WWW-Authenticate"] = authtype
    ngx.say(BODY_401_ERROR_RESPONSE)
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local function exit_403()
    ngx.status = ngx.HTTP_FORBIDDEN
    ngx.header["Content-Type"] = "text/html; charset=UTF-8"
    ngx.say(BODY_403_ERROR_RESPONSE)
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end

-- We need to differentiate how secret_key value is acquired so we acquire it
-- in different lua fila. This requires either passig this value as a global or
-- as a function argument. Function argument seems like a safer approach.
local function validate_jwt(secret_key)
    -- Inspect Authorization header in current request. Expect JSON Web Token in
    -- compliance with RFC 7519. Expect `uid` key in payload section. Extract
    -- and return uid or the error code.

    -- Refs:
    -- https://github.com/openresty/lua-nginx-module#access_by_lua
    -- https://github.com/SkyLothar/lua-resty-jwt

    if secret_key == nil then
        ngx.log(ngx.ERR, "Secret key not set. Cannot validate request.")
        return nil, 401
    end

    local auth_header = ngx.var.http_Authorization
    local token = nil
    if auth_header ~= nil then
        ngx.log(ngx.DEBUG, "Authorization header found. Attempt to extract token.")
        _, _, token = string.find(auth_header, "token=(.+)")
    else
        ngx.log(ngx.DEBUG, "Authorization header not found.")
        -- Presence of Authorization header overrides cookie method entirely.
        -- Read cookie. Note: ngx.var.cookie_* cannot access a cookie with a
        -- dash in its name.
        local cookie, err = cookiejar:new()
        token = cookie:get("dcos-acs-auth-cookie")
        if token == nil then
            ngx.log(ngx.DEBUG, "dcos-acs-auth-cookie not found.")
        else
            ngx.log(
                ngx.DEBUG, "Use token from dcos-acs-auth-cookie, " ..
                "set corresponding Authorization header for upstream."
                )
            ngx.req.set_header("Authorization", "token=" .. token)
        end
    end

    if token == nil then
        ngx.log(ngx.NOTICE, "No auth token in request.")
        return nil, 401
    end

    -- ngx.log(ngx.DEBUG, "Token: `" .. token .. "`")

    -- By default, lua-resty-jwt does not validate claims, so we build up a
    -- claim validation specification:
    -- * DC/OS-specific `uid` claim to be present.
    -- * make `exp` claim optional as some things still require "forever tokens"

    local claim_spec = {
        exp = jwt_validators.opt_is_not_expired(),
        __jwt = jwt_validators.require_one_of({"uid"})
        }

    local jwt_obj = jwt:verify(secret_key, token, claim_spec)
    ngx.log(ngx.DEBUG, "JSONnized JWT table: " .. cjson.encode(jwt_obj))

    -- .verified is False even for messed up tokens whereas .valid can be nil.
    -- So, use .verified as reference.
    if jwt_obj.verified ~= true then
        ngx.log(ngx.NOTICE, "Invalid token. Reason: ".. jwt_obj.reason)
        return nil, 401
    end

    ngx.log(ngx.DEBUG, "Valid token. Extract UID from payload.")
    local uid = jwt_obj.payload.uid

    if uid == nil or uid == ngx.null then
        ngx.log(ngx.NOTICE, "Unexpected token payload: missing uid.")
        return nil, 401
    end

    ngx.log(ngx.NOTICE, "UID from valid JWT: `".. uid .. "`")
    return uid, nil
end

-- Expose interface.
local _M = {}
_M.exit_401 = exit_401
_M.exit_403 = exit_403
_M.validate_jwt = validate_jwt


return _M
