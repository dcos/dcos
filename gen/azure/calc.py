entry = {
    'must': {
        'resolvers': '["168.63.129.16"]',
        'ip_detect_filename': 'gen/ip-detect/azure.sh',
        'master_discovery': 'static',
        'exhibitor_storage_backend': 'azure',
        'master_cloud_config': '{{ master_cloud_config }}',
        'slave_cloud_config': '{{ slave_cloud_config }}',
        'slave_public_cloud_config': '{{ slave_public_cloud_config }}',
        'oauth_enabled': "[[[variables('oauthEnabled')]]]",
        'oauth_available': 'true'
    }
}
