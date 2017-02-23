ngx.header.content_type = 'application/json'

local ip_prog = io.popen('/opt/mesosphere/bin/detect_ip_public')
local public_ip = ip_prog:read()
ip_prog:close()

if not public_ip then
    public_ip = ngx.var.server_addr
end

local cluster_id = io.open('/var/lib/dcos/cluster-id', 'r')

if cluster_id == nil
then
    ngx.say('{"PUBLIC_IPV4": "' .. public_ip .. '"}')
else
    ngx.say('{"PUBLIC_IPV4": "' .. public_ip .. '", "CLUSTER_ID": "' .. cluster_id:read() .. '"}')
end
