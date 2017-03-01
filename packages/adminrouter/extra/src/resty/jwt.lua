local cjson = require "cjson"
local evp = require "resty.evp"
local hmac = require "resty.hmac"

local _M = {_VERSION="0.1.1"}
local mt = {__index=_M}


local function get_raw_part(part_name, jwt_obj)
    local raw_part = jwt_obj["raw_" .. part_name]
    if raw_part == nil then
        local part = jwt_obj[part_name]
        if part == nil then
            error({reason="missing part " .. part_name})
        end
        raw_part = _M:jwt_encode(part)
    end
    return raw_part
end


local function parse(token_str)
    local basic_jwt = {}
    local raw_header, raw_payload, signature = string.match(
        token_str,
        '([^%.]+)%.([^%.]+)%.([^%.]+)'
    )
    local header = _M:jwt_decode(raw_header, true)
    if not header then
        error({reason="invalid header: " .. raw_header})
    end

    local payload = _M:jwt_decode(raw_payload, true)
    if not payload then
        error({reason="invalid payload: " .. raw_payload})
    end

    local basic_jwt = {
        raw_header=raw_header,
        raw_payload=raw_payload,
        header=header,
        payload=payload,
        signature=signature
    }
    return basic_jwt
end


function _M.jwt_encode(self, ori)
    if type(ori) == "table" then
        ori = cjson.encode(ori)
    end
    return ngx.encode_base64(ori):gsub("+", "-"):gsub("/", "_"):gsub("=", "")
end


function _M.jwt_decode(self, b64_str, json_decode)
    local reminder = #b64_str % 4
    if reminder > 0 then
        b64_str = b64_str .. string.rep("=", 4 - reminder)
    end
    local data = ngx.decode_base64(b64_str)
    if not data then
        return nil
    end
    if json_decode then
        data = cjson.decode(data)
    end
    return data
end

--- Initialize the trusted certs
-- During RS256 verify, we'll make sure the
-- cert was signed by one of these
function _M.set_trusted_certs_file(self, filename)
    self.trusted_certs_file = filename
end
_M.trusted_certs_file = nil

--- Set a whitelist of allowed algorithms
-- E.g., jwt:set_alg_whitelist({RS256=1,HS256=1})
--
-- @param algorithms - A table with keys for the supported algorithms
--                     If the table is non-nil, during
--                     verify, the alg must be in the table
function _M.set_alg_whitelist(self, algorithms)
    self.alg_whitelist = algorithms
end
_M.alg_whitelist = nil

function _M.sign(self, secret_key, jwt_obj)
    -- header typ check
    local typ = jwt_obj["header"]["typ"]
    if typ ~= "JWT" then
        error({reason="invalid typ: " .. typ})
    end

    -- assemble jwt parts
    local raw_header = get_raw_part("header", jwt_obj)
    local raw_payload = get_raw_part("payload", jwt_obj)

    local message =raw_header ..  "." ..  raw_payload

    -- header alg check
    local alg = jwt_obj["header"]["alg"]
    local signature = ""
    if alg == "HS256" then
        signature = hmac:new(secret_key, hmac.ALGOS.SHA256):final(message)
    elseif alg == "HS512" then
        signature = hmac:new(secret_key, hmac.ALGOS.SHA512):final(message)
    elseif alg == "RS256" then
        local signer, err = evp.RSASigner:new(secret_key)
        if not signer then
            error({reason="signer error: " .. err})
        end
        signature = signer:sign(message, evp.CONST.SHA256_DIGEST)
    else
        error({reason="unsupported alg: " .. alg})
    end
    -- return full jwt string
    return message .. "." .. _M:jwt_encode(signature)
end


function _M.load_jwt(self, jwt_str)
    local success, ret = pcall(parse, jwt_str)
    if not success then
        return {
            valid=false,
            verified=false,
            reason=ret["reason"] or "invalid jwt string"
        }
    end

    local jwt_obj = ret
    jwt_obj["verified"] = false
    jwt_obj["valid"] = true
    return jwt_obj
end


