"""Approved combined blue/white report: prose and all tables in one PNG."""
import io,re
def render(answer):
    from PIL import Image,ImageDraw
    from china_agent_reports import font
    from china_table_png import blocks
    width,pad=1900,34;ink='#233d52';dark='#1d3d51';bg='#eef4f8'
    f,bf,head=font(25),font(25,True),font(28,True)
    measure=ImageDraw.Draw(Image.new('RGB',(1,1)))
    def clean(t):return re.sub(r'\[([^]]+)\]\([^)]+\)',r'\1',str(t)).replace('**','').replace('`','').replace('<br>','\n').replace('\\|','|').strip()
    def wrap(t,w,ft):
        out=[]
        for paragraph in clean(t).split('\n'):
            line=''
            for word in paragraph.split():
                candidate=(line+' '+word).strip()
                if line and measure.textlength(candidate,font=ft)>w:out.append(line);line=''
                if measure.textlength(word,font=ft)>w:
                    for char in word:
                        if line and measure.textlength(line+char,font=ft)>w:out.append(line);line=''
                        line+=char
                else:line=(line+' '+word).strip()
            out.append(line)
        return out
    layout=[];height=132
    for kind,data in blocks(answer):
        if kind=='text':
            for text in data.splitlines():
                if not text.strip():height+=9;continue
                ft=head if text.lstrip().startswith('#') else f
                lines=wrap(re.sub(r'^#{1,6}\s*','',text),width-2*pad,ft)
                layout.append(('text',height,lines,ft));height+=len(lines)*35+12
        else:
            header,rows=data
            weights=[min(100,max(len(clean(r[k])) for r in [header]+rows))**.65 for k in range(len(header))]
            widths=[max(135,int((width-2*pad)*x/sum(weights))) for x in weights];widths[-1]+=width-2*pad-sum(widths)
            if clean(header[0])=='Артикул' and widths[0]<360 and widths[-1]>360-widths[0]+140:
                extra=360-widths[0];widths[0]+=extra;widths[-1]-=extra
            for i,row in enumerate([header]+rows):
                lines=[wrap(t,w-24,bf if i==0 else f) for t,w in zip(row,widths)]
                h=max(map(len,lines))*35+28
                layout.append(('row',height,lines,widths,h,i));height+=h
            height+=20
    height+=65
    # Respect Telegram photo bounds. Large requested coverage uses the existing
    # readable pagination rather than truncating or making text microscopic.
    if height>7500:return None
    im=Image.new('RGB',(width,height),bg);d=ImageDraw.Draw(im)
    d.rectangle((0,0,width,110),fill=dark)
    d.text((pad,22),'Китай · заказы и общая прибыль',font=font(36,True),fill='white')
    d.text((pad,72),'Начисления WB и прогноз заказов — отдельно · периоды указаны в отчёте',font=font(22),fill='#dce8ef')
    for item in layout:
        if item[0]=='text':
            _,y,lines,ft=item
            for j,line in enumerate(lines):d.text((pad,y+j*35),line,font=ft,fill=ink)
        else:
            _,y,lines,widths,h,i=item;d.rectangle((pad,y,width-pad,y+h-3),fill=dark if i==0 else 'white' if i%2 else '#e1eaf2');x=pad
            for cell,w in zip(lines,widths):
                for j,line in enumerate(cell):
                    negative=bool(re.match(r'(?:≈\s*)?[−-]\s*\d',line))
                    d.text((x+12,y+12+j*35),line,font=bf if i==0 else f,fill='white' if i==0 else '#b72c36' if negative else ink)
                x+=w
    d.text((pad,height-42),'Предварительная оценка · изменения цен и рекламы только после подтверждения',font=font(21),fill='#637c8d')
    blob=io.BytesIO();im.save(blob,format='PNG');return blob.getvalue()

