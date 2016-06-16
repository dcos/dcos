import analytics
import os
import uuid

from dcos_installer import backend


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

        # We set customer key from config to avoid loading the config during class init
        customer_key = backend.get_config().get("customer_key", None)

        analytics.track(user_id=customer_key, anonymous_id=self.uuid, event=action, properties={
            "provider": "onprem",
            "source": "installer",
            "variant": os.environ["BOOTSTRAP_VARIANT"],
            "install_id": self.uuid,
            "bootstrap_id": os.environ["BOOTSTRAP_ID"],
            "install_method": install_method,
            "stage": action,
            "errors": num_errors,
            "customerKey": customer_key,
        })
        analytics.flush()
