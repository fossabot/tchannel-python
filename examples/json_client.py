#!/usr/bin/env python

# Copyright (c) 2015 Uber Technologies, Inc.
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

import tornado.ioloop
import tornado.iostream

from options import get_args
from tchannel.tornado import TChannel
from tchannel.tornado.broker import ArgSchemeBroker
from tchannel.scheme import JsonArgScheme


@tornado.gen.coroutine
def main():

    args = get_args()

    tchannel = TChannel(name='json-client')

    # TODO: Make this API friendly.
    request = tchannel.request(
        hostport='%s:%s' % (args.host, args.port),
    )

    response = yield ArgSchemeBroker(JsonArgScheme()).send(
        request,
        'hi-json',
        None,
        None,
    )

    body = yield response.get_body()

    print body['hi']


if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(main)
