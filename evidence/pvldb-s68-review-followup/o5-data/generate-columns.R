suppressPackageStartupMessages(library(data.table))
setDTthreads(1L)
a=commandArgs(TRUE)
N=as.numeric(a[[1L]]); K=as.integer(a[[2L]])
chunk=as.integer(a[[3L]]); stage=a[[4L]]; target=a[[5L]]
stopifnot(N>=1L, N<=1e8, N%%K==0, chunk>=100L, dir.exists(stage), !file.exists(target))
stopifnot(as.character(packageVersion("data.table"))=="1.17.0",getRversion()=="4.5.0")
stopifnot(identical(RNGkind(), c("Mersenne-Twister","Inversion","Rejection")))
set.seed(108)
counts=c(K,K,as.integer(N/K),K,K,as.integer(N/K),5L,15L)
names=c(paste0("id",1:6),paste0("v",1:3))
paths=file.path(stage,paste0(names,".raw.gz"))
windows=seq(0,N-1,by=chunk)
for(j in seq_len(9)) {
  h=gzfile(paths[[j]],"wb",compression=2L)
  for(i in windows){
    len=min(chunk,N-i)
    if(j<=8)writeBin(sample.int(counts[[j]],len,replace=TRUE),h,size=4L,endian="little")
    else writeBin(round(runif(len,max=100),6),h,size=8L,endian="little")
  }
  close(h)
  cat("column",names[[j]],file.info(paths[[j]])$size,"bytes\n")
  flush.console()
}
