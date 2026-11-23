#include <array>
#include <cassert>
#include <cfenv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <string>
#include <utility>
#include <vector>
#include <sys/resource.h>
using i128=__int128_t;
using u128=__uint128_t;
using P=std::pair<u128,u128>;
using F=std::array<double,6>;
template<class T> int s(T q){return (q>0)-(q<0);}
P mul(u128 a,u128 b){
    u128 hi=(a>>64)*(b>>64);
    u128 lo=u128(uint64_t(a))*uint64_t(b);
    for(u128 z:{(a>>64)*uint64_t(b),u128(uint64_t(a))*(b>>64)}){
        u128 saved=lo;
        lo+=z<<64;
        hi+=(z>>64)+(lo<saved);
    }
    return {hi,lo};
}
u128 mag(i128 x){return x<0?u128(-x):u128(x);}
int exact_sign(i128 a,i128 b,i128 c,i128 d){
    int ps=s(a)*s(b),qs=s(c)*s(d);
    if(ps!=qs)return s(ps-qs);
    if(!ps)return 0;
    P p=mul(mag(a),mag(b)),q=mul(mag(c),mag(d));
    return ((p>q)-(p<q))*ps;
}
int fixed_exact(const F& a){
    std::array<i128,6> v;
    for(int i=0;i<6;i++) v[i]=static_cast<i128>(a[i]*0x1p68);
    return exact_sign(v[0]-v[4],v[3]-v[5],v[1]-v[5],v[2]-v[4]);
}
#include <bit>
#include <cstdlib>
int filter_sign(const F& f,bool& fback){
    constexpr double u=0x1p-53;
    double p=(f[0]-f[4])*(f[3]-f[5]),q=(f[1]-f[5])*(f[2]-f[4]),v0=p-q;
    fback=!(std::abs(v0)>(3+16*u)*u*(std::abs(p)+std::abs(q)));
    return fback?fixed_exact(f):s(v0);
}
template<int mode> void run( const std::vector<F>& native, const std::vector<char>& oracle, uint64_t n, int rep) {
    uint64_t fb=0, mismatches=0, token=0, done=0;
    std::array<uint64_t,3> count{};
    auto start=std::chrono::steady_clock::now();
    for(unsigned k=0;done<n;k++){
        double x=std::ldexp(1.,int(k%21)-10),y=std::ldexp(1.,int(k/21)-10);
        assert(k<441);
        for(size_t i=0;i<native.size()&&done<n;++i,++done){
            F f=native[i];
            for (int j=0;j<6;++j) f[j]*=(j%2?y:x);
            if constexpr(mode==0) {
                // Make all six transformed values observable in the producer floor.
                for(double d:f) token+=std::bit_cast<uint64_t>(d);
            } else {
                int v;
                if constexpr(mode==1) v=fixed_exact(f);
                else {
                    bool fback;
                    v=filter_sign(f,fback);
                    fb+=fback;
                }
                mismatches+=v+1!=oracle[i];
                ++count[v+1];
            }
        }
    }
    auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
    rusage r;getrusage(RUSAGE_SELF,&r);
    assert(mismatches==0);
    std::cout<<rep<<","<<mode<<","<<n<<","<<elapsed<<","<<r.ru_maxrss<<","<<count[0]<<","<<count[1]<<","<<count[2]<<","<<fb<<","<<mismatches<<","<<token<<"\n";
}
int main(int argc,char**argv){
    assert(argc==6);
    assert(std::numeric_limits<double>::is_iec559&&std::fegetround()==FE_TONEAREST);
    assert(std::endian::native==std::endian::little);
    std::ifstream in(argv[1],std::ios::binary), lab(argv[2],std::ios::binary);
    std::vector<F> native; native.reserve(243727);
    for(F f;in.read(reinterpret_cast<char*>(f.data()),48);){
        assert((f[0]!=0||f[2]!=0||f[4]!=0)&&(f[1]!=0||f[3]!=0||f[5]!=0));
        for(double x:f) {double z=std::ldexp(x,58);assert(z==std::trunc(z)&&std::abs(x)<256);}
        native.push_back(f);
    }
    std::vector<char> oracle((std::istreambuf_iterator<char>(lab)),{});
    assert(in.eof()&&in.gcount()==0&&native.size()==243727&&oracle.size()==native.size());
    for(int x:{-10,0,10}) for(int y:{-10,0,10}) for(int type=0;type<3;type++){
        double t=100000000.;
        F f=type==0?F{t,t-1,t-1,t-2,0,0}:
            type==1?F{t-1,t-2,t,t-1,0,0}:F{t,t,t-1,t-1,0,0};
        for(int j=0;j<6;j++) f[j]=std::ldexp(f[j],j%2?y:x);
        bool back;
        int label=(type==0?-1:type==1?1:0);
        assert(filter_sign(f,back)==label && back && fixed_exact(f)==label);
    }
    int mode=std::atoi(argv[3]),rep=std::atoi(argv[4]);uint64_t n=std::strtoull(argv[5],nullptr,10);
    if(mode==0)run<0>(native,oracle,n,rep);
    else if(mode==1)run<1>(native,oracle,n,rep);
    else if(mode==2)run<2>(native,oracle,n,rep);
    else return 2;
}
