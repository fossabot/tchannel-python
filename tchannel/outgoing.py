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

import enum
import socket
import Queue as queue
from collections import namedtuple
from threading import Lock, Thread
from functools import partial

from .socket import SocketConnection
from .futures import SettableFuture, transform_future
from .messages import CallRequestMessage
from .exceptions import TChannelApplicationException


class TChannelOutOps(object):
    """Encapsulates outgoing operations for a TChannel connection.

    Each connection has a sending and receiving thread that goes with it."""

    Request = namedtuple('Request', 'message, future')

    TIMEOUT = 0.5

    @enum.unique
    class State(enum.IntEnum):
        init = 0
        ready = 1
        closed = 2

    def __init__(self, name, sock, on_close=None, perform_handshake=True,
                 timeout=None):
        """Initialize a TChannelOutOps.

        :param name:
            Name of the current process.
        :param sock:
            Socket connection to the destination
        :param on_close:
            Function to call (without `self` as the only argument) when the
            connection is closed
        :param perform_handshake:
            If True (the default), perform a handshake with the remote host
            immediately
        """
        self._name = name
        self._sock = sock
        self._conn = SocketConnection(self._sock)

        self._state = self.State.init
        self._outstanding = queue.Queue()
        self._on_close = on_close or (lambda x: x)

        self._sender = Thread(target=self._start_sender)
        self._receiver = Thread(target=self._start_receiver)
        self._timeout = timeout or self.TIMEOUT
        self._id_counter = 0
        self._counter_lock = Lock()

        if perform_handshake:
            self.handshake()

        self._futures = {}
        self._sender.start()
        self._receiver.start()

    def _submit(self, message, future):
        """Submit the given message for sending.

        Returns immediately.

        :param message:
            Message to be sent.
        :param future:
            Future to which the response for this message will be written.
        """
        self._outstanding.put(self.Request(message, future))

    def _next_message_id(self):
        """Return the next available message ID."""
        with self._counter_lock:
            self._id_counter += 1
            return self._id_counter

    def _start_sender(self):
        """Responsible for sending requests over the wire.

        The sender monitors the `_outstanding` queue and writes incoming
        requests down the connection. The future for each request is recorded
        in `_futures`.
        """
        while not self.closed():
            try:
                request = self._outstanding.get(timeout=self._timeout)
            except queue.Empty:
                continue

            if request is None:
                break

            msg = request.message
            if msg is None:
                break

            msg_id = self._next_message_id()
            self._futures[msg_id] = request.future

            self._conn.frame_and_write(msg, message_id=msg_id)

    def _start_receiver(self):
        """Responsible for receiving and dispatching requests.

        The receiver polls the connection for incoming frames and dispatches
        the responses to the correct future based on the message ID.
        """
        while not self.closed():
            try:
                ctx = self._conn.await()
            except socket.timeout:
                continue
            if ctx is None:
                break  # end of stream
            self._futures[ctx.message_id].set_result(ctx.message)
            # TODO: We should probably discard the frame if it didn't have a
            # corresponding future.

    def handshake(self):
        """Perform a handshake with the remote host over the given connection.

        No-op if the handshake was already performed.
        """
        assert (
            not self._state == self.State.closed
        ), "The connection to %s:%s has already been terminated." % (
            self.host, self.port
        )

        if self._state != self.State.init:
            return

        self._conn.initiate_handshake({
            'host_port': '0.0.0.0:0',  # We can't receive requests
            'process_name': self._name
        })
        resp = self._conn.await_handshake_reply()
        self._state = self.State.ready
        return resp

    def send(self, arg_1, arg_2, arg_3, service=None, async=False):
        """Send the given arguments over the wire.

        ``arg_1``, ``arg_2``, and ``arg_3`` represent the triple being sent
        over the wire.

        `service` is the name of the service being called. It defaults to an
        empty string.

        :param async:
            Whether this should block for the response. The function returns a
            Future if True.
        :raises TChannelApplicationException:
            If the remote server did not respond with status code 0.
        """
        assert (
            self._state == self.State.ready
        ), "Handshake not performed or connection closed"

        msg = CallRequestMessage(arg_1=arg_1, arg_2=arg_2, arg_3=arg_3)

        future = SettableFuture()
        self._submit(msg, future)

        def handle_response(response):
            if response.code != 0:
                raise TChannelApplicationException(
                    response.code,
                    response.arg_1,
                    response.arg_2,
                    response.arg_3,
                )
            return response

        result_future = transform_future(future, handle_response)
        if async:
            return result_future
        else:
            # Wait till the response for this message has been received.
            return result_future.result()  # TODO: timeout?

    def closed(self):
        """Returns True if the connection has been closed."""
        return self._state == self.State.closed

    def close(self, wait=True):
        """Manually close this connection

        It is generally not necessary to call this manually because the
        TChannel instance will clean up after itself.
        """
        if self.closed():
            return
        self._state = self.State.closed

        # A None request informs the sender it's time to go.
        self._outstanding.put(None)
        self._sender.join()

        # Closing the socket should stop the receiver waiting.
        self._sock.close()
        self._receiver.join()

        self._on_close(self)

    def __del__(self):
        try:
            self.close()
        except:
            pass


