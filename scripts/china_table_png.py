"""Render analytical Markdown tables as frozen, scoped PNG delivery parts."""
import base64
import hashlib
import io
import re
import time
from datetime import datetime, timezone

PREFIX = 'CHINA_TABLE_PNG:'
KEY = 'china_agent:table_png:v1:'
PAVEL_ID = 307200273
PAVEL_TEXT_LIMIT = 450

def render_timing(w, job, started, **extra):
    key='china_agent:reply_latency:v1:'+str(job['id'])
    value=dict(w.get(key) or {})
    metric='artifact_cache_lookup_ms'if extra.get('artifact_cache_hit')else'render_ms'
    value.update(job_id=job['id'], stage='render', observed_at=datetime.now(timezone.utc).isoformat(), **{metric:round((time.perf_counter()-started)*1000,3)}, **extra)
    w.save(key,value)

def cells(line):
    return [x.strip() for x in re.split(r'(?<!\\)\|', line.strip().strip('|'))]

def blocks(text):
    lines = text.splitlines(); result = []; prose = []; i = 0; fenced = False
    def flush():
        if prose:
            value = '\n'.join(prose).strip()
            if value: result.append(('text', value))
            prose.clear()
    while i < len(lines):
        if lines[i].lstrip().startswith('```'): fenced = not fenced
        header = cells(lines[i])
        divider = cells(lines[i+1]) if i+1 < len(lines) else []
        if not fenced and len(header) >= 2 and len(divider) == len(header) and all(re.fullmatch(r':?-{3,}:?', x) for x in divider):
            flush(); rows = []; i += 2
            while i < len(lines) and '|' in lines[i]:
                row = cells(lines[i])
                if len(row) != len(header): break
                rows.append(row); i += 1
            result.append(('table', (header, rows)))
        else:
            prose.append(lines[i]); i += 1
    flush(); return result

