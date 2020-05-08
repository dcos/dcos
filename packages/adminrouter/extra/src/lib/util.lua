local cjson_safe = require "cjson.safe"
local cookiejar = require "resty.cookie"


local util = {}


function util.clear_dcos_cookies()
    -- This function removes dcos-specific cookies from the request header.
    --
    -- This prevents forwarding these cookies upstream as they are an internal
    -- implementation detail and services behind AR must only rely on
    -- Authorization header.
    --
    -- Cookie filtering was implemented in Lua because:
    -- * the `$cookie_<cookie_name>` variables are read-only
    --   (http://nginx.org/en/docs/http/ngx_http_core_module.html#variables)
    -- * reliable editing of Cookie header using Nginx requires using Ifs
    --   (https://www.nginx.com/resources/wiki/start/topics/depth/ifisevil/)
    --   and the regexps themselves are not trivial. E.g.
    --   ```
    --   set $new_cookie $http_cookie;
    --   if ($new_cookie ~ "(.*)(?:^|;)\s*dcos-acs-auth-cookie=[^;]+(.*)") {
    --      set $new_cookie $1$2;
    --   }
    --   if ($new_cookie ~ "(.*)(?:^|;)\s*dcos-acs-info-cookie=[^;]+(.*)") {
    --      set $new_cookie $1$2;
    --   }
    --   proxy_set_header Cookie "new_cookie";
    --   ```
    --
    -- Besides that, the `resty.cookie` library can't remove cookies from the
    -- request, but has pretty good cookie parser. So the idea is to use the
    -- parser and re-assemble the header without the dcos-* cookies.

    local filtered_cookies = {}
    local cookie_obj = cookiejar:new()

    local cookies, err = cookie_obj:get_all()
    if err then
        -- Cookie header is not present
        return
    end

    for k, v in pairs(cookies) do
        if k ~= "dcos-acs-auth-cookie" and k ~= "dcos-acs-info-cookie" then
            filtered_cookies[#filtered_cookies+1] = k .. "=" .. v
        end
    end

    -- Upstream request will inherit headers, so lets adjust the Cookie header
    -- before sending it upstream:
    -- https://github.com/openresty/lua-nginx-module/issues/437#issuecomment-65697745
    if filtered_cookies == {} then
        -- There were only DC/OS specific cookies
        ngx.req.set_header("Cookie", nil)
    else
        -- Forward user's cookies as-is
        ngx.req.set_header("Cookie", table.concat(filtered_cookies, "; "))
    end
end

function util.get_stripped_first_line_from_file(path)
    -- Return nil when file is emtpy.
    -- Return nil open I/O error.
    -- Log I/O error details.
    local f, err = io.open(path, "rb")
    if f then
        -- *l read mode: read line skipping EOL, return nil on end of file.
        local line = f:read("*l")
        f:close()
        if line then
            return line:strip()
        end
        ngx.log(ngx.ERR, "File is empty: " .. path)
        return nil
    end
    ngx.log(ngx.ERR, "Error reading file `" .. path .. "`: " .. err)
    return nil
end


function util.path_join(d, p)
    -- package.config:sub(1,1) is \ on Windows and / elsewhere
    return d .. package.config:sub(1,1) .. p
end


function util.get_file_content(path)
    local f, err = io.open(path, "rb")
    if f then
        -- *a read mode: read entire file.
        local content = f:read("*a")
        f:close()
        return content
    end
    ngx.log(ngx.ERR, "Error reading file `" .. path .. "`: " .. err)
    return nil
end


function util.set_leader_host(leader_name, local_upstream, skip_prefix_iflocal)
    -- This function is used in location blocks which require proxying requests
    -- to the AR instance or backend which is collocated with the leader named
    -- in `leader_name` argument.
    --
    -- It sets the ngx.var.leader_host to the value
    -- determined by looking at the `<leader_name>_leader` cache entry and the
    -- `local_upstream` parameter. If this instance of AR is collocated with
    -- the given leader, the ngx.var.leader_host is set to the value passed in
    -- `local_upstream`. If not - it is forwarded to the AR instance collocated
    -- with the leader.
    --
    -- In order to prevent loops, `DCOS-Forwarded` header is set while proxying
    -- for the first time. Any request which is to be proxied AND has this
    -- header set will be terminated.
    --
    -- Arguments:
    -- leader_name: name of the leader (i.e. "mesos/marathon/etc..") to fetch
    --     from cache
    -- local_upstream: to what value should the ngx.var.leader_host be set to
    --     in case when this instance is the local instance.
    -- skip_localprefix_iflocal: some of the location blocks require that
    --     a certain URL prefix needs to be stripped before proxying to the
    --     leading AR instance. This argument defines this prefix.
    local mleader = cache.get_cache_entry(leader_name .. "_leader")
    if mleader == nil then
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.say("503 Service Unavailable: cache is invalid")
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end

    if mleader['is_local'] == "unknown" then
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.say("503 Service Unavailable: " .. leader_name .. " leader is unknown.")
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end

    if mleader['is_local'] == 'yes' then
        ngx.var.leader_host = local_upstream
    else
        -- Let's prevent infinite proxy loops during failovers. Prefixing
        -- custom headers with `X-` is no longer recommended:
        -- http://stackoverflow.com/questions/3561381/custom-http-headers-naming-conventions
        if ngx.req.get_headers()["DCOS-Forwarded"] == "true" then
            ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
            ngx.say("503 Service Unavailable: " .. leader_name .. " leader is unknown")
            return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
        else
            ngx.req.set_header("DCOS-Forwarded", "true")
        end
        ngx.var.leader_host = init.DEFAULT_SCHEME .. mleader["leader_ip"]
    end

    ngx.log(ngx.DEBUG, leader_name .. " leader addr from cache: " .. ngx.var.leader_host)
end


function util.verify_ip(ip)
  -- Based on http://stackoverflow.com/a/16643628
  -- Return True if ip is a valid IPv4 IP, False otherwise.
  if type(ip) ~= "string" then return false end

  -- check for format 1.11.111.111 for ipv4
  local chunks = {ip:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")}
  if #chunks == 4 then
    for _, v in pairs(chunks) do
      if tonumber(v) > 255 then return false end
    end
    return true
  end

  return false
end


function util.table_len(tbl)
    -- Return the length of the table, without the limitations of #tbl
    -- approach, where nil value in the table terminates counting/acts as the
    -- end of the table.
    local count = 0
    for _ in pairs(tbl) do count = count + 1 end
    return count
end


function util.reverse(tbl)
    -- Reverse in-place given table
    local tl = util.table_len(tbl)

    for i=1, math.floor(tl / 2) do
        local tmp = tbl[i]
        tbl[i] = tbl[tl - i + 1]
        tbl[tl - i + 1] = tmp
    end
end


function util.extract_service_path_component(service_path, fieldsLimit)
    -- Extract path component in normalized form, at given level.
    --
    -- This function extracts from given service path the normalized service id
    -- at a given level, defined by fieldsLimit.For example:
    --
    -- service_path group1/jenkins/ver/important/path/foobar.js
    --
    -- will yield following results, depending on fieldsLimit parameter:
    -- nil:
    --   normalised_name: foobar.js.path.important.ver.jenkins.group1
    --   plain_name: group1/jenkins/ver/important/path/foobar.js
    --   moreSegments: false
    -- 4:
    --   normalised_name: important.ver.jenkins.group1
    --   plain_name: group1/jenkins/ver/important
    --   moreSegments: true
    -- 3:
    --   normalised_name: ver.jenkins.group1
    --   plain_name: group1/jenkins/ver
    --   moreSegments: true
    -- 2:
    --   normalised_name: jenkins.group1
    --   plain_name: group1/jenkins
    --   moreSegments: true
    -- 1:
    --   normalised_name: group1
    --   plain_name: group1
    --   moreSegments: true
    --
    -- Returns:
    --   A list with following elements, in order:
    --     - normalised_name: service name in normalized form
    --     - plain_name: service name in plain form
    --     - moreSegments: true/false depending on whether all segments
    --       service_path were processed or not.
    local tmpTbl = {}
    local moreSegments = false

    if service_path:len() > 0 then
        fieldsLimit = fieldsLimit or -1

        local fieldCursor, searchCursor = 1, 1
        local substrStart, _ = service_path:find('/', searchCursor, true)
        while substrStart and fieldsLimit ~= 0 do
            if substrStart ~= searchCursor then
                tmpTbl[fieldCursor] = service_path:sub(searchCursor, substrStart-1)
                fieldsLimit = fieldsLimit-1
                fieldCursor = fieldCursor+1
            end
            searchCursor = substrStart+1
            substrStart,substrStart = service_path:find('/', searchCursor, true)
        end
        if searchCursor < service_path:len() then
            if fieldsLimit ~= 0 then
                tmpTbl[fieldCursor] = service_path:sub(searchCursor)
            else
                moreSegments = true
            end
        end
    end

    local plain_name = table.concat(tmpTbl, "/")
    util.reverse(tmpTbl)
    local normalised_name = table.concat(tmpTbl, ".")

    return normalised_name, plain_name, moreSegments
end


function util.normalize_service_name(serviceName, fieldsLimit)
    -- Normalize service name
    --
    -- Different services (Marathon&Mesos vs. MesosDNS) use different formats
    -- for the service name. So the idea is that in the cache we store it in
    -- standardised format:
    --
    -- service name: group1/group2/foobar
    -- normalized: foobar.group2.group1
    --
    -- For the convienience we use MesosDNS notation (dots+reversing) in favour
    -- of Marathon&Mesos(just path) as it simplifies the code a bit.

    local ret, _, _ = util.extract_service_path_component(serviceName, nil)

    return ret
end


-- Monkey-patch string table.

function string:split(sep)
    local sep, fields = sep or " ", {}
    local pattern = string.format("([^%s]+)", sep)
    self:gsub(pattern, function(c) fields[#fields+1] = c end)
    return fields
end


function string.startswith(str, prefix)
    return string.sub(str, 1, string.len(prefix)) == prefix
end


function string:strip()
    -- Strip leading and trailing whitespace.
    -- Ref: http://lua-users.org/wiki/StringTrim
    return self:match "^%s*(.-)%s*$"
end


return util
