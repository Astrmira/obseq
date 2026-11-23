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
struct W {
    F f;
    std::array<i128,4> delta;
    explicit W(F a):f(a) {
        std::array<i128,6> fixed;
        for(int i=0;i<6;i++){
            assert(std::isfinite(a[i]) && std::abs(a[i])<=1e8);
            double v=std::ldexp(a[i],58);
            assert(v==std::trunc(v));
            fixed[i]=static_cast<i128>(v);
            assert(std::ldexp(static_cast<double>(fixed[i]),-58)==a[i]);
        }
        delta={fixed[0]-fixed[4],fixed[3]-fixed[5],fixed[1]-fixed[5],fixed[2]-fixed[4]};
    }
    int exact()const{return exact_sign(delta[0],delta[1],delta[2],delta[3]);}
    int filtered(bool &fall)const{
        constexpr double u=0x1p-53;
        double p=(f[0]-f[4])*(f[3]-f[5]),q=(f[1]-f[5])*(f[2]-f[4]),v=p-q;
        fall=!(std::abs(v)>(3+16*u)*u*(std::abs(p)+std::abs(q)));
        return fall?exact():s(v);
    }
};
F hard(int j){
    double u=100000000.-j%999;
    if(j%3==0)return {u,u-1,u-1,u-2,0,0};
    if(j%3==1)return {u-1,u-2,u,u-1,0,0};
    return {u,u,u-1,u-1,0,0};
}
int main(int argc,char**argv){
    assert(argc==3);
    assert(std::numeric_limits<double>::is_iec559&&std::fegetround()==FE_TONEAREST);
    // Deliberate local architecture check for the frozen little-endian double packet.
    uint16_t order=1;assert(*reinterpret_cast<const uint8_t*>(&order)==1);
    std::ifstream in(argv[1],std::ios::binary);
    std::vector<W> native; native.reserve(243727);
    std::ofstream labels(argv[2],std::ios::binary);
    uint64_t native_fallback=0;
    for(F f;in.read(reinterpret_cast<char*>(f.data()),48);){
        W w(f);
        bool slow=false;
        int v=w.filtered(slow);native_fallback+=slow;
        assert(v==w.exact());labels.put(static_cast<char>(v+1));native.push_back(w);
    }
    assert(in.eof()&&in.gcount()==0&&native.size()==243727&&native_fallback==53);
    labels.close();
    std::vector<W> adversarial;
    for(int i=0;i<2997;i++){
        W w(hard(i));bool f=false;int j=w.filtered(f);
        assert(f&&j==w.exact()&&j==(i%3==0?-1:i%3==1?1:0));adversarial.push_back(w);
    }
    uint64_t n=100000000;
    using clock=std::chrono::steady_clock;
    std::cout<<"workload,trial,method,n,nanos,negative,zero,positive,fallback\n";
    for(bool stress:{false,true}){
        std::array<uint64_t,3> base{};
        for(int rep=0;rep<4;rep++)for(int ix=0;ix<2;ix++){
            bool filter=(rep&1)^ix; std::array<uint64_t,3> count{};uint64_t fb=0;
            auto start=clock::now();
            for(uint64_t j=0;j<n;j++){
                const W& w=stress&&j%64==0?adversarial[(j/64)%adversarial.size()]:native[j%native.size()];
                int r;
                if(filter){bool slow=false;r=w.filtered(slow);fb+=slow;}
                else r=w.exact();
                ++count[r+1];
            }
            uint64_t elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(clock::now()-start).count();
            if(rep==0&&ix==0)base=count;
            else assert(count==base);
            std::cout<<(stress?"pressure":"native_tiled")<<","<<rep<<","<<(filter?"filtered":"fixedpoint")
                     <<","<<n<<","<<elapsed<<","<<count[0]<<","<<count[1]<<","<<count[2]<<","<<fb<<"\n";
        }
    }
    rusage r; getrusage(RUSAGE_SELF,&r);std::cerr<<"peak_rss_kib "<<r.ru_maxrss<<"\n";
}
