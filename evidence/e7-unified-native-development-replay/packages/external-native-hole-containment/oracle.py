import math
from fractions import Fraction as F
def exact(point):return tuple(map(F,point))
def orient(a,b,c):
 return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def between(a,b,p):return all(min(a[i],b[i])<=p[i]<=max(a[i],b[i]) for i in range(2))
def line(a,b,p):return orient(a,b,p)==0 and between(a,b,p)
def intersect(a,b,c,d):
 if line(a,b,c) or line(a,b,d) or line(c,d,a) or line(c,d,b):return True
 return orient(a,b,c)*orient(a,b,d)<0 and orient(c,d,a)*orient(c,d,b)<0
def scoped(part):
 if len(part)!=1:return False
 r=list(map(exact,part[0]));n=len(r)-1
 if not 3<=n<=220 or len(set(r[:-1]))!=n:return False
 if not all(orient(r[i-1 if i else n-1],r[i],r[i+1]) for i in range(n)):return False
 if not sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(r,r[1:])):return False
 edges=list(zip(r,r[1:]))
 return not any(intersect(*edges[i],*edges[j]) for i in range(n) for j in range(i+2,n)
                if not (i==0 and j==n-1))
def classify(ring,p):
 p=exact(p)
 parity=False
 for a,b in zip(ring,ring[1:]):
  o=orient(a,b,p)
  if not o and between(a,b,p):return 'boundary'
  if (a[1]>p[1])!=(b[1]>p[1]) and (o>0)==(b[1]>a[1]):parity=not parity
 return 'interior' if parity else 'exterior'
def points(ring):
 p=set(ring[:-1]);anchor=sorted(p)
 for (x,y) in anchor:
  for sign in (-math.inf,math.inf):
   p.add((math.nextafter(x,sign),y));p.add((x,math.nextafter(y,sign)))
 for a,b in zip(ring,ring[1:]):
  target=tuple((x+y)/2 for x,y in zip(exact(a),exact(b)))
  candidate=tuple(map(float,target))
  if exact(candidate)==target:p.add(candidate)
 xx,yy=zip(*ring);a,b=min(xx),max(xx);c,d=min(yy),max(yy)
 for i in range(7):
  for j in range(7):p.add((a+(b-a)*(i+1)/8,c+(d-c)*(j+1)/8))
 p.add((a-(b-a),c-(d-c)))
 return sorted(p)
def name(s):
 assert s.replace('_','').isalnum()
 return '"'+s+'"'