class OutgoingTChannel(object):
    """Manages outgoing TChannel connections.

    Example usage,

    .. code-block::

        with OutgoingTChannel('service_name') as chan:
            resp = chan.request('localhost:4040').send(
                'func 1', 'arg 1', 'arg 2'
            )

            resp_future = chan.request('localhost:4040').send(
                'func 1', 'arg 1', 'arg 2', async=True
            )

    All open connections are automatically closed when the context manager
    exits.
    """

    TIMEOUT = 0.5

    def __init__(self, name, timeout=None):
        """Initialize an OutgoingTChannel with the given process name.

        :param name:
            Process name used when talking to remote servers. This is used for
            logging only.
        """
        assert name, 'A process name is required'
        self._name = name
        self._lock = Lock()
        self._connections = {}
        self._timeout = timeout or self.TIMEOUT

    def _get_connection(self, host, port):
        """Get a TChannel connection to the given destination.

        :param host:
            Remote host
        :param port:
            Port to connect on
        """
        assert host, "host is required"
        assert port, "port is required"

        conn = self._connections.get((host, port))
        if conn:
            return conn

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        sock.settimeout(self._timeout)

        with self._lock:
            if (host, port) in self._connections:
                # Someone else established the connection while we were
                # waiting.
                sock.close()
                return self._connections[(host, port)]
            conn = self._connections[(host, port)] = TChannelOutOps(
                self._name,
                sock,
                on_close=partial(self._on_conn_close, host, port),
                timeout=self._timeout,
            )

        return conn

    def _on_conn_close(self, host, port, connection):
        with self._lock:
            if (host, port) in self._connections:
                # `is` check instead of == because we want to ensure that
                # we're not accidentally removing a different connection for
                # the same host:port.
                if self._connections[(host, port)] is connection:
                    del self._connections[(host, port)]

    def request(self, host, port=None):
        """Prepare to make a request to the given destination.

        Accepts either a `host` and `port` specifying the destination, or a
        string in the form `host:port`. This call sets up a connection to the
        destination right away (if one did not already exist). The returned
        object can be used to make calls to the destination.

        .. code-block::

            conn = chan.request('localhost:4040')
            try:
                (a, b, c) = conn.send('/health-check', '', '')
            except TChannelApplicationException as e:
                (d, e, f) = e.arg_1, e.arg_2, e.arg_3

        :param host:
            Remote host
        :param port:
            Port on the remote host
        """
        if not port:
            host, port = host.rsplit(':', 1)
        port = int(port)
        return self._get_connection(host, port)

    def close(self):
        for conn in self._connections.values():
            try:
                conn.close()
            except socket.error:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        try:
            self.close()
        except:
            pass
