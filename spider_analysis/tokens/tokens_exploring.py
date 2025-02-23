"""
Structure:
info = {
    token_1: {
        "db": {
            db_id_1: [DBDescription(type, db, table, column, value), ...]
        },
        "query": {
            db_id_1: [QueryDescription(type, db, id, nl), ...]
        },
        "question": {
            db_id_1: [QuestionDescription(db, id, nl), ...]
        }
    }
}
"""



from araneae.wrapper import Araneae
from utils.spider_connectors import *
from utils.preprocessing.text import *
from utils.nlp import is_russian
from dto.sample import *
from dataclasses import dataclass
from typing import *
from enum import Enum
import json


from configure import *


class Entity(Enum):
    DB = 0
    TABLE = 1
    COLUMN = 2
    VALUE = 3
    AGG = 4


@dataclass
class DBDescription:
    type: Entity
    db: str
    table: Optional[str] = None
    column: Optional[str] = None
    value: Optional[str] = None


@dataclass
class QuestionDescription:
    db: str
    id: int
    nl: Optional[str] = None


@dataclass
class QueryDescription:
    db: str
    id: int
    nl: Optional[str] = None
    type: Optional[Subquery] = None


@dataclass
class Token:
    db: Optional[Dict[str, List[DBDescription]]] = None
    question: Optional[Dict[str, List[QuestionDescription]]] = None
    query: Optional[Dict[str, List[QueryDescription]]] = None


def extract_tokens_info(dataset: Araneae, language: Language):
    info = dict()
    info = extract_question_info(info, dataset, language)
    info = extract_query_info(info, dataset, language)
    info = extract_db_info(info, language)
    return info


def extract_db_info(info: Dict[str, Token], language: Language) -> Dict[str, Token]:
    spider = None
    if language is Language.RU:
        spider = RuSpiderDB()
    else:
        spider = EnSpiderDB()
    columns = spider.extract_columns()
    info = get_tables_tokens(info, columns, language)
    info = get_columns_tokens(info, columns, language)
    info = get_values_tokens(info, columns, spider, language)
    print("Values done")
    return info


def extract_question_info(info: Dict[str, Token], dataset: Araneae, language: Language) -> Dict[str, Token]:
    for sample in dataset.samples.content:
        tokens = []
        nl = ""
        if language is Language.EN:
            tokens = sample.question_toks
            nl = sample.question
        if language is Language.RU:
            tokens = sample.russian_question_toks
            nl = sample.russian_question
        for _token in tokens:
            processing_language = Language.EN
            if is_russian(_token):
                processing_language = Language.RU
            processed_token = db_token_process(_token, processing_language)
            info = get_question_token(info, processed_token, sample.db_id, nl, sample.id)
    return info


def extract_query_info(info: Dict[str, Token], dataset: Araneae, language: Language) -> Dict[str, Token]:
    for sample in dataset.samples.content:
        mentions = sample.mentions
        if language is Language.EN:
            nl = sample.query
        if language is Language.RU:
            nl = sample.russian_query
        for _mention in mentions:
            info = get_query_token(info, _mention, sample.db_id, nl, sample.id)
    return info


def get_columns_tokens(info: Dict[str, Token], columns, language: Language) -> Dict[str, Token]:
    for db, db_content in columns.items():
        for table, table_content in db_content.items():
            for column in table_content:
                tokens = column.split("_")
                for token in tokens:
                    description = DBDescription(
                        db=db,
                        table=table,
                        column=column,
                        type=Entity.COLUMN.name  # TODO
                    )
                    info = add_db_to_info(info, db_token_process(token, language), description)
    return info


def get_tables_tokens(info: Dict[str, Token], columns: Dict, language: Language) -> Dict[str, Token]:
    for db, db_content in columns.items():
        for table in db_content.keys():
            tokens = table.split("_")
            for token in tokens:
                description = DBDescription(
                    db=db,
                    table=table,
                    type=Entity.TABLE.name  # TODO
                )
                info = add_db_to_info(info, db_token_process(token, language), description)
    return info


def get_db_tokens(info: Dict[str, Token], columns: Dict) -> Dict[str, Token]:
    for db in columns.keys():
        tokens = db.split("_")
        for token in tokens:
            description = DBDescription(
                db=db,
                type=Entity.DB.name  # TODO
            )
            info = add_db_to_info(info, token, description)
    return info


