import json
import tempfile
import unittest
from pathlib import Path

from apps.docker_store import get_source_repository, DockerStore


class GetSourceRepositoryTests(unittest.TestCase):
    def test_reference_with_tag(self):
        image_ref = (
            "ghcr.io/linux-validation/lava/"
            "lava-server-amd64:2026.05-qualcomm-2026.05-22-d5988428c"
        )

        self.assertEqual(
            get_source_repository(image_ref),
            "ghcr.io/linux-validation/lava/lava-server-amd64",
        )

    def test_reference_with_digest(self):
        image_ref = (
            "ghcr.io/linux-validation/lava/"
            "lava-server-amd64@sha256:0123456789abcdef"
        )

        self.assertEqual(
            get_source_repository(image_ref),
            "ghcr.io/linux-validation/lava/lava-server-amd64",
        )

    def test_reference_with_tag_and_digest(self):
        image_ref = (
            "ghcr.io/linux-validation/lava/"
            "lava-server-amd64:latest@sha256:0123456789abcdef"
        )

        self.assertEqual(
            get_source_repository(image_ref),
            "ghcr.io/linux-validation/lava/lava-server-amd64",
        )

    def test_registry_with_port(self):
        self.assertEqual(
            get_source_repository("localhost:5000/example/image:latest"),
            "localhost:5000/example/image",
        )

    def test_reference_without_tag_or_digest(self):
        self.assertEqual(
            get_source_repository("ghcr.io/example/image"),
            "ghcr.io/example/image",
        )

    def test_short_image_name_with_tag(self):
        self.assertEqual(
            get_source_repository("image:latest"),
            "image",
        )

    def test_empty_string(self):
        self.assertEqual(get_source_repository(""), "")

    def test_none(self):
        self.assertEqual(get_source_repository(None), "")

    def test_non_string(self):
        self.assertEqual(get_source_repository(123), "")


class GetLayerDigestTests(unittest.TestCase):
    def test_get_layer_digest_from_local_mapping(self):
        diff_id = "sha256:diff-id"
        expected_digest = "sha256:layer-digest"
        source_repository = "ghcr.io/example/image"

        with tempfile.TemporaryDirectory() as data_root:
            mapping_file = (
                Path(data_root)
                / DockerStore.Image._DISTRIBUTION_DIGEST_PATH
                / "diff-id"
            )
            mapping_file.parent.mkdir(parents=True)
            mapping_file.write_text(
                json.dumps(
                    [
                        {
                            "SourceRepository": source_repository,
                            "Digest": expected_digest,
                        }
                    ]
                )
            )

            image = DockerStore.Image.__new__(DockerStore.Image)
            image._data_root = data_root
            image._image_src_rep = source_repository
            image._image_ref = source_repository + ":latest"
            image._layer_digests = []

            self.assertEqual(
                image.get_layer_digest(diff_id, 0),
                expected_digest,
            )

    def test_get_layer_digest_selects_matching_source_repository(self):
        diff_id = "sha256:diff-id"
        source_repository = "ghcr.io/example/image"
        expected_digest = "sha256:digest-from-example-repo"

        with tempfile.TemporaryDirectory() as data_root:
            mapping_file = (
                    Path(data_root)
                    / DockerStore.Image._DISTRIBUTION_DIGEST_PATH
                    / "diff-id"
            )
            mapping_file.parent.mkdir(parents=True)
            mapping_file.write_text(
                json.dumps(
                    [
                        {
                            "SourceRepository": "ghcr.io/other/image",
                            "Digest": "sha256:digest-from-other-repo",
                        },
                        {
                            "SourceRepository": source_repository,
                            "Digest": expected_digest,
                        },
                    ]
                ),
                encoding="utf-8",
            )

            image = DockerStore.Image.__new__(DockerStore.Image)
            image._data_root = data_root
            image._image_src_rep = source_repository
            image._image_ref = source_repository + ":latest"
            image._layer_digests = []

            self.assertEqual(
                image.get_layer_digest(diff_id, 0),
                expected_digest,
            )


if __name__ == "__main__":
    unittest.main()