function _M.verify_jwt_obj(self, secret, jwt_obj, leeway)
    local jwt_str = jwt_obj.raw_header ..
        "." .. jwt_obj.raw_payload ..
        "." .. jwt_obj.signature

    if not jwt_obj.valid then
        return jwt_obj
    end
    local alg = jwt_obj["header"]["alg"]
    if self.alg_whitelist ~= nil then
        if self.alg_whitelist[alg] == nil then
            return {verified=false, reason="whitelist unsupported alg: " .. alg}
        end
    end
    if alg == "HS256" or alg == "HS512" then
        local success, ret = pcall(_M.sign, self, secret, jwt_obj)
        if not success then
            -- syntax check
            jwt_obj["reason"] = ret["reason"] or "internal error"
        elseif jwt_str ~= ret then
            -- signature check
            jwt_obj["reason"] = "signature mismatch: " .. jwt_obj["signature"]
        end
    elseif alg == "RS256" then
        local cert
        if self.trusted_certs_file ~= nil then
            local err, x5c = jwt_obj['header']['x5c']
            if not x5c or not x5c[1] then
                jwt_obj["reason"] = "Unsupported RS256 key model"
                return jwt_obj
                -- TODO - Implement jwk and kid based models...
            end
    
            -- TODO Might want to add support for intermediaries that we
            -- don't have in our trusted chain (items 2... if present)
            local cert_str = ngx.decode_base64(x5c[1])
            if not cert_str then
                jwt_obj["reason"] = "Malformed x5c header"
                return jwt_obj
            end
            cert, err = evp.Cert:new(cert_str)
            if not cert then
                jwt_obj["reason"] = "Unable to extract signing cert from JWT: " .. err
                return jwt_obj
            end
            -- Try validating against trusted CA's, then a cert passed as secret
            local trusted, err = cert:verify_trust(self.trusted_certs_file)
            if not trusted then
                jwt_obj["reason"] = "Cert used to sign the JWT isn't trusted: " .. err
                return jwt_obj
            end
        elseif secret ~= nil then
            local err
            cert, err = evp.Cert:new(secret)
            if not cert then
                jwt_obj["reason"] = "Decode secret is not a valid cert: " .. err
                return jwt_obj
            end
        else
            jwt_obj["reason"] = "No trusted certs loaded"
            return jwt_obj
        end
        local verifier, err = evp.RSAVerifier:new(cert)
        if not verifier then
            -- Internal error case, should not happen...
            jwt_obj["reason"] = "Failed to build verifier " .. err
            return jwt_obj
        end

        -- assemble jwt parts
        local raw_header = get_raw_part("header", jwt_obj)
        local raw_payload = get_raw_part("payload", jwt_obj)

        local message =raw_header ..  "." ..  raw_payload
        local sig = jwt_obj["signature"]:gsub("-", "+"):gsub("_", "/")
        local verified, err = verifier:verify(message, _M:jwt_decode(sig, false), evp.CONST.SHA256_DIGEST)
        if not verified then
            jwt_obj["reason"] = err
        end
    else
        jwt_obj["reason"] = "Unsupported algorithm " .. alg
    end

    local exp = jwt_obj["payload"]["exp"]
    local nbf = jwt_obj["payload"]["nbf"]

    if (exp ~= nil or nbf ~= nil ) and not jwt_obj["reason"] then
        leeway = leeway or 0
        local now = ngx.now()

        if type(exp) == "number" and exp < (now - leeway) then
            jwt_obj["reason"] = "jwt token expired at: " ..
                ngx.http_time(exp)
        elseif type(nbf) == "number" and nbf > (now + leeway) then
            jwt_obj["reason"] = "jwt token not valid until: " ..
                ngx.http_time(nbf)
        end
    end

    if not jwt_obj["reason"] then
        jwt_obj["verified"] = true
        jwt_obj["reason"] = "everything is awesome~ :p"
    end
    return jwt_obj
end


function _M.verify(self, secret, jwt_str, leeway)
    jwt_obj = _M.load_jwt(self, jwt_str)
    if not jwt_obj.valid then
         return {verified=false, reason=jwt_obj["reason"]}
    end

    return _M.verify_jwt_obj(self, secret, jwt_obj, leeway)
end

return _M
