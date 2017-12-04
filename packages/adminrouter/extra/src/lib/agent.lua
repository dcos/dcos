local function resolve()
    local state = cache.get_cache_entry("mesosstate")

    if state == nil then
        return util.exit_by_code(503, nil, "cache state is invalid")
    end

    agent_pid = state['agent_pids'][ngx.var.agentid]
    if agent_pid ~= nil then
        local split_pid = agent_pid:split("@")
        local host_port = split_pid[2]:split(":")
        ngx.var.agentaddr = DEFAULT_SCHEME .. host_port[1]
        ngx.var.agentport = host_port[2]

        ngx.log(
            ngx.DEBUG, "agentid / agentaddr:" ..
            ngx.var.agentid .. " / " .. ngx.var.agentaddr
            )
        return
    end

    return util.exit_by_code(404, nil, "agent `" .. ngx.var.agentid .. "` unknown.")
end

-- Initialise and return the module:
local _M = {}
function _M.init()
    local res = {}

    res.resolve = resolve

    return res
end

return _M
