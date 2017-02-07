import os
import uuid

import analytics

from dcos_installer.config import Config
from dcos_installer.constants import CONFIG_PATH


class InstallerAnalytics():
    def __init__(self):
        self.uuid = str(uuid.uuid4())

    def send(self, action, install_method, num_errors):
        """Sends analytics track data to segmentIO.
        variant: string | open or enterprise
        action: string | preflight, deploy, or postflight
        install_method: string | gui, cli or advanced
        """
        analytics.write_key = "51ybGTeFEFU1xo6u10XMDrr6kATFyRyh"

        # Set customer key here rather than __init__ since we want the most up to date config
        # and config may change between __init__ and here.
        config = Config(CONFIG_PATH)
        customer_key = config.hacky_default_get('customer_key', None)

        # provider is always onprem when the cli installer is used
        provider = "onprem"
        # platform defaults to provider value, if not specified
        platform = config.hacky_default_get('platform', provider)

        analytics.track(user_id=customer_key, anonymous_id=self.uuid, event="installer", properties={
            "platform": platform,
            "provider": provider,
            "source": "installer",
            "variant": os.environ["BOOTSTRAP_VARIANT"],
            "install_id": self.uuid,
            "bootstrap_id": os.environ["BOOTSTRAP_ID"],
            "install_method": install_method,
            "action_name": action,
            "errors": num_errors,
            "customerKey": customer_key,
        })
        analytics.flush()
