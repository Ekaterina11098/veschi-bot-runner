"""Render analytical Markdown tables as frozen, scoped PNG delivery parts."""
import base64
import hashlib
import io
import re

PREFIX = 'CHINA_TABLE_PNG:'
KEY = 'china_agent:table_png:v1:'

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

def render(header, rows, title='ИП · ответ агента'):
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


def render_answer(answer):
 parsed=blocks(answer)
 tables=[data for kind,data in parsed if kind=='table']
 if len(tables)==1 and all(kind=='table' or len(data)<150 for kind,data in parsed):
  pages=render(*tables[0])
 else:pages=render(['Ответ'],[[answer]])
 if len(pages)!=1:pages=render(['Ответ'],[[answer]])
 if len(pages)!=1:raise ValueError('Bounded answer must fit one PNG')
 return pages[0]

