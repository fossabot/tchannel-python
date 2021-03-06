# Copyright (c) 2016 Uber Technologies, Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from __future__ import absolute_import

import six
import inspect


def get_service_methods(iface):
    """Get a list of methods defined in the interface for a Thrift service.

    :param iface:
        The Thrift-generated Iface class defining the interface for the
        service.
    :returns:
        A set containing names of the methods defined for the service.
    """

    if six.PY3:
        methods = [func
                   for func in dir(iface)
                   if callable(getattr(iface,
                                       func)) and not func.startswith("__")]
        return set(methods)

    methods = inspect.getmembers(iface, predicate=inspect.ismethod)

    return set(
        name for (name, method) in methods if not name.startswith('__')
    )


def get_module_name(module):
    name = module.__name__.rsplit('.', 1)[-1]

    return name
