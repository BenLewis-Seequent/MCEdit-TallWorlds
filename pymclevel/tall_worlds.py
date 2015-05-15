"""
This file contains implementation of Tall World Level support
"""
import subprocess
import socket
import logging
import struct
import time
import nbt
import os
import materials
from pymclevel import LightedChunk, ChunkedLevelMixin, EntityLevel, ChunkBase
from pc_metadata import PCMetadata

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
        data = ''
        while len(data) < size:
            newData = self._socket.recv(size - len(data))
            if len(newData) == 0:
                raise IOError
            data += newData
        return struct.unpack(fmt, data)

    def _send(self, fmt, *args):
        data = struct.pack(fmt, *args)
        self._socket.sendall(data)

    def requestChunk(self, x, y, z):
        """
        Request chunk at chunk position (x, y, z)

        Returns the nbt structure of the chunk or raises an exception on IOError
        """
        self._send('!biii', 0x2, x, y, z)
        packet_id = self._recv('!b', 1)[0]
        if packet_id == 0x40:
            log.warning("server closing")
            raise IOError
        elif packet_id == 0x52:
            size = self._recv('!i', 4)[0]
            return nbt.load(buf=self._socket.recv(size))
        elif packet_id == 0x42:
            return None
        else:
            log.error("Invalid reply id %x", packet_id)
            raise IOError

    def requestColumn(self, x, z):
        self._send('!bii', 0x22, x, z)
        packet_id = self._recv('!b', 1)[0]
        if packet_id == 0x40:
            log.warning("server closing")
            raise IOError
        elif packet_id == 0x72:
            size = self._recv('!i', 4)[0]
            return nbt.load(buf=self._socket.recv(size))
        elif packet_id == 0x62:
            return None
        else:
            log.error("Invalid reply id %x", packet_id)
            raise IOError

    def requestListChunks(self):
        self._send('!b', 0x4)
        packet_id = self._recv('!b', 1)[0]
        if packet_id == 0x40:
            log.warning("server closing")
            raise IOError
        elif packet_id == 0x54:
            size = self._recv('!i', 4)[0]
            poss = list()
            for _ in range(size):
                poss.append(self._recv('!iii', 12))
            return poss
        else:
            log.error("Invalid reply id %x", packet_id)
            raise IOError

    def requestListColumns(self):
        self._send('!b', 0x24)
        packet_id = self._recv('!b', 1)[0]
        if packet_id == 0x40:
            log.warning("server closing")
            raise IOError
        elif packet_id == 0x74:
            size = self._recv('!i', 4)[0]
            poss = list()
            for _ in range(size):
                poss.append(self._recv('!ii', 8))
            return poss
        else:
            log.error("Invalid reply id %x", packet_id)
            raise IOError

    def close(self):
        self._socket.sendall('\x00')
        self._socket.close()


class TWLevel(EntityLevel, PCMetadata):

    dimNo = 0
    parentWorld = None
    isInfinite = True
    materials = materials.alphaMaterials

    def __init__(self, filename, readonly):
        if os.path.isdir(filename):
            if 'level.dat' in os.listdir(filename):
                filename = os.path.join(filename, 'level.dat')
            else:
                raise IOError("file is not a level as it doesn't have level.dat")
        self.filename = filename
        self.readonly = readonly

        self._vm = None
        self._client = None
        self._loadedColumns = {}

        self._allColumns = None
        self._allCubes = None

        self.Width = 0
        self.Length = 0
        self.Height = 0

        self.acquireSessionLock()

        self.loadLevelDat()

    def getFilePath(self, path):
        path = path.replace("/", os.path.sep)
        return os.path.join(os.path.dirname(self.filename), path)

    def getFolderPath(self, path):
        path = self.getFilePath(path)
        if not os.path.exists(path) and "players" not in path:
            os.makedirs(path)

        return path

    @classmethod
    def _isLevel(self, filename):
        if not os.path.isdir(filename):
            filename = os.path.dirname(filename)
        files = os.listdir(filename)
        return "cubes.dim0.db" in files

    def _launchVM(self):
        self._vm = _VM(os.path.dirname(self.filename))
        time.sleep(5)
        self._client = _Client()

    def close(self):
        self._client.close()
        self._vm.close()

    def displayName(self):
        return os.path.basename(os.path.dirname(self.filename))

    # column methods

    def getChunk(self, cx, cz):
        column = self._loadedColumns.get((cx, cz))
        if column is not None:
            return column
        if self._vm is None:
            self._launchVM()
        column = TWColumn(cx, cz, self, self._client.requestColumn(cx, cz))
        self._loadedColumns[(cx, cz)] = column
        return column

    @property
    def allChunks(self):
        if self._allColumns is None:
            if self._vm is None:
                self._launchVM()
            self._allColumns = self._client.requestListColumns()
        return self._allColumns.__iter__()

    # cube methods

    def getChunk_cc(self, cx, cy, cz):
        return self.getChunk(cx, cz).getCube(cy)

    def allChunks_cc(self):
        if self._allCubes is None:
            if self._vm is None:
                self._launchVM()
            self._allCubes = self._client.requestListCubes()
        return self._allCubes.__iter__()


class TWCube(ChunkBase):
    Height = 16

    def __init__(self, world, cx, cy, cz, tag):
        self.world = world
        self.cx = cx
        self.cy = cy
        self.cz = cz
        self.root_tag = tag


class TWColumn(ChunkBase):
    def __init__(self, cx, cz, world, tag):
        self.world = world
        self.root_tag = tag
        self.cx = cx
        self.cz = cz
        self._loadedChunks = {}

    def getCube(self, cy):
        chunk = self._loadedChunks.get(cy)
        if chunk is not None:
            return chunk
        chunk = TWCube(self, self.cx, cy, self.cz, self.world._client.requestChunk(self.cx, cy, self.cz))
        self._loadedChunks[cy] = chunk
        return chunk

