#
# Copyright (c) 2019 Foundries.io
# SPDX-License-Identifier: BSD-3-Clause

class TagMgr:
    def __init__(self, ota_lite_tag=''):
        # Convert thinkgs like:
        #    tag1,tag2 -> [(tag1, tag1), (tag2, tag2)]
        #    tag1:blah,tag2 -> [(tag1, blah), (tag2, tag2)]
        self._tags = []
        for x in ota_lite_tag.split(','):
            parts = x.strip().split(':', 1)
            if len(parts) == 1 or parts[1] == '':
                self._tags.append((parts[0], parts[0]))
            else:
                self._tags.append((parts[0], parts[1]))

    def __repr__(self):
        return str(self._tags)

    @property
    def tags(self):
        return self._tags

    def intersection(self, tags):
        if self._tags == [('', '')]:
            # Factory doesn't use tags, so its good.
            # This empty value is special and understood by the caller
            yield ''
        else:
            for t in tags:
                for target, parent in self._tags:
                    if t == parent:
                        yield target

    def create_target_name(self, target, version, tag):
        name = target['custom']['name'] + '-' + version
        if len(self._tags) == 1:
            return name
        # we have more than one tag - so we need something else to make
        # this dictionary key name unique:
        return name + '-' + tag

    @property
    def target_tags(self):
        """Return the list of tags we should produce Targets for."""
        return [x[0] for x in self._tags]
