ngx.header.content_type = 'application/json'

local cluster_id = io.open('/var/lib/dcos/cluster-id', 'r')

if cluster_id == nil
then
    ngx.say('{"PUBLIC_IPV4": "' .. HOST_IP .. '"}')
else
    ngx.say('{"PUBLIC_IPV4": "' .. HOST_IP .. '", "CLUSTER_ID": "' .. cluster_id:read() .. '"}')
end