def get_values_tokens(info: Dict[str, Token], columns: Dict, spider: SpiderDB, language: Language) -> Dict[str, Token]:
    db_amount = len(columns)
    ind = 0
    for db, db_content in columns.items():
        ind += 1
        print(f"{ind} / {db_amount}")
        for table, table_content in db_content.items():
            for column in table_content:
                values = set(spider.get_values(db, table, column))
                if len(values) > MAX_VALUES_IN_COLUMNS:
                    break
                for value in values:
                    tokens = value.split(" ")
                    for token in tokens:
                        description = DBDescription(
                            db=db,
                            table=table,
                            column=column,
                            value=value,
                            type=Entity.VALUE.name  # TODO
                        )
                        info = add_db_to_info(info, db_token_process(token, language), description)
    return info


def add_db_to_info(info: Dict[str, Token], name: str, description: DBDescription) -> Dict[str, Token]:
    column_token = info.get(name, Token())
    if not column_token.db:
        column_token.db = {}
    column_db_list = column_token.db.get(description.db, [])
    column_db_list.append(description)
    column_token.db[description.db] = column_db_list
    info[name] = column_token
    return info


def get_question_token(info: Dict[str, Token], token: str, db: str, nl: str, id: int) -> Dict[str, Token]:
    if len(token) < MIN_TOKEN_LENGTH:
        return info
    info[token] = info.get(token, Token())
    if not info[token].question:
        info[token].question = {}
    db_info = info[token].question.get(db, [])
    db_info.append(
        QuestionDescription(db=db, nl=nl, id=id)
    )
    info[token].question[db] = db_info
    return info


def get_query_token(info: Dict[str, Token], mention: Mention, db: str, nl: str, id: int) -> Dict[str, Token]:
    tokens = extract_token_from_mentions(mention)
    for _token in tokens:
        processed_token = values_processing(_token)
        info[processed_token] = info.get(processed_token, Token())
        if not info[processed_token].query:
            info[processed_token].query = {}
        db_info = info[processed_token].query.get(db, [])
        db_info.append(
            QueryDescription(db=db, nl=nl, id=id, type=mention.type.name)  # TODO: just type
        )
        info[processed_token].query[db] = db_info
    return info


def extract_token_from_mentions(mention: Mention) -> List[str]:
    if mention.values:
        return mention.values  # Short tokens also remains
    token = ""
    if mention.column:
        token = mention.column
    elif mention.table:
        token = mention.table
    if len(token) > MIN_TOKEN_LENGTH:
        tokens = [token]
    else:
        tokens = []
    return tokens


def info_to_dict(statistics: Dict) -> Dict:
    print("To dict started")
    info = {}
    for token_name, token in statistics.items():
        info[token_name] = {
            "db": {},
            "question": {},
            "query": {}
        }
        if token.question:
            info[token_name]["question"] = {
                _db: [_q.__dict__ for _q in _questions]
                for _db, _questions in token.question.items()
            }
        if token.query:
            info[token_name]["query"] = {
                _db: [_q.__dict__ for _q in _queries]
                for _db, _queries in token.query.items()
            }
        if token.db:
              info[token_name]["db"] = {
                _db: [_d.__dict__ for _d in _dbs]
                for _db, _dbs in token.db.items()
            }

    # # Sampling for test
    # from random import shuffle
    # part = list(info.values())[:1000]
    # shuffle(part)
    # sample_path = path.join(ROOT_PATH, "resources", "results", "tokens", "sample.json")
    # with open(sample_path, 'w', encoding='utf-8') as f:
    #     json.dump(part[:10], f, ensure_ascii=False)

    return info


def save_tokens_info(statistics, filename) -> NoReturn:
    tokens_info = info_to_dict(statistics)
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(tokens_info, f, ensure_ascii=False)


def make_using_analysis(info: Dict, language: Language) -> NoReturn:
    all_analyze(info, language)
    table_analyze(info, language)
    column_analyze(info, language)
    value_analyze(info, language)


