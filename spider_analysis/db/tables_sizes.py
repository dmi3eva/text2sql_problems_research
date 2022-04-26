from collections import Counter
from utils.spider_connectors import *
from dataclasses import dataclass


@dataclass
class NumericalItem:
    key: Union[int, str]
    value: int


class NumericalStatistics:
    def __init__(self, content: Counter):
        sorted_items = sorted(content.items())
        self.content = [NumericalItem(key=_k, value=_v) for _k, _v in sorted_items]

    def get_x(self):
        return [_item.key for _item in self.content]

    def get_y(self):
        return [_item.value for _item in self.content]


def get_tables_sizes_statistics(connector: SpiderDB) -> Tuple[NumericalStatistics, NumericalStatistics]:
    """
    Returns sizes of tables, amount of unique values in the tables
    """
    all_sizes = []
    unique_sizes = []
    for _triple in connector.triples:
        db, table, column = _triple
        values = connector.get_values(db, table, column)
        unique_values = set(values)
        all_sizes.append(len(values))
        unique_sizes.append(len(unique_values))
    all_counter = Counter(all_sizes)
    unique_counter = Counter(unique_sizes)
    return NumericalStatistics(all_counter), NumericalStatistics(unique_counter)


def get_entities_sizes_statistics(connector: SpiderDB) -> Tuple[NumericalStatistics, NumericalStatistics]:
    """
    Returns sizes of values in symbols and in tokens
    """
    all_sizes = []
    unique_sizes = []
    all_values = set()
    total = len(connector.triples)
    for ind, _triple in enumerate(connector.triples):
        if ind % 500 == 0:
            print(f"{ind} / {total}")
        db, table, column = _triple
        values = connector.get_values(db, table, column)
        unique_values = set(values)
        all_values = all_values.union(unique_values)
    all_values_list = list(all_values)
    print(f"Amount of unique values is {len(all_values_list)}")

    symbol_sizes = [len(entity) for entity in all_values_list]
    print(f"Longest value is {all_values_list[symbol_sizes.index(max(symbol_sizes))]}")

    token_sizes = [len(entity.split(' ')) for entity in all_values_list]
    print(f"Longest value is {all_values_list[token_sizes.index(max(token_sizes))]}")

    print(f"Average symbols size if {sum(symbol_sizes) / len(all_values_list)}")
    print(f"Average tokens size if {sum(token_sizes) / len(all_values_list)}")
    symbols_counter = Counter(symbol_sizes)
    tokens_counter = Counter(token_sizes)
    return NumericalStatistics(symbols_counter), NumericalStatistics(tokens_counter)