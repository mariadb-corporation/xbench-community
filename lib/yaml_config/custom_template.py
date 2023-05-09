# -*- coding: utf-8 -*-
# Copyright (C) 2020 dvolkov

"""

Purpose of this file is provide template engine when you can pass uppercase arguments
$POD will be translating into NA44, while $pod to the na44 and so forth.

I use tha fact that original Template module is case sensitive and I found a parameter with upper case I extend initial dict before passing
to the Template
"""

from string import Template, ascii_uppercase, _ChainMap


def get_mapping_from_args(*args, **kws):
    if len(args) > 1:
        raise TypeError("Too many positional arguments")
    if not args:
        mapping = kws
    elif kws:
        mapping = _ChainMap(kws, args[0])
    else:
        mapping = args[0]
    return mapping


class CustomTemplate(Template):
    def __init__(self, *args, **kws):
        super(CustomTemplate, self).__init__(*args, **kws)
        self.orig_template = self.template
        self.template = self.template

    def do_template_based_capitalization(self, mapping):
        matches = self.pattern.findall(self.orig_template)
        for match in matches:
            keyword = match[self.pattern.groupindex["braced"] - 1]
            if (len(keyword) > 0) and (
                keyword[0] in ascii_uppercase
            ):  # First letter is CAPITALIZED
                if keyword == keyword.upper():  # Condition for full capitalization
                    mapping[keyword.upper()] = mapping[
                        keyword.lower()
                    ].upper()  # I extend the initial dictionary
                else:  # Condition for only first letter capitalization
                    mapping[keyword.capitalize()] = mapping[
                        keyword.lower()
                    ].capitalize()

    def safe_substitute(self, *args, **kws):
        mapping = get_mapping_from_args(*args, **kws)
        self.do_template_based_capitalization(mapping)
        return super(CustomTemplate, self).safe_substitute(mapping)

    def substitute(self, *args, **kws):
        mapping = get_mapping_from_args(*args, **kws)
        self.do_template_based_capitalization(mapping)
        return super(CustomTemplate, self).substitute(mapping)


# High level API
def substitute(query, values):
    t = CustomTemplate(query)
    return t.safe_substitute(values)
