"""Lossless columnar JSON for repeated evidence rows; no filtering or summarization."""
import json

MODEL='gpt-6.1-sol'
COLUMN_RULE='Таблицы с encoding=columnar-v1: columns задаёт имена полей, каждая строка rows содержит значения в том же порядке. Все строки и null сохранены; null не ноль.'

def pack(value):
    if isinstance(value,dict):
        return {k:pack(v) for k,v in value.items()}
    if isinstance(value,list):
        rows=[pack(v) for v in value]
        if len(value)>=3 and all(isinstance(v,dict) for v in value):
            columns=list(value[0])
            if columns and all(set(v)==set(columns) for v in value):
                table={'encoding':'columnar-v1','columns':columns,
                       'rows':[[row[k] for k in columns] for row in rows]}
                if len(dumps(table))<len(dumps(rows)):return table
        return rows
    return value

def dumps(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),default=str)

def message(value):
    return dumps(pack(value))
