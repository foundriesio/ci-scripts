import unittest

from apps.publish_manifest_lists import compose_tagged_uri


class ManifestListPublishing(unittest.TestCase):
    def test_tagged_uri_composing(self):
        factory = "_devel-arduino_"
        app_name = "python-_devel-arduino_"
        build_num = "459"
        latest_tag = "_devel-arduino_"

        uris = [
            (
                f"hub.foundries.io_{factory}_{app_name}-{build_num}_d09aa17",
                f"hub.foundries.io/{factory}/{app_name}:{build_num}_d09aa17",
            ),
            (
                f"hub.foundries.io_{factory}_{app_name}-{build_num}_d09aa17a",
                f"hub.foundries.io/{factory}/{app_name}:{build_num}_d09aa17a",
            ),
            (
                # `latest_tag` contains dashes
                # `app_name` contains `latest_tag`
                # `latest_tag` matches `factory` with underscores
                f"hub.foundries.io_{factory}_{app_name}-{latest_tag}",
                f"hub.foundries.io/{factory}/{app_name}:{latest_tag}",
            )
        ]

        for u in uris:
            res_uri = compose_tagged_uri(factory, u[0], build_num, latest_tag)
            self.assertEqual(u[1], res_uri)

