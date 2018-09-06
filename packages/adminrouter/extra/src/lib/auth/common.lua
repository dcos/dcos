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

local function validate_jwt(auth_token_verification_key)
    -- Admin Router is a DC/OS authenticator. A DC/OS authenticator is an entity
    -- which implements the correct procedure for verifying DC/OS authentication
    -- tokens.
    --
    -- Expect the current HTTP request to present a valid DC/OS authentication
    -- token. A valid DC/OS authentication token is a JSON Web Token (JWT) of
    -- type RS256 (or HS256 in old DC/OS versions) as specified by RFC 7519.
    -- Specifically, a DC/OS authentication token must pass a
    -- standards-compliant JWT validation method as specified via
    -- https://tools.ietf.org/html/rfc7519#section-7.2 and
    -- https://www.rfc-editor.org/rfc/rfc7515.txt.
    --
    -- In addition to what the JWT standard demands a DC/OS authentication token
    -- must have present the custom `uid` claim. It communicates the DC/OS user
    -- ID of the entity that sent the HTTP request. If the authentication token
    -- verification suceeds then the `uid` value can be trusted used for further
    -- processing.
    --
    -- The DC/OS authenticator specification demands that a DC/OS authentication
    -- token must have an `exp` claim set. Do not yet enforce that. Clients,
    -- however, must not rely on this behavior.
    --
    -- TODO(JP): require the `exp` claim to be set.
    --
    -- A DC/OS authentication token must usually be communicated via the
    -- `Authorization` header of the HTTP request, but, for simplifying web
    -- browser support here it can also be set via a special cookie. This is a
    -- private interface between the DC/OS UI and Admin Router and it must not
    -- be relied upon by any other party.
    --
    -- If the authentication token is presented in the Authorization header it
    -- can be presentend in two different formats, one of which is
    --
    --   Authorization: Bearer <authtoken>
    --
    -- While this is against the IANA assignment of authentication schemes
    -- (which reserves Bearer for OAuth2) the industry seems to converge towards
    -- using this method for presenting various kinds of signed tokens to
    -- various kinds of authenticator / authorizer systems in various very
    -- different contexts. Admin Router supports this because this makes it easy
    -- to make third party clients send the DC/OS authentication token in a way
    -- that DC/OS understands.
    --
    -- Extract the presented authentication token, validate it, and return an
    -- error or the `uid`.
    --
    -- Refs:
    -- https://github.com/openresty/lua-nginx-module#access_by_lua
    -- https://github.com/SkyLothar/lua-resty-jwt
    -- https://github.com/cdbattags/lua-resty-jwt

    if auth_token_verification_key == nil then
        ngx.log(ngx.ERR, "Auth token verification key not set. Reject request.")
        return nil, 401
    end

    local auth_header = ngx.var.http_Authorization
    local token = nil
    if auth_header ~= nil then
        ngx.log(ngx.DEBUG, "Authorization header found. Attempt to extract token.")
        _, _, token = string.find(auth_header, "token=(.+)")
        -- Implement Bearer fall-back method.
        if token == nil then
            _, _, token = string.find(auth_header, "Bearer (.+)")
            -- Note(JP) Rewrite to token=<authtoken> for upstream?
        end
    else
        ngx.log(ngx.DEBUG, "Authorization header not found.")
        -- Presence of Authorization header overrides cookie method entirely.
        -- Read cookie. Note(JP): ngx.var.cookie_* cannot access a cookie with a
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

    -- By default, lua-resty-jwt does not validate claims. Build up a claim
    -- validation specification:
    -- * Require DC/OS-specific `uid` claim to be present.
    -- * Make `exp` claim optional (for now).

    local claim_spec = {
        exp = jwt_validators.opt_is_not_expired(),
        __jwt = jwt_validators.require_one_of({"uid"})
        }

    local jwt_obj = jwt:verify(auth_token_verification_key, token, claim_spec)
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
        -- This should not happen as of the claim spec above. But we are no
        -- Lua experts.
        ngx.log(ngx.NOTICE, "Unexpected token payload: missing uid.")
        return nil, 401
    end

    ngx.log(ngx.NOTICE, "UID from the valid DC/OS authentication token: `".. uid .. "`")
    return uid, nil
end

-- Expose interface.
local _M = {}
_M.exit_401 = exit_401
_M.exit_403 = exit_403
_M.validate_jwt = validate_jwt


return _M
