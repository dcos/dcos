local cjson = require "cjson"
local jwt = require "resty.jwt"
local cookiejar = require "resty.cookie"


local util = require "common.util"


local SECRET_KEY = nil
local BODY_AUTH_ERROR_RESPONSE = nil

local basichttpcred = os.getenv("MESOSPHERE_HTTP_CREDENTIALS")
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
end


-- Refs:
-- https://github.com/openresty/lua-nginx-module#access_by_lua
-- https://github.com/SkyLothar/lua-resty-jwt


local function exit_401()
    ngx.log(ngx.DEBUG, "ETHOS: exit 401 called")
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "text/html; charset=UTF-8"
    ngx.header["WWW-Authenticate"] = "oauthjwt"
    ngx.say(BODY_401_ERROR_RESPONSE)
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end


local function exit_403()
    ngx.status = ngx.HTTP_FORBIDDEN
    ngx.header["Content-Type"] = "text/html; charset=UTF-8"
    ngx.say(BODY_403_ERROR_RESPONSE)
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end


local function validate_jwt_or_exit()
    -- Inspect Authorization header in current request. Expect JSON Web Token in
    -- compliance with RFC 7519. Expect `uid` key in payload section. Extract
    -- and return uid. In all other cases, terminate request handling and
    -- respond with an appropriate HTTP error status code.

    if SECRET_KEY == nil then
        ngx.log(ngx.ERR, "Secret key not set. Cannot validate request.")
        return exit_401()
    end

    local auth_header = ngx.var.http_Authorization
    local token = nil
    if auth_header ~= nil then
        ngx.log(ngx.DEBUG, "Authorization header found. Attempt to extract token.")
        if string.find(auth_header, "Basic") then
          ngx.log(
              ngx.DEBUG, "Basic authentication header found " ..
              "look for token in cookie and override."
              )
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
        else
          _, _, token = string.find(auth_header, "token=(.+)")
        end
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
        return exit_401()
    end

    -- ngx.log(ngx.DEBUG, "Token: `" .. token .. "`")
    -- Parse and verify token (also validate expiration time).
    local jwt_obj = jwt:verify(SECRET_KEY, token)
    ngx.log(ngx.DEBUG, "JSONnized JWT table: " .. cjson.encode(jwt_obj))
    -- .verified is False even for messed up tokens whereas .valid can be nil.
    -- So, use .verified as reference.
    if jwt_obj.verified == false then
        ngx.log(ngx.NOTICE, "Invalid token. Reason: ".. jwt_obj.reason)
        return exit_401()
    end

    ngx.log(ngx.DEBUG, "Valid token. Extract UID from payload.")
    local uid = jwt_obj.payload.uid

    if uid == nil then
        ngx.log(ngx.NOTICE, "Unexpected token payload: missing uid.")
        return exit_401()
    end

    ngx.log(ngx.NOTICE, "UID from valid JWT: `".. uid .. "`")

    res = ngx.location.capture("/acs/api/v1/users/" .. uid)
    if res.status ~= ngx.HTTP_OK then
        ngx.log(ngx.ERR, "User not found: `" .. uid .. "`")
        return exit_401()
    end
    -- set authorization header back to basic
    if auth_header ~= nil then
        if string.find(auth_header, "Basic") then
            ngx.log(ngx.DEBUG, "Setting authorization header back to basic.")
            ngx.req.set_header("Authorization", auth_header)
        else
            if basichttpcred ~= nil then
	        ngx.log(ngx.DEBUG, "auth_header is token type set authorization to basic.")
	        ngx.req.set_header("Authorization" , "Basic " .. util.base64encode(basichttpcred))
            end
        end
    else
        if basichttpcred ~= nil then
            ngx.log(ngx.DEBUG, "auth_header nil set authorization to basic.")
            ngx.req.set_header("Authorization" , "Basic " .. util.base64encode(basichttpcred))
        end
    end

    return uid
end


-- Expose interface.
local _M = {}
_M.validate_jwt_or_exit = validate_jwt_or_exit


return _M
