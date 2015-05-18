import nbt
import struct
import time
import random
import logging
import os
import traceback
from numpy import array

from uuid import UUID
from mclevelbase import PlayerNotFound
from level import MCLevel

log = logging.getLogger(__name__)

def TagProperty(tagName, tagType, default_or_func=None):
    def getter(self):
        if tagName not in self.root_tag["Data"]:
            if hasattr(default_or_func, "__call__"):
                default = default_or_func(self)
            else:
                default = default_or_func

            self.root_tag["Data"][tagName] = tagType(default)
        return self.root_tag["Data"][tagName].value

    def setter(self, val):
        self.root_tag["Data"][tagName] = tagType(value=val)

    return property(getter, setter)

class SessionLockLost(IOError):
    pass


class PCMetadata(MCLevel):
    """
    Common super type of world types that have PC like metadata.

    This is used by both MCInfdevOldLevel and TWLevel
    """
    playersFolder = None
    readonly = False
    playerTagCache = {}
    players = []
    filename = None

    # --- NBT Tag variables ---

    VERSION_ANVIL = 19133

    SizeOnDisk = TagProperty('SizeOnDisk', nbt.TAG_Long, 0)
    RandomSeed = TagProperty('RandomSeed', nbt.TAG_Long, 0)
    Time = TagProperty('Time', nbt.TAG_Long, 0)  # Age of the world in ticks. 20 ticks per second; 24000 ticks per day.
    LastPlayed = TagProperty('LastPlayed', nbt.TAG_Long, lambda self: long(time.time() * 1000))

    LevelName = TagProperty('LevelName', nbt.TAG_String, lambda self: self.displayName)
    GeneratorName = TagProperty('generatorName', nbt.TAG_String, 'default')

    MapFeatures = TagProperty('MapFeatures', nbt.TAG_Byte, 1)

    GameType = TagProperty('GameType', nbt.TAG_Int, 0)  # 0 for survival, 1 for creative

    version = TagProperty('version', nbt.TAG_Int, VERSION_ANVIL)

    def getFilePath(self, filename):
        pass

    def getFolderPath(self, dirname):
        pass

    def initPlayers(self):
        if os.path.exists(self.getFilePath("players")) and os.listdir(
                    self.getFolderPath("players")) != []:
            self.playersFolder = self.getFolderPath("players")
            self.oldPlayerFolderFormat = True
            if os.path.exists(self.getFolderPath("playerdata")):
                self.playersFolder = self.getFolderPath("playerdata")
                self.oldPlayerFolderFormat = False
            self.players = [x[:-4] for x in os.listdir(self.playersFolder) if x.endswith(".dat")]
            for player in self.players:
                try:
                    UUID(player, version=4)
                except ValueError:
                    print "{0} does not seem to be in a valid UUID format".format(player)
                    self.players.remove(player)
            if "Player" in self.root_tag["Data"]:
                self.players.append("Player")

    def acquireSessionLock(self):
        lockfile = self.getFilePath("session.lock")
        self.initTime = int(time.time() * 1000)
        with file(lockfile, "wb") as f:
            f.write(struct.pack(">q", self.initTime))
            f.flush()
            os.fsync(f.fileno())
        logging.getLogger().info("Re-acquired session lock")

    def checkSessionLock(self):
        if self.readonly:
            raise SessionLockLost("World is opened read only.")

        lockfile = self.getFilePath("session.lock")
        try:
            (lock, ) = struct.unpack(">q", file(lockfile, "rb").read())
        except struct.error:
            lock = -1
        if lock != self.initTime:
            # I should raise an error, but this seems to always fire the exception, so I will just try to aquire it instead
            raise SessionLockLost("Session lock lost. This world is being accessed from another location.")
            #self.acquireSessionLock()

    def _create(self, filename, random_seed, last_played):

        # create a new level
        root_tag = nbt.TAG_Compound()
        root_tag["Data"] = nbt.TAG_Compound()
        root_tag["Data"]["SpawnX"] = nbt.TAG_Int(0)
        root_tag["Data"]["SpawnY"] = nbt.TAG_Int(2)
        root_tag["Data"]["SpawnZ"] = nbt.TAG_Int(0)

        if last_played is None:
            last_played = long(time.time() * 1000)
        if random_seed is None:
            random_seed = long(random.random() * 0xffffffffffffffffL) - 0x8000000000000000L

        self.root_tag = root_tag
        root_tag["Data"]['version'] = nbt.TAG_Int(self.VERSION_ANVIL)

        self.LastPlayed = long(last_played)
        self.RandomSeed = long(random_seed)
        self.SizeOnDisk = 0
        self.Time = 1
        self.LevelName = os.path.basename(self.filename)

        # ## if singleplayer:

        self.createPlayer("Player")

    def loadLevelDat(self, create=False, random_seed=None, last_played=None):

        if create:
            self._create(self.filename, random_seed, last_played)
            self.saveInPlace()
        else:
            try:
                self.root_tag = nbt.load(self.filename)
            except Exception, e:
                filename_old = self.getFilePath("level.dat_old")
                log.info("Error loading level.dat, trying level.dat_old ({0})".format(e))
                try:
                    self.root_tag = nbt.load(filename_old)
                    log.info("level.dat restored from backup.")
                    self.saveInPlace()
                except Exception, e:
                    traceback.print_exc()
                    print repr(e)
                    log.info("Error loading level.dat_old. Initializing with defaults.")
                    self._create(self.filename, random_seed, last_played)

    def save_metadata(self):
        """
        Saves the metadata to file. The session lock should have already been checked.
        """
        for path, tag in self.playerTagCache.iteritems():
            tag.save(path)

        if self.playersFolder is not None:
            for file_ in os.listdir(self.playersFolder):
                if file_.endswith(".dat") and file_[:-4] not in self.players:
                    os.remove(os.path.join(self.playersFolder, file_))

        self.playerTagCache.clear()

        self.root_tag.save(self.filename)

    def init_scoreboard(self):
        if os.path.exists(self.getFolderPath("data")):
                if os.path.exists(self.getFolderPath("data")+"/scoreboard.dat"):
                    return nbt.load(self.getFolderPath("data")+"/scoreboard.dat")
                else:
                    root_tag = nbt.TAG_Compound()
                    root_tag["data"] = nbt.TAG_Compound()
                    root_tag["data"]["Objectives"] = nbt.TAG_List()
                    root_tag["data"]["PlayerScores"] = nbt.TAG_List()
                    root_tag["data"]["Teams"] = nbt.TAG_List()
                    root_tag["data"]["DisplaySlots"] = nbt.TAG_List()
                    self.save_scoreboard(root_tag)
                    return root_tag
        else:
            self.getFolderPath("data")
            root_tag = nbt.TAG_Compound()
            root_tag["data"] = nbt.TAG_Compound()
            root_tag["data"]["Objectives"] = nbt.TAG_List()
            root_tag["data"]["PlayerScores"] = nbt.TAG_List()
            root_tag["data"]["Teams"] = nbt.TAG_List()
            root_tag["data"]["DisplaySlots"] = nbt.TAG_List()
            self.save_scoreboard(root_tag)
            return root_tag

    def save_scoreboard(self, score):
        score.save(self.getFolderPath("data")+"/scoreboard.dat")

    def init_player_data(self):
        player_data = {}
        if self.oldPlayerFolderFormat:
            for p in self.players:
                if p != "Player":
                    player_data_file = os.path.join(self.getFolderPath("players"), p+".dat")
                    player_data[p] = nbt.load(player_data_file)
                else:
                    data = nbt.load(self.getFilePath("level.dat"))
                    player_data[p] = data["Data"]["Player"]
        else:
            for p in self.players:
                if p != "Player":
                    player_data_file = os.path.join(self.getFolderPath("playerdata"), p+".dat")
                    player_data[p] = nbt.load(player_data_file)
                else:
                    data = nbt.load(self.getFilePath("level.dat"))
                    player_data[p] = data["Data"]["Player"]

        #player_data = []
        #for p in [x for x in os.listdir(self.playersFolder) if x.endswith(".dat")]:
                #player_data.append(player.Player(self.playersFolder+"\\"+p))
        return player_data

    def save_player_data(self, player_data):
        if self.oldPlayerFolderFormat:
            for p in player_data.keys():
                if p != "Player":
                    player_data[p].save(os.path.join(self.getFolderPath("players"), p+".dat"))
        else:
            for p in player_data.keys():
                if p != "Player":
                    player_data[p].save(os.path.join(self.getFolderPath("playerdata"), p+".dat"))

    # --- Player and spawn manipulation ---

    def playerSpawnPosition(self, player=None):
        """
        xxx if player is None then it gets the default spawn position for the world
        if player hasn't used a bed then it gets the default spawn position
        """
        dataTag = self.root_tag["Data"]
        if player is None:
            playerSpawnTag = dataTag
        else:
            playerSpawnTag = self.getPlayerTag(player)

        return [playerSpawnTag.get(i, dataTag[i]).value for i in ("SpawnX", "SpawnY", "SpawnZ")]

    def setPlayerSpawnPosition(self, pos, player=None):
        """ xxx if player is None then it sets the default spawn position for the world """
        if player is None:
            playerSpawnTag = self.root_tag["Data"]
        else:
            playerSpawnTag = self.getPlayerTag(player)
        for name, val in zip(("SpawnX", "SpawnY", "SpawnZ"), pos):
            playerSpawnTag[name] = nbt.TAG_Int(val)

    def getPlayerPath(self, player, dim=0):
        assert player != "Player"
        if dim != 0:
            return os.path.join(os.path.dirname(self.filename), "DIM%s" % dim, "playerdata", "%s.dat" % player)
        else:
            return os.path.join(self.playersFolder, "%s.dat" % player)

    def getPlayerTag(self, player="Player"):
        if player == "Player":
            if player in self.root_tag["Data"]:
                # single-player world
                return self.root_tag["Data"]["Player"]
            raise PlayerNotFound(player)
        else:
            playerFilePath = self.getPlayerPath(player)
            playerTag = self.playerTagCache.get(playerFilePath)
            if playerTag is None:
                if os.path.exists(playerFilePath):
                    playerTag = nbt.load(playerFilePath)
                    self.playerTagCache[playerFilePath] = playerTag
                else:
                    raise PlayerNotFound(player)
            return playerTag

    def getPlayerDimension(self, player="Player"):
        playerTag = self.getPlayerTag(player)
        if "Dimension" not in playerTag:
            return 0
        return playerTag["Dimension"].value

    def setPlayerDimension(self, d, player="Player"):
        playerTag = self.getPlayerTag(player)
        if "Dimension" not in playerTag:
            playerTag["Dimension"] = nbt.TAG_Int(0)
        playerTag["Dimension"].value = d

    def setPlayerPosition(self, (x, y, z), player="Player"):
        posList = nbt.TAG_List([nbt.TAG_Double(p) for p in (x, y - 1.75, z)])
        playerTag = self.getPlayerTag(player)

        playerTag["Pos"] = posList

    def getPlayerPosition(self, player="Player"):
        playerTag = self.getPlayerTag(player)
        posList = playerTag["Pos"]

        x, y, z = map(lambda x: x.value, posList)
        return x, y + 1.75, z

    def setPlayerOrientation(self, yp, player="Player"):
        self.getPlayerTag(player)["Rotation"] = nbt.TAG_List([nbt.TAG_Float(p) for p in yp])

    def getPlayerOrientation(self, player="Player"):
        """ returns (yaw, pitch) """
        yp = map(lambda x: x.value, self.getPlayerTag(player)["Rotation"])
        y, p = yp
        if p == 0:
            p = 0.000000001
        if p == 180.0:
            p -= 0.000000001
        yp = y, p
        return array(yp)

    def setPlayerAbilities(self, gametype, player="Player"):
        playerTag = self.getPlayerTag(player)

        # Check for the Abilities tag.  It will be missing in worlds from before
        # Beta 1.9 Prerelease 5.
        if 'abilities' not in playerTag:
            playerTag['abilities'] = nbt.TAG_Compound()

        # Assumes creative (1) is the only mode with these abilities set,
        # which is true for now.  Future game modes may not hold this to be
        # true, however.
        if gametype == 1:
            playerTag['abilities']['instabuild'] = nbt.TAG_Byte(1)
            playerTag['abilities']['mayfly'] = nbt.TAG_Byte(1)
            playerTag['abilities']['invulnerable'] = nbt.TAG_Byte(1)
        else:
            playerTag['abilities']['flying'] = nbt.TAG_Byte(0)
            playerTag['abilities']['instabuild'] = nbt.TAG_Byte(0)
            playerTag['abilities']['mayfly'] = nbt.TAG_Byte(0)
            playerTag['abilities']['invulnerable'] = nbt.TAG_Byte(0)

    def setPlayerGameType(self, gametype, player="Player"):
        playerTag = self.getPlayerTag(player)
        # This annoyingly works differently between single- and multi-player.
        if player == "Player":
            self.GameType = gametype
            self.setPlayerAbilities(gametype, player)
        else:
            playerTag['playerGameType'] = nbt.TAG_Int(gametype)
            self.setPlayerAbilities(gametype, player)

    def getPlayerGameType(self, player="Player"):
        if player == "Player":
            return self.GameType
        else:
            playerTag = self.getPlayerTag(player)
            return playerTag["playerGameType"].value

    def createPlayer(self, playerName):
        if playerName == "Player":
            playerTag = self.root_tag["Data"].setdefault(playerName, nbt.TAG_Compound())
        else:
            playerTag = nbt.TAG_Compound()

        playerTag['Air'] = nbt.TAG_Short(300)
        playerTag['AttackTime'] = nbt.TAG_Short(0)
        playerTag['DeathTime'] = nbt.TAG_Short(0)
        playerTag['Fire'] = nbt.TAG_Short(-20)
        playerTag['Health'] = nbt.TAG_Short(20)
        playerTag['HurtTime'] = nbt.TAG_Short(0)
        playerTag['Score'] = nbt.TAG_Int(0)
        playerTag['FallDistance'] = nbt.TAG_Float(0)
        playerTag['OnGround'] = nbt.TAG_Byte(0)

        playerTag["Inventory"] = nbt.TAG_List()

        playerTag['Motion'] = nbt.TAG_List([nbt.TAG_Double(0) for i in range(3)])
        playerTag['Pos'] = nbt.TAG_List([nbt.TAG_Double([0.5, 2.8, 0.5][i]) for i in range(3)])
        playerTag['Rotation'] = nbt.TAG_List([nbt.TAG_Float(0), nbt.TAG_Float(0)])

        if playerName != "Player":
            self.playerTagCache[self.getPlayerPath(playerName)] = playerTag
