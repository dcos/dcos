import azure.common.credentials
import azure.mgmt.network
import azure.mgmt.resource

subscription_id = 'get_me'
group = 'get_me'
client_id = 'get_me',
secret = 'get_me',
tenant = 'get_me'

# Connect to azure
credentials = azure.common.credentials.ServicePrincipalCredentials(client_id, secret, tenant)


rmc = azure.mgmt.resource.ResourceManagementClient(credentials, subscription_id)
nmc = azure.mgmt.network.NetworkManagementClient(credentials, subscription_id)

# Get the ips of the nics we care about, grouped by instance kind.
buckets = {
    'masterNodeNic': [],
    'slavePrivateNic': [],
    'slavePublicNic': []
}


def try_get_bucket(name):
    for bucket_name, bucket in buckets.items():
        if name.startswith(bucket_name):
            return bucket
    return None


def lookup_ip(name):
    nic = nmc.network_interfaces.get(group, name)
    all_ips = []
    for config in nic.ip_configurations:
        all_ips.append(config.private_ip_address)
    assert len(all_ips) == 1
    return all_ips[0]

resources_we_want = list()
for resource in rmc.resource_groups.list_resources(group):
    bucket = try_get_bucket(resource.name)
    if bucket is None:
        continue

    bucket.append(lookup_ip(resource.name))

print(buckets)
