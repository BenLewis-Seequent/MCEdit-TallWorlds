import tall_worlds as tw
import time

import logging
import sys
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)
vm = tw._VM("../test_save/cubes.dim0.db")

time.sleep(5)
client = tw._Client()
print(client.requestChunk(-7, -4, -6))
client.close()
vm.close()