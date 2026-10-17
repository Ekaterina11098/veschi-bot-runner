"""Verified Telegram chat lineage; historical jobs and receipt identities stay immutable."""
KEY = 'china_agent:chat_migration:v1:'


def accepted_chat(db, previous, current, bot_id, owner_id):
    if previous == current:
        return True
    rows = db('GET', 'telegram_api_cache', params={'cache_key':'eq.'+KEY+str(current), 'select':'payload', 'limit':1}) or []
    p = rows[0]['payload'] if rows else {}
    return (p.get('verified') is True and p.get('agent_id') == 'china'
            and p.get('to_chat_id') == current and p.get('bot_id') == bot_id
            and p.get('owner_user_id') == owner_id and previous in p.get('previous_chat_ids', []))


def previous_chats(db, cfg):
    rows = db('GET', 'telegram_api_cache', params={'cache_key':'eq.'+KEY+str(cfg['chat_id']), 'select':'payload', 'limit':1}) or []
    p = rows[0]['payload'] if rows else {}
    if not rows or not accepted_chat(db, p.get('from_chat_id'), cfg['chat_id'], cfg['bot_id'], cfg['owner_user_id']):
        return []
    return p['previous_chat_ids']


def install(root='source'):
    from pathlib import Path
    import shutil
    target = Path(root)/'china_agent'
    shutil.copyfile(__file__, target/'chat_migration.py')
    path = target/'daily_report_worker.py'
    if path.exists():
        text = path.read_text(encoding='utf-8')
        old = "        if not previous or previous[0]['chat_id'] != self.chat:\n"
        new = "        from .chat_migration import accepted_chat\n        if not previous or not accepted_chat(self.db, previous[0]['chat_id'], self.chat, cfg.get('bot_id'), cfg['owner_user_id']):\n"
        if old not in text and new not in text:
            raise RuntimeError('China report recipient guard changed; review required')
        text=text.replace(old,new)
        old2="self.job['chat_id'] != self.chat"
        new2="(self.job['chat_id'] != self.chat and not (self.job['status'] == 'done' and accepted_chat(self.db, self.job['chat_id'], self.chat, cfg.get('bot_id'), cfg['owner_user_id'])))"
        if new2 not in text:text=text.replace(old2,new2)
        path.write_text(text,encoding='utf-8')


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--root',default='source')
    install(parser.parse_args().root)
