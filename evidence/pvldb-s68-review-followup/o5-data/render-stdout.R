suppressPackageStartupMessages(library(data.table))
setDTthreads(1L)
args=commandArgs(TRUE)
N=as.numeric(args[[1L]]); K=as.integer(args[[2L]]); chunk=as.integer(args[[3L]])
stage=args[[4L]]; target=args[[5L]]
stopifnot(N%%K==0)
nr=c(paste0("id",1:6),paste0("v",1:3))
paths=file.path(stage,paste0(nr,".raw.gz"))
stopifnot(all(file.exists(paths)))
cons=lapply(paths,gzfile,open="rb")

labels=sprintf("id%03d",seq_len(K)); dense=sprintf("id%010d",seq_len(N/K))
for(i in seq(0,N-1,by=chunk)){
 len=min(chunk,N-i); got=vector("list",9L); names(got)=nr
 for(j in seq_len(9)){
  x=if(j<=8)readBin(cons[[j]],integer(),n=len,size=4L,endian="little") else readBin(cons[[j]],numeric(),n=len,size=8L,endian="little")
  stopifnot(length(x)==len)
  got[[j]]=if(j<=2)labels[x] else if(j==3)dense[x] else x
 }
 setDT(got)
 fwrite(got,"",col.names=(i==0),nThread=1L,showProgress=FALSE)
 if(i%%(chunk*10)==0){cat("rows",i+len,"/",N,"\n",file=stderr());flush.console()}
}
for(h in cons){stopifnot(length(readBin(h,raw(),n=1L))==0);close(h)}
cat("DONE",N,"\n",file=stderr())
