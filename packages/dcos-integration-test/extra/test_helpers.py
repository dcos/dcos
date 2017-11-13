from pkgpanda.util import load_json


def get_exhibitor_admin_password():
    try:
        with open('/opt/mesosphere/etc/exhibitor_realm', 'r') as f:
            exhibitor_realm = f.read().strip()
    except FileNotFoundError:
        # Unset. Return the default value.
        return ''

    creds = exhibitor_realm.split(':')[1].strip()
    password = creds.split(',')[0].strip()
    return password


expanded_config = load_json('/opt/mesosphere/etc/expanded.config.json')
# expanded.config.json doesn't contain secret values, so we need to read the Exhibitor admin password from
# Exhibitor's config.
# TODO: Remove this hack. https://jira.mesosphere.com/browse/QUALITY-1611
expanded_config['exhibitor_admin_password'] = get_exhibitor_admin_password()

dcos_config = expanded_config
