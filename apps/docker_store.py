import hashlib
import json
import os.path
import subprocess


class DockerStore:
    _REPO_PATH = "image/overlay2/repositories.json"

    class Layer:
        _LAYER_DB_PATH = "image/overlay2/layerdb/sha256"
        _LAYER_DATA_BASE_PATH = "overlay2"
        _SUPPORTED_HASH_TYPE = "sha256:"

        def __init__(self, data_root, layer_digest, layer_diff_id, parent_chain_id):
            self._data_root = data_root
            self.diff_id = layer_diff_id
            self.digest = layer_digest
            self.chain_id = self._get_chain_id(parent_chain_id)
            # Wire/transfer size (in bytes) of unarchived layer
            self.size = self._get_layer_size_from_meta()
            self.cache_id = self._get_cache_id()
            self.data_path = os.path.join(self._data_root, self._LAYER_DATA_BASE_PATH,
                                          self.cache_id)

            # Disk usage (in bytes) of unarchived layer taking into account the volume block size
            self.usage = self._get_disk_usage()
            # Disk usage (in bytes) of unarchived layer along with metadata
            # taking into account the volume block size
            self.usage_with_meta = self._get_disk_usage_with_metadata()
            # Size of the file containing metadata about the layer's TAR stream.
            # It's stored in
            # `<docker-data-root>/image/overlay2/layerdb/sha256/<chainID>/tar-split.json.gz
            # It can be used to partially "fsck" layer data/files on disk based on file/dir names
            # and their sizes stored in the "tar-split" file.
            # E.g. `tar-split a --input <path to tar-split.json.gz> \
            #                   --path <docker-data-root>/overlay2/<cacheID>/diff/>
            #                   --output /dev/null`
            self.tar_split_size = self._get_tar_split_size()
            self.overall_usage = self.usage_with_meta + self.tar_split_size

        def _get_chain_id(self, parent_chain_id):
            if not parent_chain_id:
                return self.diff_id
            bytes = parent_chain_id + " " + self.diff_id
            return self._SUPPORTED_HASH_TYPE + hashlib.sha256(bytes.encode('utf-8')).hexdigest()

        def _get_layer_size_from_meta(self):
            size_file = os.path.join(self._data_root, self._LAYER_DB_PATH,
                                     self.chain_id[len(self._SUPPORTED_HASH_TYPE):], "size")
            if not os.path.exists(size_file):
                raise Exception(f"Layer size file is missing: {size_file}")
            with open(size_file) as f:
                size_str = f.readline()
            return int(size_str)

        def _get_cache_id(self):
            cache_id_file = os.path.join(self._data_root, self._LAYER_DB_PATH,
                                         self.chain_id[len(self._SUPPORTED_HASH_TYPE):], "cache-id")
            if not os.path.exists(cache_id_file):
                raise Exception(f"Layer cache-id file is missing: {cache_id_file}")
            with open(cache_id_file) as f:
                cache_id = f.readline()
            return cache_id

        def _get_disk_usage_with_metadata(self):
            # get disk usage of the layer diff/rootfs along with its metadata
            # taking into account a block size
            du_output = subprocess.check_output("du -sk " + self.data_path, shell=True)
            return int(du_output.decode().split()[0])*1024

        def _get_disk_usage(self):
            # get disk usage of the layer diff/rootfs taking into account a block size
            du_output = subprocess.check_output("du -sk " + self.data_path + "/diff", shell=True)
            return int(du_output.decode().split()[0])*1024

        def _get_tar_split_size(self):
            tar_split_file = os.path.join(self._data_root, self._LAYER_DB_PATH,
                                          self.chain_id[len(self._SUPPORTED_HASH_TYPE):],
                                          "tar-split.json.gz")
            if not os.path.exists(tar_split_file):
                raise Exception(f"Layer tar_split file is missing: {tar_split_file}")

            return os.path.getsize(tar_split_file)

    class Image:
        _IMAGE_DB_ROOT_PATH = "image/overlay2/imagedb"
        _IMAGE_DB_CONTENT_PATH = "content/sha256"
        _SUPPORTED_HASH_TYPE = "sha256:"
        _DISTRIBUTION_DIGEST_PATH = "image/overlay2/distribution/v2metadata-by-diffid/sha256"

        def __init__(self, image_ref, data_root, image_conf_hash):
            self._image_ref = image_ref
            self._data_root = data_root
            self._layer_digests = []
            if not image_conf_hash.startswith(self._SUPPORTED_HASH_TYPE):
                raise Exception(f"Unsupported image config hash type: {image_conf_hash}")

            image_conf_path = os.path.join(data_root,
                                           self._IMAGE_DB_ROOT_PATH, self._IMAGE_DB_CONTENT_PATH,
                                           image_conf_hash[len(self._SUPPORTED_HASH_TYPE):])
            if not os.path.exists(image_conf_path):
                raise Exception(f"Image config has not been found in: {image_conf_path}")

            self.layers = []
            self.conf_hash = image_conf_hash
            with open(image_conf_path) as f:
                image_conf = json.load(f)
                cur_chain_id = None
                layer_indx = 0
                for layer_diff_id in image_conf["rootfs"]["diff_ids"]:
                    layer_digest = self.get_layer_digest(layer_diff_id, layer_indx)
                    layer = DockerStore.Layer(data_root, layer_digest, layer_diff_id, cur_chain_id)
                    self.layers.append(layer)
                    cur_chain_id = layer.chain_id
                    layer_indx += 1

        def get_layer_digest(self, diff_id, idx):
            # If image layer digests were fetched before then just get the given layer digest value
            # by its index. The image spec guarantees that order of layer diffIDs and digests listed
            # in an image config and manifest respectively is the same - it starts from the base
            # layer up to the top image layer.
            if len(self._layer_digests) > idx:
                return self._layer_digests[idx]

            # If image layers digests were not fetched then try to get it from
            # the image/overlay2/distribution/v2metadata-by-diffid/ where the mapping between
            # diffID and digest is supposed to be stored if an image was `docker pull` or
            # `docker push`.
            digest_file_path = os.path.join(self._data_root, self._DISTRIBUTION_DIGEST_PATH,
                                            diff_id[len(self._SUPPORTED_HASH_TYPE):])
            if os.path.exists(digest_file_path):
                with open(digest_file_path) as f:
                    digests = json.load(f)
                    return digests[0]["Digest"]
            else:
                print(f"Image layer diff ID to digest mapping is not found in: {digest_file_path}, "
                      f"fetching image manifest to get its layer digests; uri: {self._image_ref}...")
                output = subprocess.check_output(
                    ["skopeo", "inspect", f"docker://{self._image_ref}"])
                image_desc = json.loads(output)
                for layer in image_desc["Layers"]:
                    self._layer_digests.append(layer)

                if len(self._layer_digests) <= idx:
                    raise Exception("the number of image layer diffIDs and layer digests does not"
                                    f" match; digests number: {len(self._layer_digests)},"
                                    f" diffID index: {idx}, image: {self._image_ref}")

                return self._layer_digests[idx]

    def __init__(self, data_root="/var/lib/docker"):
        self.data_root = data_root
        self._cfg_to_image = {}
        self.images_by_ref = {}
        self._parse_repositories()

    def _parse_repositories(self):
        repos_file = os.path.join(self.data_root, self._REPO_PATH)
        if not os.path.exists(repos_file):
            raise Exception(f"No `repositories.json` is found in the docker store: {repos_file}")
        with open(repos_file) as f:
            repos = json.load(f)
            fs_stats = os.fstatvfs(f.fileno())
            self.fs_block_size = fs_stats.f_bsize

        for image_base_ref, image_refs in repos["Repositories"].items():
            for ref, image_conf_hash in image_refs.items():
                if image_conf_hash not in self._cfg_to_image:
                    self._cfg_to_image[image_conf_hash] = self.Image(ref, self.data_root, image_conf_hash)
                self.images_by_ref[ref] = self._cfg_to_image[image_conf_hash]
