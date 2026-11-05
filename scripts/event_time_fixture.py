from datetime import datetime
def event_time(at):
 if not isinstance(at,str) or not at.strip():raise ValueError('Receipt timestamp is missing or not a string')
 if at.endswith(' UTC'):at=at[:-4]+'+00:00'
 value=datetime.fromisoformat(at.replace('Z','+00:00'))
 if value.tzinfo is None:raise ValueError('Receipt timestamp needs timezone')
 return value


