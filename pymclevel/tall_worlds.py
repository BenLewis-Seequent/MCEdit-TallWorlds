"""
This file contains implementation of Tall World Level support
"""
import subprocess
import socket
import logging
import struct
import nbt
#from pymclevel import LightedChunk, ChunkedLevelMixin, EntityLevel, ChunkBase

log = logging.getLogger(__name__)

port = 25666


class _VM(object):
    def __init__(self, filename):
        self.filename = filename
        self._cmd = subprocess.Popen(["java", "-jar", "TWMapServer-1.0-all.jar", self.filename, str(port)], stdin=subprocess.PIPE)

    def close(self):
        # allow server to close gracefully
        self._cmd.stdin.write("exit\n")
        log.info("Waiting for vm to close")
        if self._cmd.wait():
            log.warning("VM exited with exit code {}", self._cmd.returncode)
        else:
            log.info("VM exited ok!")


class _Client(object):
    def __init__(self):
        self._socket = socket.socket()
        self._socket.connect(("localhost", port))
        self._socket.setblocking(1)

    def _recv(self, fmt, size):
        data = self._socket.recv(size)
        return struct.unpack(fmt, data)

    def _send(self, fmt, *args):
        data = struct.pack(fmt, *args)
        self._socket.sendall(data)

    def requestChunk(self, x, y, z):
        """
        Request chunk at chunk position (x, y, z)

        Returns the nbt structure of the chunk or raises an exception on IOError
        """
        self._send('!biii', 0x4, x, y, z)
        packet_id = self._recv('!b', 1)[0]
        if packet_id == 0x10:
            log.warning("server closing")
            raise IOError
        elif packet_id == 0x15:
            size = self._recv('!i', 4)[0]
            return nbt.load(buf=self._socket.recv(size))
        elif packet_id == 0x14:
            return None
        else:
            log.error("Invalid reply id %x", packet_id)
            raise IOError

    def close(self):
        self._socket.sendall('\x00')
        self._socket.close()
# class TWWorld(EntityLevel):
#     def __init__(self, filename):
#         self.filename = filename
#         self._vm = None
#         self._client = None
#
#     def _launchVM(self):
#         self._vm = _VM(self.filename)
#         self._client = _Client()
#
#
# class TWCube(ChunkBase):
#     pass
#
#
# class TWColumn(ChunkBase):
#     pass

