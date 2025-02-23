import os
import re
import json
import dill as pickle
import pandas as pd
from configure import *
from copy import deepcopy
from typing import *
from nltk import word_tokenize
from utils.preprocessing.spider.process_sql import tokenize

from utils.common import *
from utils.preprocessing.text import *
from utils.mention_extractor import MentionExtractor
from araneae.settings import *

from utils.preprocessing.spider.preprocess.parse_sql_one import get_schemas_from_json, Schema
from utils.preprocessing.spider.process_sql_russian import get_sql
from dto.sample import *

# nltk.download('punkt')


class Araneae:
    def __init__(self):
        self.samples: SamplesCollection = SamplesCollection()
        self.column_types = {}
        self.load_column_types()
        self.db_tokens = {
            "all": {"ru": None, "en": None}
        }
        self.db_tokens_multiusing = {
            "all": {"ru": None, "en": None},
            "tables": {"ru": None, "en": None},
            "columns": {"ru": None, "en": None},
            "values": {"ru": None, "en": None}
        }
        self.load_db_tokens()
        self.mention_extractor = MentionExtractor()
        self.russian__mention_extractor = None
        self.start_indices = None
        self.EXTRACTION_FUNCTIONS = {
            QueryType.TWO: lambda sample: self._specifications_binary(sample),
            QueryType.DATETIME: lambda sample: self._specifications_from_mentions(QueryType.DATETIME, sample),
            QueryType.SIMPLICITY: lambda sample: self._specifications_simplicity(sample),
            QueryType.JOIN: lambda sample: self._specifications_join(sample),
            QueryType.SELECT: lambda sample: self._specifications_select(sample),
            QueryType.LOGIC: lambda sample: self._specifications_logic(sample),
            QueryType.NL: lambda sample: self._specifications_nl(sample),
            QueryType.NEGATION: lambda sample: self._specifications_negation(sample),
            QueryType.DB: lambda sample: self._specifications_db(sample),
            QueryType.SQL: lambda sample: self._specifications_sql(sample),
            QueryType.WHERE: lambda sample: self._specifications_where(sample),
            QueryType.GROUP_BY: lambda sample: self._specifications_group_by(sample),
            QueryType.ORDER_BY: lambda sample: self._specifications_order_by(sample),
            QueryType.NEW: lambda sample: self._specifications_new(sample)
        }
        schemas, db_names, tables = get_schemas_from_json(SCHEMES_PATH)
        self.schemas = schemas
        self.tables = tables

    def load_column_types(self):
        for _column_type in QueryType:
            path = os.path.join(QUERY_TYPES_PATH, f"{_column_type.value}.json")
            if not os.path.exists(path):
                continue
            self.column_types[_column_type] = {}
            with open(path) as column_file:
                self.column_types[_column_type] = json.load(column_file)

    def load_db_tokens(self):
        with open(EN_ENTITIES, "r", encoding='utf-8') as in_file:
            self.db_tokens["all"]["en"] = json.load(in_file)
        with open(EN_MULTIUSING_ENTITIES, "r", encoding='utf-8') as in_file:
            self.db_tokens_multiusing["all"]["en"] = json.load(in_file)
        with open(EN_MULTIUSING_TABLES, "r", encoding='utf-8') as in_file:
            self.db_tokens_multiusing["tables"]["en"] = json.load(in_file)
        with open(EN_MULTIUSING_COLUMNS, "r", encoding='utf-8') as in_file:
            self.db_tokens_multiusing["columns"]["en"] = json.load(in_file)
        with open(EN_MULTIUSING_VALUES, "r", encoding='utf-8') as in_file:
            self.db_tokens_multiusing["values"]["en"] = json.load(in_file)
        with open(RU_ENTITIES, "r", encoding='utf-8') as in_file:
            self.db_tokens["all"]["ru"] = json.load(in_file)
        with open(RU_MULTIUSING_ENTITIES, "r", encoding='utf-8') as in_file:
            self.db_tokens_multiusing["all"]["ru"] = json.load(in_file)
        with open(RU_MULTIUSING_TABLES, "r", encoding='utf-8') as in_file:
            self.db_tokens_multiusing["tables"]["ru"] = json.load(in_file)
        with open(RU_MULTIUSING_COLUMNS, "r", encoding='utf-8') as in_file:
            self.db_tokens_multiusing["columns"]["ru"] = json.load(in_file)
        with open(RU_MULTIUSING_VALUES, "r", encoding='utf-8') as in_file:
            self.db_tokens_multiusing["values"]["ru"] = json.load(in_file)

    def load_from_json(self, filepath: str, source: Source) -> int:
        with open(filepath) as json_file:
            json_samples = json.load(json_file)
        for _json_sample in json_samples:
            sample = self.create_sample_from_json(_json_sample, source)
            self.samples.content.append(sample)
        return len(json_samples)

    def load_russian_in_english_from_csv(self, filepath: str, id_start: int) -> int:
        data_df = pd.read_csv(filepath, sep=',', encoding='utf-8')
        current_ind = id_start
        samples_json = []
        for ind, row in data_df.iterrows():
            current_sample = self.samples.content[current_ind]
            self._verify_translation(current_sample, row)
            current_sample.russian_query = row['sql_ru']
            corrected = row["sql_ru_corrected"]
            if not pd.isna(corrected) and corrected and len(corrected) > 0:
                current_sample.russian_query = row['sql_ru_corrected']
            current_sample.russian_question = row['ru']
            corrected = row["ru_corrected"]
            if not pd.isna(corrected) and corrected and len(corrected) > 0:
                current_sample.russian_question = row['ru_corrected']
            current_sample.russian_query_toks = tokenize(current_sample.russian_query)
            current_sample.russian_question_toks = word_tokenize(current_sample.russian_question, language="russian")
            current_sample.id = row["id"]
            if current_sample.russian_question.lower().startswith("select"):
                raise KeyError("SQL in NL")
            schema = self.schemas[current_sample.db_id]
            table = self.tables[current_sample.db_id]
            schema_obj = Schema(schema, table)
            current_sample.russian_sql = get_sql(schema_obj, current_sample.russian_query)
            current_sample.russian_mentions = self.mention_extractor.get_mentions_from_sample({
                "db_id": current_sample.db_id,
                "sql": current_sample.russian_sql
            })
            current_sample.russian_query_toks_no_values = []
            values_mentions = []
            for _mention in current_sample.russian_mentions:
                if _mention.type is Subquery.WHERE and _mention.values is not None:
                    values_mentions += _mention.values
            values_mentions = [_v if isinstance(_v, str) else _v for _v in values_mentions]
            for _tok in current_sample.russian_query_toks:
                if _tok not in values_mentions:
                    current_sample.russian_query_toks_no_values.append(_tok)
                else:
                    current_sample.russian_query_toks_no_values.append(VALUE)
            current_ind += 1
        return len(data_df)

    def load_russian_from_csv(self, filepath: str, source: Source) -> NoReturn:
        data_df = pd.read_csv(filepath, sep=',', encoding='utf-8')

        # Preparing for typing
        with open(DB_DIVISION, "r") as db_file:
            db_division = json.load(db_file)

        source_mapping = {
            "train-spider": TrainDevType.TRAIN,
            "train-others": TrainDevType.TRAIN,
            "dev": TrainDevType.DEV
        }
        db_mapping = {}
        for source_name, dbs in db_division.items():
            for db_name in dbs:
                db_mapping[db_name] = source_mapping[source_name]

        # Iteration
        for ind, row in data_df.iterrows():
            generated_sample = Sample()
            generated_sample.id = row['id']
            generated_sample.db_id = row['db_id']
            generated_sample.source = source
            generated_sample.type = db_mapping[generated_sample.db_id]
            generated_sample.question = row['en']
            generated_sample.russian_question = row['ru']
            question_corrected = row["ru_corrected"]
            if not pd.isna(question_corrected) and question_corrected and len(question_corrected) > 0:
                 generated_sample.russian_question = question_corrected
            generated_sample.query = row['sql_en']
            generated_sample.russian_query = row['sql_ru']
            query_corrected = row["sql_ru_corrected"]
            if not pd.isna(query_corrected) and query_corrected and len(query_corrected) > 0:
                 generated_sample.russian_query = query_corrected

            ##################
            # Processed part #
            ##################

            # SQL
            schema = self.schemas[generated_sample.db_id]
            table = self.tables[generated_sample.db_id]
            schema_obj = Schema(schema, table)
            try:
                generated_sample.sql = get_sql(schema_obj, generated_sample.query)
                generated_sample.russian_sql = get_sql(schema_obj, generated_sample.russian_query)
            except:
                raise ValueError()

            # generated_sample.sql = get_sql(schema_obj, generated_sample.query)
            # generated_sample.russian_sql = get_sql(schema_obj, generated_sample.russian_query)

            # Mentions

            generated_sample.mentions = self.mention_extractor.get_mentions_from_sample({
                "db_id": generated_sample.db_id,
                "sql": generated_sample.sql
            })
            generated_sample.russian_mentions = self.mention_extractor.get_mentions_from_sample({
                "db_id": generated_sample.db_id,
                "sql": generated_sample.russian_sql
            })

            # Tokens
            generated_sample.query_toks = tokenize(generated_sample.query)
            generated_sample.question_toks = word_tokenize(generated_sample.question, language="english")
            generated_sample.russian_query_toks = tokenize(generated_sample.russian_query)
            generated_sample.russian_question_toks = word_tokenize(generated_sample.russian_question, language="russian")

            # Tokens with no values
            generated_sample.query_toks_no_values = self.extract_toks_with_no_values(generated_sample.mentions, generated_sample.query_toks)
            generated_sample.russian_query_toks_no_values = self.extract_toks_with_no_values(generated_sample.russian_mentions,
                                                                           generated_sample.russian_query_toks)
            # Checkings
            if generated_sample.russian_question.lower().startswith("select"):
                raise KeyError("SQL in NL")

            self.samples.content.append(generated_sample)


    def extract_toks_with_no_values(self, mentions: List[Mention], query_toks: List[str]) -> List[str]:
        toks_no_values = []
        values_mentions = []
        for _mention in mentions:
            if _mention.type is Subquery.WHERE and _mention.values is not None:
                values_mentions += _mention.values
        values_mentions = [_v if isinstance(_v, str) else _v for _v in values_mentions]
        for _token in query_toks:
            if _token not in values_mentions:
                toks_no_values.append(_token)
            else:
                toks_no_values.append(VALUE)
        return toks_no_values

    def load_russian_from_json(self, filepath: str, id_start: int) -> int:
        with open(filepath) as json_file:
            json_samples = json.load(json_file)
        current_ind = id_start
        for _json_sample in json_samples:
            cusrrent_sample = self.samples.content[current_ind]
            self._verify_translation(cusrrent_sample, _json_sample)
            cusrrent_sample.russian_query = _json_sample['query']
            cusrrent_sample.russian_question = _json_sample['question']
            cusrrent_sample.russian_query_toks = _json_sample['query_toks']
            cusrrent_sample.russian_question_toks = _json_sample['question_toks']
            cusrrent_sample.russian_query_toks_no_values = _json_sample['query_toks_no_value']
            current_ind += 1
        return len(json_samples)

    def add_specifications(self, extraction_functions: List[QueryType]) -> NoReturn:
        samples_amount = len(self.samples.content)
        for ind, _sample in enumerate(self.samples.content):
            if ind % 200 == 0:
                print(f"{ind} / {samples_amount}")
            _sample.specifications = self.extract_specifications(extraction_functions, _sample)

    def import_spider(self):
        dev_path = os.path.join(SPIDER_PATH, 'dev.json')
        train_spider_path = os.path.join(SPIDER_PATH, 'train_spider.json')
        train_others_path = os.path.join(SPIDER_PATH, 'train_others.json')
        dev_size = self.load_from_json(dev_path, Source.SPIDER_DEV),
        train_size = self.load_from_json(train_spider_path, Source.SPIDER_TRAIN),
        other_size = self.load_from_json(train_others_path, Source.SPIDER_TRAIN_OTHERS)
        self.start_indices = {
            Source.SPIDER_DEV: 0,
            Source.SPIDER_TRAIN: dev_size,
            Source.SPIDER_TRAIN_OTHERS: dev_size + train_size
        }

    def import_russocampus_in_english_from_json(self):
        ru_dev_path = os.path.join(RUSSOCAMPUS_PATH, 'rusp_dev.json')
        ru_train_path = os.path.join(RUSSOCAMPUS_PATH, 'rusp_train.json')
        ru_train_others_path = os.path.join(RUSSOCAMPUS_PATH, 'rusp_train_others.json')

        dev_size = self.load_russian_from_json(ru_dev_path, 0)
        train_size = self.load_russian_from_json(ru_train_path, dev_size)
        _ = self.load_russian_from_json(ru_train_others_path, dev_size + train_size)

    def import_russocampus_in_english_from_csv(self):
        ru_dev_path = os.path.join(RUSSOCAMPUS_NEW_PATH, 'dev.csv')
        ru_train_path = os.path.join(RUSSOCAMPUS_NEW_PATH, 'train.csv')

        dev_size = self.load_russian_in_english_from_csv(ru_dev_path, 0)
        _ = self.load_russian_in_english_from_csv(ru_train_path, dev_size)

    def import_russocampus(self):
        ru_dev_path = os.path.join(RUSSOCAMPUS_NEW_PATH, 'dev.csv')
        ru_train_path = os.path.join(RUSSOCAMPUS_NEW_PATH, 'train_spider.csv')
        ru_others_path = os.path.join(RUSSOCAMPUS_NEW_PATH, 'train_others.csv')
        additional_files = filter(lambda x: x.endswith('.csv'), os.listdir(ADDITIONAL_DIR_PATH))
        additional_path = [os.path.join(ADDITIONAL_DIR_PATH, _p) for _p in additional_files]

        self.load_russian_from_csv(ru_dev_path, Source.SPIDER_DEV)
        self.load_russian_from_csv(ru_train_path, Source.SPIDER_TRAIN)
        self.load_russian_from_csv(ru_others_path, Source.SPIDER_TRAIN_OTHERS)

        for _additional in additional_path:
            self.load_russian_from_csv(_additional, Source.ADDITION)

    def load(self):
        with open(SAMPLES_PATH, 'rb') as sample_file:
            self.samples.content = pickle.load(sample_file)
        with open(INDICES_PATH, 'rb') as indices_file:
            self.start_indices = pickle.load(indices_file)

    def save(self):
        with open(SAMPLES_PATH, 'wb') as sample_file:
            pickle.dump(self.samples.content, sample_file)
        with open(COLUMN_TYPES_PATH, 'wb') as column_type_file:
            pickle.dump(self.column_types, column_type_file)
        with open(INDICES_PATH, 'wb') as indices_file:
            pickle.dump(self.start_indices, indices_file)

    def save_in_json(self):
        all_in_json = [_s.to_json() for _s in self.samples.content]
        train_spider = [_s.to_json() for _s in self.samples.content if _s.source is Source.SPIDER_TRAIN]
        train_others = [_s.to_json() for _s in self.samples.content if _s.source is Source.SPIDER_TRAIN_OTHERS]
        dev = [_s.to_json() for _s in self.samples.content if _s.source is Source.SPIDER_DEV]  # To remove

        all_train = [_s.to_json() for _s in self.samples.content if _s.type is TrainDevType.TRAIN and not _s.id.startswith("E_")]
        all_dev = [_s.to_json() for _s in self.samples.content if _s.type is TrainDevType.DEV and not _s.id.startswith("E_")]

        just_new_all = [_s.to_json() for _s in self.samples.content if _s.source is Source.ADDITION]
        just_new_train = [_s.to_json() for _s in self.samples.content if _s.source is Source.ADDITION and _s.type is TrainDevType.TRAIN]
        just_new_dev = [_s.to_json() for _s in self.samples.content if _s.source is Source.ADDITION and _s.type is TrainDevType.DEV]

        empty_train = [_s.to_json() for _s in self.samples.content if _s.type is TrainDevType.TRAIN and _s.id.startswith("E_")]
        empty_dev = [_s.to_json() for _s in self.samples.content if _s.type is TrainDevType.DEV and _s.id.startswith("E_")]

        with open(JSON_ALL, "w", encoding='utf-8') as outp:
            json.dump(all_in_json, outp, ensure_ascii=False)
        with open(JSON_TRAIN_SPIDER, "w", encoding='utf-8') as outp:
            json.dump(train_spider, outp, ensure_ascii=False)
        with open(JSON_TRAIN_OTHERS, "w", encoding='utf-8') as outp:
            json.dump(train_others, outp, ensure_ascii=False)
        with open(JSON_DEV, "w", encoding='utf-8') as outp:
            json.dump(dev, outp, ensure_ascii=False)

        with open(JSON_ALL_TRAIN, "w", encoding='utf-8') as outp:
            json.dump(all_train, outp, ensure_ascii=False)
        with open(JSON_ALL_DEV, "w", encoding='utf-8') as outp:
            json.dump(all_dev, outp, ensure_ascii=False)
        with open(JSON_NEW_ALL, "w", encoding='utf-8') as outp:
            json.dump(just_new_all, outp, ensure_ascii=False)
        with open(JSON_NEW_TRAIN, "w", encoding='utf-8') as outp:
            json.dump(just_new_train, outp, ensure_ascii=False)
        with open(JSON_NEW_DEV, "w", encoding='utf-8') as outp:
            json.dump(just_new_dev, outp, ensure_ascii=False)

        with open(JSON_EMPTY_TRAIN, "w", encoding='utf-8') as outp:
            json.dump(empty_train, outp, ensure_ascii=False)
        with open(JSON_EMPTY_DEV, "w", encoding='utf-8') as outp:
            json.dump(empty_dev, outp, ensure_ascii=False)

    def find_triples(self, triples: List[Triple]) -> List[Sample]:
        desired = []
        for _sample in self.samples.content:
            for _mention in _sample.mentions:
                if _mention.type is not Subquery.WHERE:
                    continue
                mention_triple = Triple(_mention.db, _mention.table, _mention.column)
                if mention_triple in triples:
                    desired.append(_sample)
        return desired

    def create_sample_from_json(self, sample_json: Dict, source: Source) -> Sample:
        generated_sample = Sample()
        generated_sample.id = len(self.samples.content)
        generated_sample.db_id = sample_json.get('db_id', None)
        generated_sample.source = source
        generated_sample.question = sample_json.get('question', None)
        generated_sample.query = sample_json.get('query', None)
        generated_sample.sql = sample_json.get('question', None)
        generated_sample.query_toks = sample_json.get('query_toks', None)
        generated_sample.query_toks_no_values = sample_json.get('query_toks_no_value', None)
        generated_sample.question_toks = sample_json.get('question_toks', None)
        generated_sample.sql = sample_json.get('sql', None)
        generated_sample.mentions = self.mention_extractor.get_mentions_from_sample(sample_json)
        return generated_sample

    @profile
    def extract_specifications(self, query_types: List[QueryType], sample: Sample) -> Dict:
        specifications = {}
        for _query_type in query_types:
            specifications[_query_type] = self.EXTRACTION_FUNCTIONS[_query_type](sample)
        return specifications

    def find_all_with_type_and(self, type: QueryType, subtypes: Optional[List[QuerySubtype]] = None) -> SamplesCollection:
        """Concatinating condition by AND"""
        search_result = SamplesCollection()
        for _sample in self.samples.content:
            sample_subtypes = _sample.specifications.get(type, None)
            condition_1 = not subtypes and sample_subtypes
            condition_2 = subtypes and sample_subtypes and all([_s in sample_subtypes for _s in subtypes])
            if condition_1 or condition_2:
                search_result.add(_sample)
        return search_result

    def find_all_with_type_or(self, type: QueryType, subtypes: Optional[List[QuerySubtype]] = None) -> SamplesCollection:
        """Concatinating condition by AND"""
        search_result = SamplesCollection()
        for _sample in self.samples.content:
            sample_subtypes = _sample.specifications.get(type, None)
            condition_1 = not subtypes and sample_subtypes
            condition_2 = subtypes and sample_subtypes and any([_s in sample_subtypes for _s in subtypes])
            if condition_1 or condition_2:
                search_result.add(_sample)
        return search_result

    def _verify_translation(self, sample: Sample, translation_json: Dict):
        if sample.db_id != translation_json['db_id']:
            if 'question' in translation_json.keys():
                raise ValueError(
                    f"Translation problem: {sample.id} = {sample.question} ({translation_json['question']})")
            else:
                raise ValueError(
                    f"Translation problem: {sample.id} = {sample.question} ({translation_json['id']})")

    def _specifications_from_mentions(self, query_type: QueryType, sample: Sample) -> Optional[List[QuerySubtype]]:
        specifications = None
        values = self.column_types[query_type]
        for _mention in sample.mentions:
            if not _mention.db or not _mention.table or not _mention.column:
                continue
            column_type_value = values.get(_mention.db, {}).get(_mention.table, {}).get(_mention.column, None)
            if not column_type_value:
                continue
            subtype = query_subtype_mapping[column_type_value["type"]]
            if not specifications:
                specifications = []
            specifications += [subtype]
            if _mention.values:
                specifications += [QuerySubtype.WITH_VALUES]
            else:
                specifications += [QuerySubtype.WITHOUT_VALUES]
        if specifications:
            specifications = list(set(specifications))
        return specifications

    def _specifications_binary(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        subtypes = self._specifications_from_mentions(QueryType.TWO, sample)
        if not subtypes:
            return []
        if QuerySubtype.BINARY_0_1 in subtypes or QuerySubtype.BINARY_YES_NO in subtypes or QuerySubtype.BINARY_TRUE_FALSE in subtypes:
            subtypes.append(QuerySubtype.JUST_BINARY)
        if (sample.id.startswith("TS_") or sample.id.startswith("TO_") or sample.id.startswith("D_")) and QuerySubtype.JUST_BINARY in subtypes:
            subtypes.append(QuerySubtype.JUST_BINARY_OLD)
        return subtypes

    def _specifications_simplicity(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        if if_extra_simple(sample):
            return [QuerySubtype.EXTRA_SIMPLE]
        if if_simple(sample):
            return [QuerySubtype.SIMPLE]
        return None

    def _specifications_join(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        if if_single_join(sample):
            return [QuerySubtype.SINGLE_JOIN]
        if if_multi_join(sample):
            return [QuerySubtype.MULTI_JOIN]
        return None

    def _specifications_select(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        subtypes = []
        if if_multi_select(sample):
            subtypes.append(QuerySubtype.MULTI_SELECT)
        if if_hetero_agg(sample):
            subtypes.append(QuerySubtype.HETERO_AGG)
        if if_mono_agg(sample):
            subtypes.append(QuerySubtype.MONO_AGG)
        selects = re.findall("select", sample.query)
        if len(selects) > 1:
            subtypes.append(QuerySubtype.NESTED)
        if len(subtypes) == 0:
            return None
        return subtypes

    def _specifications_logic(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        and_keys = {"and", "и"}
        or_keys = {"or", "или"}
        and_or = {"and", "or", "или", "и", "intersect", "union"}
        subtypes = []
        sql_logic_keys = get_logic_keys_from_sql(sample.query_toks_no_values)
        nl_logic_keys = get_logic_keys_from_nl(sample.question_toks) + get_logic_keys_from_nl(sample.russian_question_toks)
        if len(sql_logic_keys) > 0:
            subtypes.append(QuerySubtype.LOGIC_SQL_ALL)
        if len(nl_logic_keys) > 0:
            subtypes.append(QuerySubtype.LOGIC_NL_ALL)
        sql_and_or = and_or.intersection(set(sql_logic_keys))
        nl_and_or = and_or.intersection(set(nl_logic_keys))
        nl_and = and_keys.intersection(set(nl_logic_keys))
        nl_or = or_keys.intersection(set(nl_logic_keys))
        if len(sql_and_or) > 0:
            subtypes.append(QuerySubtype.LOGIC_SQL_AND_OR)
        if len(nl_and_or) > 0:
            subtypes.append(QuerySubtype.LOGIC_NL_AND_OR_OR)
        if len(nl_and) > 0 and len(nl_or) > 0:
            subtypes.append(QuerySubtype.LOGIC_NL_AND_AND_OR)
        condition_1 = ('and' in sql_and_or or "intersect" in sql_and_or) and ('or' in nl_and_or)
        condition_2 = ('or' in sql_and_or or "union" in sql_and_or) and ('and' in nl_and_or)
        """
        Don't fit:
            1. Union = SELECT for several columns
            2. AND & OR are both in NL
            3. UNION = WHERE with AND
        """
        if (condition_1 or condition_2) and sample.id in [726, 1902, 2387, 2402]:   # TO-DO
            subtypes.append(QuerySubtype.LOGIC_VS)
        if contains_logic_set_phrase(sample):
            subtypes.append(QuerySubtype.LOGIC_SET_PHRASE)
        if len(subtypes) == 0:
            return None
        return subtypes

    def _specifications_negation(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        subtypes = []
        nl = sample_token_processing(sample.question)
        sql = sample_token_processing(sample.query)
        sql_tokens = set([sample_token_processing(_t) for _t in sample.query_toks])
        nl_tokens = set([sample_token_processing(_t) for _t in sample.question_toks])
        negation_nl_keywords = {"no", "not", "dont", "doesnt", "isnt", "arent", "didnt", "except", "never",
                                "without", "non", "nt", "nor", "ignore", "ignoring", "exclude", "excluding"}
        negation_sql_keywords = {"except", "!", "!=", "null"}
        not_equal_keywords = {"no", "not", "dont", "doesnt", "isnt", "arent", "didnt", "!", "!=", "null", "nor", "not"}
        except_keywords = {"except", "without", "exclude", "excluding", "ignore", "ignoring", "exclude", "excluding"}
        negations_in_nl = nl_tokens.intersection(negation_nl_keywords)
        negations_in_sql = sql_tokens.intersection(negation_sql_keywords)
        VALUES_IDS = {1993, 5660, 5664}  # ID of samples in which "No" is part of value
        if len(negations_in_nl) > 0 and sample.id not in VALUES_IDS:
            subtypes.append(QuerySubtype.NEGATION_NL)
        STRUCTURE_IDS = {
            5516, 5517, 9081, 9082, 9083, 9084, 9085, 9148,
            1230, 1558, 3520, 3521, 3522, 3523, 4027, 8830
        }  # Samples with complex structure, not negations
        NULL_IDS = {4460, 4467, 4468, 4480, 4487, 3494, 3526}
        TOKENIZATION_IDS = {609, 610}
        sql_condition_1 = len(negations_in_sql) > 0 or "!=" in sql
        sql_condition_2 = "not in" not in sql or len(negations_in_sql) > 1
        sql_condition_3 = sample.id not in STRUCTURE_IDS
        sql_condition_4 = sample.id not in NULL_IDS and sample.id not in TOKENIZATION_IDS
        if sql_condition_1 and sql_condition_2 and sql_condition_3 and sql_condition_4:
            subtypes.append(QuerySubtype.NEGATION_SQL)
        if len(subtypes) == 0:
            return None
        negations_in_sample = negations_in_nl.union(negations_in_sql)
        if "no more" in nl:
            subtypes.append(QuerySubtype.NEGATION_SET_PHRASE)
        if "never" in nl_tokens:
            subtypes.append(QuerySubtype.NEGATION_NEVER)
        if "not only" in nl_tokens:
            subtypes.append(QuerySubtype.NEGATION_NOT_ONLY)
        if sample.id in [984, 985]:
            subtypes.append(QuerySubtype.NEGATION_COMMON_KNOWLEDGE)
        if len(negations_in_sample.intersection(not_equal_keywords)) > 0:
            subtypes.append(QuerySubtype.NEGATION_NOT_EQUAL)
        if len(negations_in_sample.intersection(except_keywords)) > 0:
            subtypes.append(QuerySubtype.NEGATION_EXCEPT)
        if "neither" in nl_tokens:
            subtypes.append(QuerySubtype.NEGATION_NEITHER_NOR)
        if "ignore" in nl:
            subtypes.append(QuerySubtype.NEGATION_IGNORING)
        if "other than" in nl:
            subtypes.append(QuerySubtype.NEGATION_OTHER_THAN)
        if "outside" in nl:
            subtypes.append(QuerySubtype.NEGATION_OUTSIDE)
        if "any" in nl_tokens or "all" in nl_tokens or "each" in nl_tokens:
            subtypes.append(QuerySubtype.NEGATION_ANY_ALL)
        if "null" in nl_tokens or "null" in sql_tokens:
            subtypes.append(QuerySubtype.NEGATION_NULL)
        if len(subtypes) == 0:
            return None
        return subtypes

    def _specifications_nl(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        subtypes = []
        sentences_amount = get_sentences_amount(sample.question)
        sql_tokens = len(sample.query_toks)
        nl_tokens = len(sample.question_toks)
        if sentences_amount > 1:
            subtypes.append(QuerySubtype.NL_SEVERAL_SENTENCES)
        if sql_tokens / nl_tokens >= SQL_NL_THRESHOLD:
            subtypes.append(QuerySubtype.NL_SHORT_SQL_LONG)
        if nl_tokens / sql_tokens >= NL_SQL_THRESHOLD:
            subtypes.append(QuerySubtype.NL_LONG_SQL_SHORT)
        if nl_tokens >= LONG_NL:
            subtypes.append(QuerySubtype.NL_LONG)
        return subtypes

    def _specifications_db(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        subtypes = []

        if contains_db_mentioned(sample, self.db_tokens, Language.EN):
            subtypes.append(QuerySubtype.DB_EN_MENTIONED_BUT_NOT_USED)
        if contains_db_mentioned(sample, self.db_tokens, Language.RU):
            subtypes.append(QuerySubtype.DB_RU_MENTIONED_BUT_NOT_USED)

        if contains_db_hetero(sample, self.db_tokens_multiusing, Language.EN):
            subtypes.append(QuerySubtype.DB_EN_HETERO_AMBIGUITY)
        if contains_db_hetero(sample, self.db_tokens_multiusing, Language.RU):
            subtypes.append(QuerySubtype.DB_RU_HETERO_AMBIGUITY)

        if contains_db_homo_tables(sample, self.db_tokens_multiusing, Language.EN):
            subtypes.append(QuerySubtype.DB_EN_TABLES_AMBIGUITY)
        if contains_db_homo_columns(sample, self.db_tokens_multiusing, Language.EN):
            subtypes.append(QuerySubtype.DB_EN_COLUMNS_AMBIGUITY)
        if contains_db_homo_values(sample, self.db_tokens_multiusing, Language.EN):
            subtypes.append(QuerySubtype.DB_EN_VALUES_AMBIGUITY)

        if contains_db_homo_tables(sample, self.db_tokens_multiusing, Language.RU):
            subtypes.append(QuerySubtype.DB_RU_TABLES_AMBIGUITY)
        if contains_db_homo_columns(sample, self.db_tokens_multiusing, Language.RU):
            subtypes.append(QuerySubtype.DB_RU_COLUMNS_AMBIGUITY)
        if contains_db_homo_values(sample, self.db_tokens_multiusing, Language.RU):
            subtypes.append(QuerySubtype.DB_RU_VALUES_AMBIGUITY)

        return subtypes

    def _specifications_sql(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        subtypes = []
        sql = sample_token_processing(sample.query)
        if "like" in sql:
            subtypes.append(QuerySubtype.SQL_LIKE)
        if "limit" in sql:
            subtypes.append(QuerySubtype.SQL_LIMIT)
        if "cast" in sql:
            subtypes.append(QuerySubtype.SQL_CAST)
        if "exist" in sql:
            subtypes.append(QuerySubtype.SQL_EXISTS)
        if "null" in sql:
            subtypes.append(QuerySubtype.SQL_NULL)
        if "between" in sql:
            subtypes.append(QuerySubtype.SQL_BETWEEN)
        if "except" in sql:
            subtypes.append(QuerySubtype.SQL_EXCEPT)
        if "having" in sql:
            subtypes.append(QuerySubtype.SQL_HAVING)
        if "distinct" in sql:
            subtypes.append(QuerySubtype.SQL_DISCTINCT)
        if "<" in sql or ">" in sql or "=" in sql or "between" in sql:
            subtypes.append(QuerySubtype.SQL_COMPARE)
        return subtypes

    def _specifications_where(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        subtypes = []
        where_mentions = [_m for _m in sample.mentions if _m.type is Subquery.WHERE]
        if len(where_mentions) == 1:
            subtypes.append(QuerySubtype.WHERE_MONO)
        if len(where_mentions) >= 2:
            subtypes.append(QuerySubtype.WHERE_MULTI)
        return subtypes

    def _specifications_group_by(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        subtypes = []
        group_by_mentions = [_m for _m in sample.mentions if _m.type is Subquery.GROUP_BY]
        if len(group_by_mentions) > 0:
            subtypes.append(QuerySubtype.GROUP_BY_EXISTS)
        """
        The idea was to extract something like this:
            SELECT count(*) ,  country_code FROM players GROUP BY country_code
            SELECT count(*) ,  YEAR FROM matches GROUP BY YEAR
            SELECT Nationality ,  COUNT(*) FROM people GROUP BY Nationality 
        """
        if len(group_by_mentions) > 0 and 'count(' in sample.query.lower():
            subtypes.append(QuerySubtype.GROUP_BY_COUNT)
        return subtypes

    def _specifications_order_by(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        subtypes = []
        order_by_mentions = [_m for _m in sample.mentions if _m.type is Subquery.ORDER_BY]
        if len(order_by_mentions) > 0:
            subtypes.append(QuerySubtype.ORDER_BY_EXISTS)
        if len(order_by_mentions) > 0 and 'order by count(' in sample.query.lower():
            subtypes.append(QuerySubtype.ORDER_BY_COUNT)
        return subtypes

    def _specifications_new(self, sample: Sample) -> Optional[List[QuerySubtype]]:
        subtypes = []
        mentions = sample.mentions
        aggs = ['average', 'mean', 'max', 'min', 'total', 'count', 'sum']
        for _mention in mentions:
            if _mention.column:
                column_tokens = list(map(lambda x: x.lower(), str(_mention.column).split("_")))
                for agg_key in aggs:
                    if agg_key in column_tokens:
                        subtypes.append(QuerySubtype.AGG_IN_COLUMN)
                        # print(_mention.column)
            if _mention.values is None:
                continue
            for _value in _mention.values:
                if len(str(_value).split()) > 4:
                    subtypes.append(QuerySubtype.OLD_LONG)
                    break

        if sample.id.startswith("L_"):
            subtypes.append(QuerySubtype.NEW_LONG)
        if sample.id.startswith("E_"):
            subtypes.append(QuerySubtype.NEW_EMPTY)
        if sample.id.startswith("B_"):
            subtypes.append(QuerySubtype.NEW_BINARY)
        if sample.id.startswith("F_"):
            subtypes.append(QuerySubtype.NEW_FUZZY)
        if sample.id.startswith("T_"):
            subtypes.append(QuerySubtype.NEW_DATES)
        if len(subtypes) > 0:
            subtypes.append(QuerySubtype.NEW_ALL)
        return subtypes

