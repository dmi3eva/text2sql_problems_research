import json
import telebot

from random import choice
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import *
from verification.settings.config import *

SAMPLES_PATH = '../resources/datasets/araneae/araneae.json'


class Status(Enum):
    READY = 0
    IN_PROGRESS = 1
    ERROR_DESCRIBING = 2
    DB_EXPLORING = 3
    INFO_READING = 4
    IN_PROGRESS_FLUENCY = 5
    IN_PROGRESS_EQUIVALENT = 6
    IN_PROGRESS_SQL = 7
    ERROR_DESCRIBING_FLUENCY = 8
    ERROR_DESCRIBING_EQUIVALENT = 9
    ERROR_DESCRIBING_SQL = 10


class State(Enum):
    SAMPLE = 0
    TABLES = 1
    VIEW = 2
    INFO = 3
    ERROR = 4


@dataclass
class BotSample:
    db: Optional[str] = None
    nl: Optional[str] = None
    sql: Optional[str] = None
    source_nl: Optional[str] = None
    source_sql: Optional[str] = None
    result: Optional[str] = None


class User:
    def __init__(self, user_id):
        self.id: str = user_id
        self.last_sample: Optional[BotSample] = None
        self.last_message: Any = None
        self.state: State = State.SAMPLE
        self.status: Status = Status.READY


class Controller:
    def __init__(self):
        self.users: Dict[str, User] = {}
        self.samples = []
        self.load_samples()

    def load_samples(self):
        with open(SAMPLES_PATH, 'r') as samples_file:
            self.samples = json.load(samples_file)

    def add_new_user(self, user_id):
        self.users[user_id] = User(user_id)

    def generate_sample_for_user(self, user_id) -> BotSample:  # TODO
        # generated_sample = Sample()
        json_sample = choice(self.samples)
        generated_sample = BotSample(
            db=json_sample['db_id'],
            nl=json_sample['question'],
            sql=json_sample['query']

        )
        self.users[user_id].last_sample = deepcopy(generated_sample)
        return generated_sample