def all_analyze(info: Dict[str, Token], language: Language) -> NoReturn:
    filepath = os.path.join(TOKENS_EN_PATH, RU_MULTIUSING_ENTITIES)
    if language is Language.EN:
        filepath = os.path.join(TOKENS_EN_PATH, EN_MULTIUSING_ENTITIES)
    with open(filepath, "r", encoding="utf-8") as tokens_file:
        all_multiusing = json.load(tokens_file)
    used = []
    for _token, _description in info.items():
        if not _description.db:
            continue
        if not _description.question:
            continue
        for _db in _description.db.keys():
            if _db not in _description.question.keys():
                continue
            if _token in all_multiusing[_db].keys():
                used.append((_token, _db, _description))
    print(f"В {language.name} {len(used)} all entities")


def table_analyze(info: Dict[str, Token], language: Language) -> NoReturn:
    filepath = os.path.join(TOKENS_EN_PATH, RU_MULTIUSING_TABLES)
    if language is Language.EN:
        filepath = os.path.join(TOKENS_EN_PATH, EN_MULTIUSING_TABLES)
    with open(filepath, "r", encoding="utf-8") as tokens_file:
        all_multiusing = json.load(tokens_file)
    used = []
    _description: Token
    for _token, _description in info.items():
        if not _description.db:
            continue
        if not _description.query:
            continue
        for _db in _description.db.keys():
            if _db not in _description.query.keys():
                continue
            types = [_q.type for _q in _description.query[_db]]
            if 'FROM' not in types:
                continue
            if _token in all_multiusing[_db].keys():
                used.append((_token, _db, _description))
    print(f"В {language.name} {len(used)} tables")


def column_analyze(info: Dict[str, Token], language: Language) -> NoReturn:
    filepath = os.path.join(TOKENS_EN_PATH, RU_MULTIUSING_COLUMNS)
    if language is Language.EN:
        filepath = os.path.join(TOKENS_EN_PATH, EN_MULTIUSING_COLUMNS)
    with open(filepath, "r", encoding="utf-8") as tokens_file:
        all_multiusing = json.load(tokens_file)
    used = []
    _description: Token
    for _token, _description in info.items():
        if not _description.db:
            continue
        if not _description.query:
            continue
        for _db in _description.db.keys():
            if _db not in _description.query.keys():
                continue
            types = [_q.type for _q in _description.query[_db]]
            if 'SELECT' not in types and 'GROUP_BY' not in types and 'ORDER_BY' not in types:
                continue
            if _token in all_multiusing[_db].keys():
                used.append((_token, _db, _description))
                print('-----')
                print(_token)
                print('SQL:')
                print([(_q.id, _q.nl) for _q in _description.query[_db]])
                print('Mentions:')
                print([_q for _q in _description.db[_db]])
                print()
    print(f"В {language.name} {len(used)} columns")


def value_analyze(info: Dict[str, Token], language: Language) -> NoReturn:
    filepath = os.path.join(TOKENS_EN_PATH, RU_MULTIUSING_VALUES)
    if language is Language.EN:
        filepath = os.path.join(TOKENS_EN_PATH, EN_MULTIUSING_VALUES)
    with open(filepath, "r", encoding="utf-8") as tokens_file:
        all_multiusing = json.load(tokens_file)
    used = []
    _description: Token
    for _token, _description in info.items():
        if not _description.db:
            continue
        if not _description.query:
            continue
        for _db in _description.db.keys():
            if _db not in _description.query.keys():
                continue
            types = [_q.type for _q in _description.query[_db]]
            if 'WHERE' not in types:
                continue
            if _token in all_multiusing[_db].keys():
                used.append((_token, _db, _description))
    print(f"В {language.name} {len(used)} values")


if __name__ == "__main__":
    araneae = Araneae()
    araneae.load()

    print("English starts")
    en_tokens = extract_tokens_info(araneae, Language.EN)
    make_using_analysis(en_tokens, Language.EN)  # Not for first execution
    save_tokens_info(en_tokens, TOKENS_EN_PATH)
    print("English ends")

    print("Russian starts")
    ru_tokens = extract_tokens_info(araneae, Language.RU)
    save_tokens_info(ru_tokens, TOKENS_RU_PATH)
    make_using_analysis(ru_tokens, Language.RU)  # Not for first execution
    print("Russian ends")
