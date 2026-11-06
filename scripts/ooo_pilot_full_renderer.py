"""Render a bounded private report bundle; no network, model, or business constants."""
import io,os
from PIL import Image,ImageDraw,ImageFont
def render(bundle,decision,kind):
 W=2600;navy='#193e52';ink='#172c38'
 def f(n=26,b=False):
  p=('C:/Windows/Fonts/arial'+('bd'if b else'')+'.ttf')if os.name=='nt'else('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold'if b else'')+'.ttf')
  return ImageFont.truetype(p,n)
 im=Image.new('RGB',(W,11000),'#edf3f7');d=ImageDraw.Draw(im)
 def lines(t,w,n=26,b=False):
  out=[]
  for para in str(t).split('\n'):
   cur=''
   for word in para.split():
    nxt=(cur+' '+word).strip()
    if cur and d.textlength(nxt,font=f(n,b))>w:out.append(cur);cur=word
    else:cur=nxt
   out.append(cur)
  return out
 d.rectangle((0,0,W,210),fill=navy)
 for y,t,n in [(22,bundle['titles'][kind],40),(83,bundle['period'],28),(139,bundle['sources'],25)]:d.text((35,y),t,font=f(n,True),fill='white')
 selected=set(decision['selected']);xs=bundle['columns'][kind];y=245
 for i,t in enumerate(bundle['headers'][kind]):
  for k,l in enumerate(lines(t,xs[i+1]-xs[i]-22,25,True)):d.text((xs[i],y+k*32),l,font=f(25,True),fill=navy)
 y=350
 for row in bundle['rows'][kind]:
  if row.get('candidate_id')and row['candidate_id']not in selected:continue
  cells=list(row['cells']);group=row.get('group',False)
  if row.get('candidate_id'):cells[-1]=bundle['actions'][row['candidate_id']]['display']
  ll=[lines(t,xs[i+1]-xs[i]-25,26,group or i==len(cells)-1)for i,t in enumerate(cells)]
  h=max(map(len,ll))*34+28;d.rounded_rectangle((20,y,W-20,y+h),10,fill='#d9e7ee'if group else'white')
  for i,ls in enumerate(ll):
   for k,l in enumerate(ls):
    col=ink
    if kind=='advertising'and i in(2,3):
     v=row.get('drr3'if i==2 else'drrday');col=('#247447'if v<=5 else'#b32f36')if v is not None else ink
    if kind=='budgets'and l.startswith('ДРР'):
     v=row.get('drr3'if '3 дня' in l else'drrday');col=('#247447'if v<=5 else'#b32f36')if v is not None else ink
    d.text((xs[i],y+13+k*34),l,font=f(26,group or i==len(cells)-1),fill=col)
  y+=h+9
 if kind=='advertising':
  y+=15;d.rounded_rectangle((20,y,W-20,y+205),14,fill=navy)
  for k,t in enumerate(bundle['totals_display']):d.text((40,y+18+k*57),t,font=f(31,True),fill='white')
  y+=233
 notes=bundle['notes'][kind]
 if kind=='advertising':notes=decision['assessment']+notes
 for t in notes:
  for l in lines(t,W-80,24):d.text((40,y),l,font=f(24),fill=ink);y+=32
  y+=13
 if y>11000:raise ValueError('Report height exceeded')
 b=io.BytesIO();im.crop((0,0,W,y+24)).save(b,format='PNG');return b.getvalue()

