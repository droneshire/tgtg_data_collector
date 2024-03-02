import typing as T

from rich.console import Console
from rich.table import Table


def camel_to_snake(str_in: str) -> str:
    # https://stackoverflow.com/a/1176023/10940584
    return "".join(["_" + c.lower() if c.isupper() else c for c in str_in]).lstrip("_")


def snake_to_camel(str_in: str) -> str:
    # https://stackoverflow.com/a/19053800/10940584
    return "".join([t.title() for t in str_in.split("_")])


def dict_keys_camel_to_snake_deep(dict_in) -> T.Any:
    # recursively convert dict keys from camelCase to snake_case
    if isinstance(dict_in, dict):
        dict_in = {camel_to_snake(k): dict_keys_camel_to_snake_deep(v) for k, v in dict_in.items()}
    return dict_in


def dict_keys_snake_to_camel_deep(dict_in) -> T.Any:
    # recursively convert dict keys from snake_case to camelCase
    if isinstance(dict_in, dict):
        dict_in = {snake_to_camel(k): dict_keys_snake_to_camel_deep(v) for k, v in dict_in.items()}
    return dict_in


def get_pretty_seconds(seconds: int, use_days: bool = False) -> str:
    """Given an amount of seconds, return a formatted string with
    hours, minutes and seconds; taken from
    https://stackoverflow.com/a/775075/2972183"""
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if use_days:
        days, hours = divmod(hours, 24)
        string = f"{days:d}d:{hours:d}h:{minutes:02d}m:{seconds:02d}s"
    else:
        string = f"{hours:d}h:{minutes:02d}m:{seconds:02d}s"
    return string


def print_simple_rich_table(title: str, data: T.List[T.Dict[str, str]]) -> None:
    console = Console()

    # infer the column names from the first item in the list
    column1 = list(data[0].keys())[0]
    column2 = list(data[0].keys())[1]

    table = Table(title=title, show_header=True, header_style="bold magenta")

    max_stat_len = max(len(stat[column1]) for stat in data)
    max_val_len = max(len(stat[column2]) for stat in data)

    table.add_column(column1, style="dim", width=max_stat_len)
    table.add_column(column2, width=int(max_val_len * 1.1))

    for item in data:
        table.add_row(item[column1], item[column2])

    console.print(table)