def render(header, rows, title='Китай · аналитика'):
    from PIL import Image, ImageDraw, ImageFont
    def font(n, bold=False):
        for path in [('C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf'), ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]:
            try: return ImageFont.truetype(path, n)
            except OSError: pass
        return ImageFont.load_default(size=n)
    f, bf = font(23), font(23, True)
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    def clean(t): return re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', t).replace('**', '').replace('`', '').replace('\\|', '|').replace('<br>', '\n')
    # Weight columns by actual content; long recommendation columns get more space.
    weights = [min(80, max(len(clean(row[k])) for row in [header]+rows))**0.6 for k in range(len(header))]
    widths = [max(170, int(1720 * x / sum(weights))) for x in weights]
    width = sum(widths)+40
    def wrap(t, w, ft):
        out = []
        for para in clean(t).split('\n'):
            line = ''
            for char in para:
                if line and measure.textlength(line+char, font=ft) > w:
                    cut = line.rfind(' ')
                    if cut > len(line)//2:
                        out.append(line[:cut]); line = line[cut+1:]+char
                    else: out.append(line); line = char
                else: line += char
            out.append(line)
        return out
    def layout(row, ft):
        wrapped = [wrap(t, w-28, ft) for t, w in zip(row, widths)]
        return wrapped, max(len(x) for x in wrapped)*31+28
    heads, hh = layout(header, bf)
    pages = []; batch = []; height = 112+hh+55
    for row in rows:
        lines, rh = layout(row, f)
        if batch and height+rh > 2450:
            pages.append(batch); batch = []; height = 112+hh+55
        batch.append((lines, rh)); height += rh
    pages.append(batch)
    result = []
    for page, group in enumerate(pages):
        h = 112+hh+sum(rh for _, rh in group)+55
        im = Image.new('RGB', (width, h), '#eff4f8'); d = ImageDraw.Draw(im)
        d.rectangle((0, 0, width, 95), fill='#1e3d50')
        d.text((24, 25), title+(' · '+str(page+1)+'/'+str(len(pages)) if len(pages)>1 else ''), font=font(30, True), fill='white')
        y = 112
        for idx, (lines, rh) in enumerate([(heads, hh)]+group):
            bg = '#1e3d50' if idx == 0 else ('white' if idx % 2 else '#e2ebf3')
            d.rectangle((20, y, width-20, y+rh-3), fill=bg); x = 20
            for col, ls in enumerate(lines):
                for k, line in enumerate(ls):
                    d.text((x+14, y+14+k*31), line, font=bf if idx == 0 else f, fill='white' if idx == 0 else '#253f52')
                x += widths[col]
            y += rh
        d.text((24, y+12), 'Аналитический ответ · изменения только после подтверждения', font=font(20), fill='#657b8a')
        buf = io.BytesIO(); im.save(buf, format='PNG'); result.append(buf.getvalue())
    return result

def delivery_parts(w, job, answer, split):
    started = time.perf_counter()
    key = KEY+str(job['id']); saved = w.get(key)
    pavel = job.get('sender_id') == PAVEL_ID
    pavel_long = pavel and len(answer) > PAVEL_TEXT_LIMIT
    if saved:
        if saved['chat_id'] != job['chat_id'] or saved['answer_sha256'] != hashlib.sha256(answer.encode()).hexdigest(): raise PermissionError('Frozen table scope changed')
        if pavel_long and not all(p.startswith(PREFIX) for p in saved['parts']): raise PermissionError('Frozen long Pavel answer is not PNG-only; no blind delivery migration')
        render_timing(w,job,started,answer_chars=len(answer),png_only=pavel_long,additional_model_calls=0,artifact_cache_hit=True)
        return saved['parts']
    if pavel and not pavel_long:
        render_timing(w,job,started,answer_chars=len(answer),png_only=False,additional_model_calls=0,artifact_cache_hit=False)
        return [answer]
    parsed = blocks(answer)
    if pavel_long:
        parsed = [('table', (['Ответ Павлу'], [[data] if kind == 'text' else [' | '.join(data[0]) + '\n' + '\n'.join(' | '.join(row) for row in data[1])] for kind, data in parsed]))]
    if not any(kind == 'table' for kind, _ in parsed): return [answer] if job.get('sender_id') == 307200273 else split(answer)
    # A deployment must not change identities for an already partially delivered answer.
    if any(w.get('china_agent:conversion_watch_delivery:v1:'+prefix+str(job['id'])+':0') for prefix in ('question:', 'codex_bridge:')):
        if pavel_long: raise PermissionError('Existing delivery requires frozen original parts')
        return split(answer)
    files = []; parts = []
    for kind, data in parsed:
        if kind == 'text': parts.extend(split(data))
        else:
            for blob in render(*data):
                index = len(files)
                files.append(dict(sha256=hashlib.sha256(blob).hexdigest(), data=base64.b64encode(blob).decode()))
                parts.append(PREFIX+key+':'+str(index))
    render_timing(w,job,started,answer_chars=len(answer),png_only=pavel_long,additional_model_calls=0,artifact_cache_hit=False)
    saved = dict(status='frozen', job_id=job['id'], chat_id=job['chat_id'], answer_sha256=hashlib.sha256(answer.encode()).hexdigest(), files=files, parts=parts)
    if not w.save(key, saved, insert=True):
        frozen=w.get(key) or {}
        if frozen.get('chat_id')!=job['chat_id'] or frozen.get('answer_sha256')!=saved['answer_sha256'] or frozen.get('parts')!=parts: raise PermissionError('Concurrent artifact conflict; no recursive retry')
        return frozen['parts']
    return parts

def photo(w, chat, text):
    if text.startswith('CHINA_SCHEDULED_TABLE_PNG:'):
        return scheduled_photo(w, chat, text)
    if not text.startswith(PREFIX): return None
    key, index = text[len(PREFIX):].rsplit(':', 1); saved = w.get(key)
    if not saved or saved.get('status') != 'frozen' or saved['chat_id'] != chat or saved['job_id'] != getattr(w, 'active_question_id', None): raise PermissionError('Table PNG question scope')
    i = int(index)
    if not 0 <= i < len(saved['files']): raise ValueError('Table PNG index')
    part = saved['files'][i]; blob = base64.b64decode(part['data'], validate=True)
    if hashlib.sha256(blob).hexdigest() != part['sha256']: raise ValueError('Table PNG hash')
    return blob, 'Таблица к аналитическому ответу. Изменения не применены.'


def scheduled_parts(w, report_key, chat, answer, split):
    """Freeze scheduled tables independently of human question IDs."""
    key = KEY+'scheduled:'+report_key
    saved = w.get(key)
    digest = hashlib.sha256(answer.encode()).hexdigest()
    if saved:
        if saved.get('chat_id') != chat or saved.get('answer_sha256') != digest or saved.get('report_key') != report_key:
            raise PermissionError('Scheduled table scope changed')
        return saved['parts']
    parsed = blocks(answer)
    if not any(kind == 'table' for kind, _ in parsed): return split(answer)
    if w.get('china_agent:conversion_watch_delivery:v1:'+report_key+':part:0'):
        return split(answer)
    files = []; parts = []
    for kind, data in parsed:
        if kind == 'text': parts.extend(split(data))
        else:
            for blob in render(*data):
                index = len(files)
                files.append(dict(sha256=hashlib.sha256(blob).hexdigest(), data=base64.b64encode(blob).decode()))
                parts.append('CHINA_SCHEDULED_TABLE_PNG:'+key+':'+str(index))
    saved = dict(status='frozen', report_key=report_key, chat_id=chat, answer_sha256=digest, files=files, parts=parts)
    if not w.save(key, saved, insert=True):
        return scheduled_parts(w, report_key, chat, answer, split)
    return parts

def scheduled_photo(w, chat, text):
    key, index = text[len('CHINA_SCHEDULED_TABLE_PNG:'):].rsplit(':', 1)
    saved = w.get(key)
    if not saved or saved.get('status') != 'frozen' or saved.get('chat_id') != chat or saved.get('report_key') != getattr(w, 'active_report_key', None):
        raise PermissionError('Scheduled table PNG scope')
    i = int(index)
    if not 0 <= i < len(saved['files']): raise ValueError('Scheduled table PNG index')
    part = saved['files'][i]; blob = base64.b64decode(part['data'], validate=True)
    if hashlib.sha256(blob).hexdigest() != part['sha256']: raise ValueError('Scheduled table PNG hash')
    return blob, 'Таблица к плановому аналитическому отчёту. Изменения не применены.'


