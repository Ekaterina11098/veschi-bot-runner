/** Small deterministic PNG charts; no external renderer, data URL or public upload. */
const FONT={
'0':['01110','10001','10011','10101','11001','10001','01110'],'1':['00100','01100','00100','00100','00100','00100','01110'],'2':['01110','10001','00001','00010','00100','01000','11111'],'3':['11110','00001','00001','01110','00001','00001','11110'],'4':['00010','00110','01010','10010','11111','00010','00010'],'5':['11111','10000','10000','11110','00001','00001','11110'],'6':['01110','10000','10000','11110','10001','10001','01110'],'7':['11111','00001','00010','00100','01000','01000','01000'],'8':['01110','10001','10001','01110','10001','10001','01110'],'9':['01110','10001','10001','01111','00001','00001','01110'],
'.':['0','0','0','0','0','1','1'],',':['0','0','0','0','1','1','1'],'-':['00000','00000','00000','11111','00000','00000','00000'],' ':['000','000','000','000','000','000','000'],
'C':['01111','10000','10000','10000','10000','10000','01111'],'N':['10001','11001','11001','10101','10011','10011','10001'],'Y':['10001','10001','01010','00100','00100','00100','00100'],
'З':['11110','00001','00001','01110','00001','00001','11110'],'А':['01110','10001','10001','11111','10001','10001','10001'],'К':['10001','10010','10100','11000','10100','10010','10001'],'Ы':['10001','10001','10001','11101','10011','10011','11101'],'С':['01111','10000','10000','10000','10000','10000','01111'],'У':['10001','10001','10001','01111','00001','00001','11110'],'М':['10001','11011','10101','10101','10001','10001','10001']};
const table=Array.from({length:256},(_,n)=>{for(let k=0;k<8;k++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0;});
function crc(a){let c=0xffffffff;for(const b of a)c=table[(c^b)&255]^(c>>>8);return(c^0xffffffff)>>>0;}
function uint(n){return new Uint8Array([(n>>>24)&255,(n>>>16)&255,(n>>>8)&255,n&255]);}
function join(parts){const a=new Uint8Array(parts.reduce((n,p)=>n+p.length,0));let i=0;for(const p of parts){a.set(p,i);i+=p.length;}return a;}
function chunk(s,data){const type=new TextEncoder().encode(s),body=join([type,data]);return join([uint(data.length),body,uint(crc(body))]);}
Object.assign(FONT,{'Л':['00111','01001','01001','01001','01001','01001','10001'],'И':['10001','10011','10101','10101','11001','10001','10001'],'О':['01110','10001','10001','10001','10001','10001','01110'],'Т':['11111','00100','00100','00100','00100','00100','00100'],'Р':['11110','10001','10001','11110','10000','10000','10000'],'Я':['01111','10001','10001','01111','00101','01001','10001'],'R':['11110','10001','10001','11110','10100','10010','10001'],'%':['11001','11010','00100','01000','10110','00110','00000']});
export async function salesChart(points,labels=null){
 const W=800,H=780,pixels=new Uint8Array(W*H*3).fill(255);
 const set=(x,y,c)=>{x=Math.round(x);y=Math.round(y);if(x<0||x>=W||y<0||y>=H)return;const i=(y*W+x)*3;pixels.set(c,i);};
 const rect=(x,y,w,h,c)=>{for(let j=y;j<y+h;j++)for(let i=x;i<x+w;i++)set(i,j,c);};
 const line=(x0,y0,x1,y1,c,width=2)=>{const steps=Math.ceil(Math.max(Math.abs(x1-x0),Math.abs(y1-y0)))||1;for(let i=0;i<=steps;i++)rect(Math.round(x0+(x1-x0)*i/steps),Math.round(y0+(y1-y0)*i/steps),width,width,c);};
 const text=(x,y,s,scale=3,c=[36,65,85])=>{for(const ch of s){const glyph=FONT[ch]||FONT[' '];for(let j=0;j<7;j++)for(let i=0;i<glyph[j].length;i++)if(glyph[j][i]==='1')rect(x+i*scale,y+j*scale,scale,scale,c);x+=(glyph[0].length+1)*scale;}};
 const blue=[36,139,200],grid=[221,231,237],gray=[101,124,139];
 for(let chart=0;chart<2;chart++){
  const top=45+chart*370,left=110,right=765,y0=top+55,y1=top+280,field=chart?'amount_cny':'count';
  text(28,top,labels?labels[chart]:chart?'СУММА, CNY':'ЗАКАЗЫ',4);
  const vals=points.map(p=>p[field]).filter(n=>typeof n==='number'&&Number.isFinite(n));
  const max=Math.max(1,...vals)*1.12;
  for(let i=0;i<=4;i++){const y=y1-(y1-y0)*i/4;line(left,y,right,y,grid,1);text(8,y-9,String(labels&&chart?Math.round(max*i/4*100)/100:Math.round(max*i/4)),2,gray);}
  line(left,y0,left,y1,gray,2);line(left,y1,right,y1,gray,2);
  let prev=null;
  points.forEach((p,i)=>{
   const x=left+(right-left)*(points.length===1?.5:i/(points.length-1));
   if((i%Math.max(1,Math.ceil(points.length/7))===0&&(i===0||x<right-85))||i===points.length-1)text(Math.min(x-26,right-54),y1+18,p.date.slice(8,10)+'.'+p.date.slice(5,7),2,gray);
   const v=p[field];
   if(typeof v!=='number'||!Number.isFinite(v)){line(x-4,y1-8,x+4,y1-8,gray,2);prev=null;return;}
   const y=y1-(y1-y0)*v/max;if(prev)line(prev[0],prev[1],x,y,blue,3);
   rect(Math.round(x)-3,Math.round(y)-3,7,7,blue);prev=[x,y];
  });
 }
 const raw=new Uint8Array(H*(1+W*3));for(let y=0;y<H;y++){raw[y*(1+W*3)]=0;raw.set(pixels.subarray(y*W*3,(y+1)*W*3),y*(1+W*3)+1);}
 const compressor=new CompressionStream('deflate'),writer=compressor.writable.getWriter();const read=new Response(compressor.readable).arrayBuffer();await writer.write(raw);await writer.close();const compressed=new Uint8Array(await read);
 const header=join([uint(W),uint(H),new Uint8Array([8,2,0,0,0])]);
 return join([new Uint8Array([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',compressed),chunk('IEND',new Uint8Array())]);
}
