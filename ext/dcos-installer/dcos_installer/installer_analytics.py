import analytics
import os
import uuid


class InstallerAnalytics():
    def __init__(self, config):
        self.uuid = self.new_uuid()
        self.bootstrap_version = os.getenv("BOOTSTRAP_ID")
        self.customer_key = config["customer_key"] if 'customer_key' in config else ""
        self.source = "onprem"  # If you're using the installer you're not in AWS or Azure

    def send(self, action, install_method, num_errors):
        """Sends analytics track data to segmentIO.
        variant: string | open or enterprise
        action: string | preflight, deploy, or postflight
        install_method: string | gui, cli or advanced
        """
        analytics.write_key = "39uhSEOoRHMw6cMR6st9tYXDbAL3JSaP"

        analytics.track(user_id=self.customer_key, anonymous_id=self.uuid, event=action, properties={
            "install_id": self.uuid,
            "bootstrap_id": self.bootstrap_version,
            "provider": self.source,
            "source": "installer",
            "install_method": install_method,
            "stage": action,
            "errors": num_errors,
            "customer_key": self.customer_key,
        })
        analytics.flush()

    def new_uuid(self):
        return str(uuid.uuid4())
