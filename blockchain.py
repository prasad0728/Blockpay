import hashlib
import json
from datetime import datetime


class Block:
    def __init__(self, index, data, previous_hash, timestamp=None, nonce=0):
        self.index = index
        self.timestamp = timestamp or datetime.now().isoformat()
        self.data = data
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = self.calculate_hash()

    def calculate_hash(self):
        block_data = (
            str(self.index)
            + self.timestamp
            + json.dumps(self.data, sort_keys=True)
            + self.previous_hash
            + str(self.nonce)
        )
        return hashlib.sha256(block_data.encode()).hexdigest()

    def mine_block(self, difficulty=3):
        target = "0" * difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.calculate_hash()


class Blockchain:
    def __init__(self, difficulty=3):
        self.difficulty = difficulty

    def create_block(self, index, data, previous_hash):
        block = Block(index, data, previous_hash)
        block.mine_block(self.difficulty)
        return block
