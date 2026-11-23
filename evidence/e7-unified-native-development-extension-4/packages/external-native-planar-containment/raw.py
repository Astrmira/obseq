import math,struct

def wkb(blob):
 assert blob[:2]==b'GP' and blob[2]==0
 flags=blob[3];assert flags&0xf0==0
 env=(flags>>1)&7; assert env in (0,1,2,3,4)
 start=8+[0,32,48,48,64][env]
 def read_geom(pos):
  order=blob[pos];assert order in (0,1)
  F='<' if order else '>'; t=struct.unpack_from(F+'I',blob,pos+1)[0];pos+=5
  def count():
   nonlocal pos
   n=struct.unpack_from(F+'I',blob,pos)[0];pos+=4
   assert n<1000000
   return n
  if t==3:
   rings=[]
   for _ in range(count()):
    n=count()
    ring=list(struct.iter_unpack(F+'dd',blob[pos:pos+16*n]));pos+=16*n
    assert len(ring)==n and n>=4 and ring[0]==ring[-1]
    assert all(math.isfinite(a) and math.isfinite(b) for a,b in ring)
    rings.append(ring)
   assert rings
   return [rings],pos
  assert t==6
  result=[]
  for _ in range(count()):
   assert struct.unpack_from(('<' if blob[pos] else '>')+'I',blob,pos+1)[0]==3
   x,pos=read_geom(pos);result.extend(x)
  return result,pos
 result,end=read_geom(start)
 assert result and end==len(blob)
 return result
