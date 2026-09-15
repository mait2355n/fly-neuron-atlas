#!/usr/bin/env python3
"""Voltage-analysis core adapted for this publication.
Call through reanalyze_ephys.py. Source-normalization algorithm uses
Wilson Lab MIT-licensed code; see ../licenses/Wilson-Lab-MIT.txt.
Paths are assigned by the caller. Computation is preserved from the
2026-09-15 research snapshot.
"""
from pathlib import Path
import argparse,csv,json,hashlib,datetime,time,gc
import numpy as np
import scipy
from scipy.io import loadmat,whosmat
from scipy import signal,ndimage
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

B=Path(__file__).resolve().parent; ROOT=B.parent; RAW=ROOT/'raw'
HZ=100; LAGS=np.arange(-50,51); RNG=np.random.default_rng(102230)
FLAGS={'a2_d_14':'author_physiology_LOW_SNR_REJECT','a1_a2_d_02':'author_DNa01_spike_detection_difficult','a1_d_09':'author_spike_detection_difficult'}

def dump(path,obj):
    def cv(v):
        if isinstance(v,np.generic):return v.item()
        if isinstance(v,np.ndarray):return v.tolist()
        raise TypeError(type(v))
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,default=cv,allow_nan=True)+'\n')

def write_csv(path,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def labels(fly):
    if fly.startswith('a1_a2_d'):return ['a2_l','a1_l']
    typ=fly[:2]
    return [typ+'_l',typ+'_r'] if '_d_' in fly else [typ+'_l']

def corr(x,y,mx,my=None,lag=0):
    if my is None:my=mx
    if lag>0:x,y,mx,my=x[:-lag],y[lag:],mx[:-lag],my[lag:]
    elif lag<0:x,y,mx,my=x[-lag:],y[:lag],mx[-lag:],my[:lag]
    m=mx & my & np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(m)<100:return np.nan
    a=x[m];b=y[m];a=a-a.mean();b=b-b.mean()
    den=np.sqrt(np.sum(a*a)*np.sum(b*b))
    return float(np.sum(a*b)/den) if den>0 else np.nan

def metrics(x,y,m,curve=True):
    rr=np.array([corr(x,y,m,lag=int(l)) for l in LAGS]) if curve else None
    shifts=[len(x)//3,2*len(x)//3]
    out={'r0':corr(x,y,m),'r150':corr(x,y,m,lag=15)}
    for i,k in enumerate(shifts):out['shift'+str(i+1)+'_r150']=corr(np.roll(x,k),y,np.roll(m,k),m,15)
    if curve and np.isfinite(rr).any():
        p=np.nanargmax(np.abs(rr));out.update(peak_abs_r=float(rr[p]),peak_abs_lag_ms=int(LAGS[p]*10))
    return out,rr

def mad_process(v,fs):
    """Independent transcription of statically read source normalization.

    Source reshape uses C order (fs,-1) and MAD axis0. This is not a
    contiguous rolling.5s estimate; preserve code semantics without relabeling.
    No author module is imported or executed.
    """
    if len(v)%fs:raise ValueError('source normalization requires integer seconds')
    dt=np.zeros_like(v,dtype=float)
    for dur in [120,30]:dt+=signal.detrend(v,bp=np.arange(0,len(v)-1,dur*fs))*.5
    order,wn=signal.buttord(wp=100,ws=.05,gpass=3,gstop=30,fs=fs)
    b,a=signal.butter(order,wn,btype='high',fs=fs)
    hp=signal.filtfilt(b,a,dt);del dt
    med=0.;scale=0.
    for shift in [-fs//2,0,fs//2]:
        arr=np.roll(hp,shift).reshape(fs,-1)
        med0=np.median(arr,axis=0)
        scale=scale+np.median(np.abs(arr-med0),axis=0)*1.4826/3
        med=med+med0/3
    del arr
    good=scale>0
    if not good.all():raise ValueError('nonpositive source normalization MAD')
    info={'noise_scale_median_mV':float(np.median(scale)),'noise_scale_p05_mV':float(np.percentile(scale,5)),'zero_mad_blocks':int((~good).sum())}
    scale_full=signal.resample(scale,len(hp));med_full=signal.resample(med,len(hp))
    hp=(hp-med_full)/scale_full
    return hp,info

def extract_spikes(proc,fs,prom,spb):
    peaks,_=signal.find_peaks(proc,height=2.5,prominence=prom,wlen=int(10*fs))
    counts=np.bincount(peaks//spb,minlength=len(proc)//spb)
    assert counts.sum()==len(peaks)
    rate=ndimage.gaussian_filter1d(counts.astype(float)*HZ,sigma=2.5,mode='nearest')
    frac=float(np.mean(np.diff(peaks)<.002*fs)) if len(peaks)>1 else np.nan
    return peaks,counts,rate,frac

def selftest():
    rng=np.random.default_rng(42);x=rng.normal(size=30000);y=np.zeros_like(x);y[15:]=x[:-15];m=np.ones(len(x),bool)
    rr=np.array([corr(x,y,m,lag=int(l)) for l in LAGS])
    assert LAGS[np.argmax(rr)]==15 and rr.max()>.999999
    assert corr(-x,y,m,lag=15)<-.999999
    spikes=np.array([0,39,40,80,99]);counts=np.bincount(spikes//40,minlength=3)
    assert counts.tolist()==[2,1,2] and counts.sum()==5
    return {'known_neural_lead_150ms':'pass','right_minus_left_sign':'pass','bin_count_conservation':'pass','no_formal_sample_pvalues':True}

def run_file(entry,limit=None):
    t0=time.time();f=entry['dataFile'];p=RAW/f['filename'];fly=entry['directoryLabel'].split('ephys_data_')[1]
    info={'fly':fly,'file':f['filename'],'file_id':f['id'],'author_quality_flag':FLAGS.get(fly,''),'status':'pending'}
    receiptp=p.with_suffix(p.suffix+'.receipt.json')
    if not p.exists() or not receiptp.exists():info['reason']='download_pending';return info,[],[],[],[]
    rec=json.loads(receiptp.read_text())
    if rec.get('status')!='verified' or rec.get('md5')!=f['checksum']['value'] or p.stat().st_size!=f['filesize']:
        info.update(status='excluded',reason='source_receipt_or_size_invalid');return info,[],[],[],[]
    info['source_md5_verified']=True
    structure=whosmat(p);info['mat_fields']=';'.join(x[0] for x in structure)
    d=loadmat(p,squeeze_me=True)
    ns=labels(fly);fs=int(d['ephys_SR']);bs=int(d['ball_SR']);spb=fs//HZ
    if fs%HZ:raise ValueError('ephys sample rate not divisible by100')
    source_te=np.asarray(d['t_ephys']);source_tb=np.asarray(d['t_ball'])
    dt=np.diff(source_te);bt=np.diff(source_tb)
    er=np.where(dt<=0)[0]+1;br=np.where(bt<=0)[0]+1
    eb=np.r_[0,er,len(source_te)];bb=np.r_[0,br,len(source_tb)]
    if len(eb)!=len(bb) or not np.allclose(eb/fs,bb/bs):raise ValueError('unmatched_ephys_ball_clock_resets')
    te=source_te.copy();tb=source_tb.copy();offset=0.;epoch_starts=[]
    for a,b,c,e in zip(eb[:-1],eb[1:],bb[:-1],bb[1:]):
        et=source_te[a:b];ballt=source_tb[c:e]
        if not np.all(np.isfinite(et)) or not np.allclose(np.diff(et),1/fs,atol=1e-7,rtol=1e-4):raise ValueError('irregular ephys within_epoch timebase')
        if not np.all(np.isfinite(ballt)) or not np.allclose(np.diff(ballt),1/bs,atol=1e-7,rtol=1e-4):raise ValueError('irregular ball within_epoch timebase')
        if abs((ballt[0]-et[0])-(source_tb[0]-source_te[0]))>1e-6:raise ValueError('epoch alignment offset changed')
        epoch_starts.append(offset)
        # Offset is a bookkeeping coordinate, not an inferred real-time gap.
        te[a:b]=et-et[0]+offset;tb[c:e]=ballt-et[0]+offset;offset+=(b-a)/fs
    info.update(source_clock_resets=len(er),epoch_durations_s=';'.join(str((b-a)/fs) for a,b in zip(eb[:-1],eb[1:])),time_coordinate='concatenated_epoch_index_seconds' if len(er) else 'source_seconds')
    start=max(te[0],tb[0]);start=np.ceil((start-te[0])*HZ)/HZ+te[0]
    end=min(te[-1]+1/fs,tb[-1])
    if limit:end=min(end,start+limit)
    nbin=int(np.floor((end-start)*HZ));starti=int(round((start-te[0])*fs));endi=starti+nbin*spb
    tc=start+(np.arange(nbin)+.5)/HZ
    if tc[-1]>tb[-1]:raise ValueError('lastbin would extrapolate ball')
    info.update(status='usable',reason='all_required_variables_regular_timebase',ephys_hz=fs,ball_hz=bs,available_ephys_s=len(te)/fs,analyzed_s=nbin/HZ,start_s=float(start),end_s=float(start+nbin/HZ),bins=nbin,author_spike_arrays='absent',neurons=';'.join(ns))
    ball={k:np.interp(tc,tb,d[k])*factor for k,factor in [('yaw',.000395/.000436),('fwd',.0051/.000436),('lat',.003/.000436)]}
    info['fwd_lat_raw_exact_equal_fraction']=float(np.mean(d['fwd']==d['lat']))
    stim=np.asarray(d['stim'])[starti:endi].reshape(nbin,spb)
    son=np.max(stim,axis=1)>2.5
    # Include smoothing support100ms before; exclude250ms after every stimulated bin.
    blocked=np.convolve(son.astype(np.int32),np.ones(36,dtype=np.int32),mode='full')[10:10+nbin]>0
    valid=~blocked;valid[:50]=False;valid[-50:]=False
    for boundary in epoch_starts[1:]:
        ix=int(round((boundary-start)*HZ));valid[max(0,ix-50):ix+50]=False
    for y in ball.values():valid &= np.isfinite(y)
    info.update(stim_bin_fraction=float(son.mean()),valid_no_stim_s=float(valid.sum()/HZ),stim_min=float(np.min(stim)),stim_max=float(np.max(stim)))
    chs=[];pairs=[];curves=[];sens=[];data={};plot_data={};spike_times={}
    for idx,lab in enumerate(ns):
        vv=np.asarray(d['ephys_'+('A' if idx==0 else 'B')])[starti:endi]
        if not np.isfinite(vv).all():
            chs.append({'fly':fly,'neuron':lab,'status':'excluded','reason':'nonfinite_voltage'});continue
        vm=ndimage.median_filter(np.median(vv.reshape(nbin,spb),axis=1),size=3,mode='nearest')
        original_voltage=np.asarray(d['ephys_'+('A' if idx==0 else 'B')])
        proc_full=np.empty_like(original_voltage,dtype=float);noise_parts=[]
        for ea,ebound in zip(eb[:-1],eb[1:]):
            pp,nn=mad_process(original_voltage[ea:ebound],fs);proc_full[ea:ebound]=pp;noise_parts.append(nn);del pp
        noise={k:float(np.mean([n[k] for n in noise_parts])) for k in noise_parts[0]}
        proc=proc_full[starti:endi];prom=5.75 if lab.startswith('a1') else 7.5
        peak,counts,fr,refract=extract_spikes(proc,fs,prom,spb)
        cm=valid & np.isfinite(vm)&np.isfinite(fr)
        base={'fly':fly,'neuron':lab,'type':'DNa01' if lab[:2]=='a1' else 'DNa02','side':'left' if lab[-1]=='l' else 'right','mat_channel':'ephys_'+('A' if idx==0 else 'B'),'status':'usable','spikes':int(len(peak)),'rate_mean_Hz':float(len(peak)/info['analyzed_s']),'rate_no_stim_mean_Hz':float(counts[cm].mean()*HZ),'fraction_ISI_under2ms':refract,'prominence':prom,'main_summary_eligible':fly!='a2_d_14','author_quality_flag':FLAGS.get(fly,''),**noise}
        for bk,yy in ball.items():
            mm,rr=metrics(fr,yy,cm,curve=bk=='yaw')
            base.update({bk+'_'+k:v for k,v in mm.items()})
            if rr is not None:curves.extend({'fly':fly,'signal':lab+'_rate','target':bk,'lag_ms':int(l*10),'r':float(r)} for l,r in zip(LAGS,rr))
        base['yaw_counts_r150']=corr(counts,ball['yaw'],cm,lag=15)
        base['yaw_vm_r150']=corr(vm,ball['yaw'],cm,lag=15)
        base['rate_vm_r0']=corr(fr,vm,cm)
        # Persistence is assessed within sequential thirds, not new independent flies.
        for j,inds in enumerate(np.array_split(np.arange(nbin),3)):
            sub=np.zeros(nbin,bool);sub[inds]=True
            base[f'yaw_r150_third{j+1}']=corr(fr,ball['yaw'],cm&sub,lag=15)
        chs.append(base)
        data[lab]={'fr':fr,'counts':counts,'vm':vm,'valid':cm}
        spike_times[lab]=peak/fs+start
        for mult in ([.75,1,1.25,1.5,2,2.5] if lab.startswith('a2') else [.75,1,1.25]):
            if mult==1:pks,cts,rrate,rf=peak,counts,fr,refract
            else:pks,cts,rrate,rf=extract_spikes(proc,fs,prom*mult,spb)
            sens.append({'fly':fly,'neuron':lab,'prominence_multiplier':mult,'spikes':int(len(pks)),'fraction_ISI_under2ms':rf,'yaw_r150':corr(rrate,ball['yaw'],cm,lag=15)})
        plot_data[lab]={'raw':vv[:20*fs: max(1,fs//2000)].copy(),'raw_t':te[starti:starti+20*fs:max(1,fs//2000)].copy(),'peaks_s':peak[peak<20*fs]/fs+start,'fr':fr[:20*HZ].copy(),'vm':vm[:20*HZ].copy()}
        del proc,proc_full
    if len(data)==2:
        a,b=[data[n] for n in ns];pm=a['valid']&b['valid']
        paired_kind='same_side_cross_type' if fly.startswith('a1_a2') else 'bilateral_same_type'
        mm,rr=metrics(a['fr'],b['fr'],pm)
        pairs.append({'fly':fly,'kind':paired_kind,'signal':ns[0]+'_rate','target':ns[1]+'_rate',**mm,'main_summary_eligible':fly!='a2_d_14'})
        curves.extend({'fly':fly,'signal':ns[0]+'_rate','target':ns[1]+'_rate','lag_ms':int(l*10),'r':float(r)} for l,r in zip(LAGS,rr))
        for kind,x in [('A_minus_B',a['fr']-b['fr']),('A_plus_B',a['fr']+b['fr'])]:
            mm,rr=metrics(x,ball['yaw'],pm)
            pairs.append({'fly':fly,'kind':paired_kind,'signal':kind,'target':'yaw',**mm,'main_summary_eligible':fly!='a2_d_14'})
            curves.extend({'fly':fly,'signal':kind,'target':'yaw','lag_ms':int(l*10),'r':float(r)} for l,r in zip(LAGS,rr))
    fig,axs=plt.subplots(len(plot_data)+2,1,figsize=(12,2.15*(len(plot_data)+2)),sharex=True)
    for ax,(lab,pl) in zip(axs,plot_data.items()):
        ax.plot(pl['raw_t'],pl['raw'],lw=.35,color='#7a8fa6',label=lab+' raw voltage')
        ax.plot(tc[:len(pl['vm'])],pl['vm'],lw=1,color='#15284c',label='Vm proxy')
        ax.scatter(pl['peaks_s'],np.interp(pl['peaks_s'],pl['raw_t'],pl['raw']),s=5,color='#e55f35',label='detected spikes')
        ax.set_ylabel('mV');ax.legend(loc='upper right',fontsize=8)
    for lab,pl in plot_data.items():axs[-2].plot(tc[:len(pl['fr'])],pl['fr'],label=lab)
    axs[-2].set_ylabel('Detected rate Hz');axs[-2].legend(fontsize=8)
    axs[-1].plot(tc[:20*HZ],ball['yaw'][:20*HZ],label='yaw: raw sign',color='#913a62')
    axs[-1].set_ylabel('yaw deg/s');axs[-1].set_xlabel('time s')
    for ax in axs:ax.grid(alpha=.15)
    fig.suptitle(fly+' | first20s fixed example | orange = current detection');fig.tight_layout();(B/'figures').mkdir(exist_ok=True);fig.savefig(B/'figures'/f'{fly}_first20s.png',dpi=130);plt.close(fig)
    # The entire aligned representation is small enough for parent independent checks.
    aligned={'time_s':tc,'source_time_s':np.interp(tc,te,source_te),'epoch_id':np.searchsorted(epoch_starts,tc,side='right')-1,'valid':valid,'stim_on':son,**ball}
    for lab,vals in data.items():
        for k,v in vals.items():aligned[lab+'_'+k]=v
    (B/'aligned').mkdir(exist_ok=True)
    np.savez_compressed(B/'aligned'/f'{fly}.npz',**aligned)
    (B/'spikes').mkdir(exist_ok=True)
    np.savez_compressed(B/'spikes'/f'{fly}.npz',**spike_times)
    info['processing_seconds']=time.time()-t0
    return info,chs,pairs,curves,sens
