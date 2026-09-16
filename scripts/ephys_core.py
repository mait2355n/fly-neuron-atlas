#!/usr/bin/env python3
"""Voltage-analysis core adapted for this publication.
Call through reanalyze_ephys.py. Source-normalization algorithm uses
Wilson Lab MIT-licensed code; see ../licenses/Wilson-Lab-MIT.txt.
Paths are assigned by the caller. Source normalization is preserved from the
2026-09-15 research snapshot; validity and source-epoch boundaries are explicit.
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
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,default=cv,allow_nan=True)+'\n',encoding='utf-8')

def write_csv(path,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        w.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()} for row in rows)

def labels(fly):
    if fly.startswith('a1_a2_d'):return ['a2_l','a1_l']
    typ=fly[:2]
    return [typ+'_l',typ+'_r'] if '_d_' in fly else [typ+'_l']

def lagged_values(x,y,mx,my=None,lag=0,epochs=None):
    """Select finite paired observations without linking distinct source epochs."""
    if my is None:my=mx
    same=np.ones(max(0,len(x)-abs(lag)),dtype=bool)
    if epochs is not None and lag:
        same=epochs[:-abs(lag)]==epochs[abs(lag):]
    if lag>0:x,y,mx,my=x[:-lag],y[lag:],mx[:-lag],my[lag:]
    elif lag<0:x,y,mx,my=x[-lag:],y[:lag],mx[-lag:],my[:lag]
    m=mx & my & np.isfinite(x) & np.isfinite(y) & same
    return x[m],y[m]

def valid_lagged_count(x,y,mx,my=None,lag=15,epochs=None):
    return len(lagged_values(x,y,mx,my,lag,epochs)[0])

def corr(x,y,mx,my=None,lag=0,epochs=None):
    a,b=lagged_values(x,y,mx,my,lag,epochs)
    if len(a)<100:return np.nan
    if np.ptp(a)==0 or np.ptp(b)==0:return np.nan
    a=a-a.mean();b=b-b.mean()
    den=np.sqrt(np.sum(a*a)*np.sum(b*b))
    return float(np.sum(a*b)/den) if den>0 else np.nan

def metrics(x,y,m,curve=True,epochs=None):
    rr=np.array([corr(x,y,m,lag=int(l),epochs=epochs) for l in LAGS]) if curve else None
    shifts=[len(x)//3,2*len(x)//3]
    out={'r0':corr(x,y,m,epochs=epochs),'r150':corr(x,y,m,lag=15,epochs=epochs)}
    for i,k in enumerate(shifts):
        xx=np.roll(x,k);mm=np.roll(m,k)
        if epochs is not None:
            for eid in np.unique(epochs):
                ix=np.flatnonzero(epochs==eid);kk=(i+1)*len(ix)//3
                xx[ix]=np.roll(x[ix],kk);mm[ix]=np.roll(m[ix],kk)
        out['shift'+str(i+1)+'_r150']=corr(xx,y,mm,m,15,epochs=epochs)
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

def extract_spikes_by_epoch(proc,fs,prom,spb,epoch_bounds):
    """Detect and smooth independently; returned peaks index the concatenation."""
    peaks=[];counts=[];rates=[];violations=intervals=0
    for a,b in zip(epoch_bounds[:-1],epoch_bounds[1:]):
        if (b-a)%spb:raise ValueError('epoch selection must contain complete bins')
        pp,cc,rr,_=extract_spikes(proc[a:b],fs,prom,spb)
        peaks.append(pp+a);counts.append(cc);rates.append(rr)
        isi=np.diff(pp);violations+=int(np.count_nonzero(isi<.002*fs));intervals+=len(isi)
    return (np.concatenate(peaks),np.concatenate(counts),np.concatenate(rates),
            violations/intervals if intervals else np.nan)

def process_voltage_epochs(voltage,fs,prom,spb,epoch_bounds,starti=0,endi=None,normalizer=None):
    """Preserve source normalization while isolating all filters at clock resets.

    Bounds index the original voltage. Normalize each whole source epoch, then
    crop to the selected bins and apply detection, rate smoothing and Vm filtering
    within that epoch. Returned bounds and peaks index the selected concatenation.
    """
    if endi is None:endi=len(voltage)
    procs=[];vms=[];bounds=[0];noise_parts=[]
    for a,b in zip(epoch_bounds[:-1],epoch_bounds[1:]):
        lo=max(a,starti);hi=min(b,endi)
        if hi<=lo:continue
        if (hi-lo)%spb:raise ValueError('epoch selection must contain complete bins')
        source=np.asarray(voltage[a:b])
        if not np.isfinite(source).all():raise ValueError('nonfinite_voltage')
        pp,nn=(normalizer or mad_process)(source,fs);procs.append(pp[lo-a:hi-a]);noise_parts.append(nn)
        vv=source[lo-a:hi-a].reshape(-1,spb)
        vms.append(ndimage.median_filter(np.median(vv,axis=1),size=3,mode='nearest'))
        bounds.append(bounds[-1]+hi-lo)
    if not procs:raise ValueError('empty_voltage_selection')
    proc=np.concatenate(procs);bounds=np.asarray(bounds,dtype=int)
    peaks,counts,fr,refract=extract_spikes_by_epoch(proc,fs,prom,spb,bounds)
    noise={k:float(np.mean([n[k] for n in noise_parts])) for k in noise_parts[0]}
    return {'proc':proc,'peaks':peaks,'counts':counts,'fr':fr,'vm':np.concatenate(vms),
            'fraction_ISI_under2ms':refract,'noise':noise,'epoch_bounds':bounds}

def stimulus_validity(stim,epoch_id):
    """Any nonfinite sample makes its bin unknown, never known stimulus-off."""
    unknown=~np.isfinite(stim).all(axis=1)
    on=np.any(np.isfinite(stim)&(stim>2.5),axis=1)
    blocked=np.zeros(len(stim),bool)
    for eid in np.unique(epoch_id):
        ix=np.flatnonzero(epoch_id==eid)
        # 100 ms before and 250 ms after known-on OR unknown bins.
        bad=(on[ix]|unknown[ix]).astype(np.int32)
        blocked[ix]=np.convolve(bad,np.ones(36,dtype=np.int32),mode='full')[10:10+len(ix)]>0
    return on,unknown,blocked

def selftest():
    rng=np.random.default_rng(42);x=rng.normal(size=30000);y=np.zeros_like(x);y[15:]=x[:-15];m=np.ones(len(x),bool)
    rr=np.array([corr(x,y,m,lag=int(l)) for l in LAGS])
    assert LAGS[np.argmax(rr)]==15 and rr.max()>.999999
    assert corr(-x,y,m,lag=15)<-.999999
    spikes=np.array([0,39,40,80,99]);counts=np.bincount(spikes//40,minlength=3)
    assert counts.tolist()==[2,1,2] and counts.sum()==5
    return {'known_neural_lead_150ms':'pass','right_minus_left_sign':'pass','bin_count_conservation':'pass','no_formal_sample_pvalues':True}

def finalize_inventory(info,channels,pairs):
    """Keep processing completion, scientific availability and author flags apart."""
    expected=info['expected_channels'];expected_pairs=info['expected_pair_series']
    observed=[r['neuron'] for r in channels if r.get('metrics_computed',False)]
    observed_pairs=[r['signal']+'->'+r['target'] for r in pairs if r.get('metrics_computed',False)]
    good=[r['neuron'] for r in channels if r.get('numerical_valid',False)]
    good_pairs=[r['signal']+'->'+r['target'] for r in pairs if r.get('numerical_valid',False)]
    complete=observed==expected and observed_pairs==expected_pairs
    usable=complete and good==expected and good_pairs==expected_pairs
    status='usable' if usable else ('partial' if good or good_pairs else 'excluded')
    reasons=list(info.get('reasons',[]))
    if not complete:reasons.append('incomplete_expected_channel_or_pair_series')
    for row in channels+pairs:
        for reason in row.get('reasons',[]):
            if reason not in reasons:reasons.append(reason)
    if not usable and not reasons:reasons.append('required_correlations_not_numerically_valid')
    info.update(status=status,analysis_status=status,record_complete=complete,
                observed_channels=observed,numerically_valid_channels=good,
                observed_pair_series=observed_pairs,numerically_valid_pair_series=good_pairs,
                expected_channel_count=len(expected),observed_channel_count=len(observed),
                expected_pair_count=len(expected_pairs),observed_pair_count=len(observed_pairs),
                reasons=reasons,reason=';'.join(reasons) if reasons else 'all_required_outputs_numerically_valid')
    for row in channels+pairs:
        row['record_complete']=complete
        row['author_reference_eligible']=info['author_reference_eligible']
        row['main_summary_eligible']=bool(usable and row.get('numerical_valid',False) and info['author_reference_eligible'])

def numerical_validity(row,x,y,mask,epochs,prefix=''):
    row['n_valid_r150']=valid_lagged_count(x,y,mask,lag=15,epochs=epochs)
    reasons=[]
    if row['n_valid_r150']<100:reasons.append('fewer_than_100_valid_lag150_samples')
    if not all(np.isfinite(row.get(prefix+k,np.nan)) for k in ('r0','r150')):
        reasons.append('nonfinite_required_correlations')
    row.update(numerical_valid=not reasons,status='excluded' if reasons else 'usable',
               analysis_status='excluded' if reasons else 'usable',reasons=reasons,
               reason=';'.join(reasons) if reasons else 'required_correlations_numerically_valid',metrics_computed=True)

def run_file(entry,limit=None,normalizer=None):
    t0=time.time();f=entry['dataFile'];p=RAW/f['filename'];fly=entry['directoryLabel'].split('ephys_data_')[1]
    ns=labels(fly)
    expected_pairs=[ns[0]+'_rate->'+ns[1]+'_rate','A_minus_B->yaw','A_plus_B->yaw'] if len(ns)==2 else []
    info={'fly':fly,'file':f['filename'],'file_id':f['id'],'author_quality_flag':FLAGS.get(fly,''),
          'author_reference_eligible':fly!='a2_d_14','status':'excluded','analysis_status':'excluded',
          'processing_status':'not_processed','expected_channels':ns,'expected_pair_series':expected_pairs,'reasons':[]}
    def rejected(reason):
        info['reasons'].append(reason);finalize_inventory(info,[],[])
        info['processing_seconds']=time.time()-t0
        return info,[],[],[],[]
    receiptp=p.with_suffix(p.suffix+'.receipt.json')
    if not p.exists() or not receiptp.exists():return rejected('download_pending')
    rec=json.loads(receiptp.read_text(encoding='utf-8'))
    if rec.get('status')!='verified' or rec.get('md5')!=f['checksum']['value'] or p.stat().st_size!=f['filesize']:
        return rejected('source_receipt_or_size_invalid')
    info['source_md5_verified']=True
    structure=whosmat(p);info['mat_fields']=';'.join(x[0] for x in structure)
    d=loadmat(p,squeeze_me=True)
    info['processing_status']='completed'
    missing=[k for k in ('ephys_SR','ball_SR','t_ephys','t_ball','stim','yaw','fwd','lat') if k not in d]
    if missing:return rejected('missing_required_variables:'+','.join(missing))
    fs=int(d['ephys_SR']);bs=int(d['ball_SR']);spb=fs//HZ
    if fs<=0 or bs<=0 or fs%HZ:raise ValueError('ephys sample rate must be positive and divisible by100')
    source_te=np.asarray(d['t_ephys']).reshape(-1);source_tb=np.asarray(d['t_ball']).reshape(-1)
    if not len(source_te) or not len(source_tb):return rejected('empty_timebase')
    if len(np.asarray(d['stim']).reshape(-1))!=len(source_te):return rejected('stim_timebase_length_mismatch')
    if any(len(np.asarray(d[k]).reshape(-1))!=len(source_tb) for k in ('yaw','fwd','lat')):
        return rejected('ball_timebase_length_mismatch')
    dt=np.diff(source_te);bt=np.diff(source_tb)
    er=np.where(dt<=0)[0]+1;br=np.where(bt<=0)[0]+1
    eb=np.r_[0,er,len(source_te)];bb=np.r_[0,br,len(source_tb)]
    if len(eb)!=len(bb) or not np.allclose(eb/fs,bb/bs):raise ValueError('unmatched_ephys_ball_clock_resets')
    if np.any(eb%spb):raise ValueError('source_epoch_boundary_not_aligned_to_bins')
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
    if nbin<=0:return rejected('no_aligned_bins')
    tc=start+(np.arange(nbin)+.5)/HZ
    if tc[-1]>tb[-1]:raise ValueError('lastbin would extrapolate ball')
    info.update(ephys_hz=fs,ball_hz=bs,available_ephys_s=len(te)/fs,analyzed_s=nbin/HZ,start_s=float(start),end_s=float(start+nbin/HZ),bins=nbin,author_spike_arrays='absent',neurons=';'.join(ns))
    epoch_id=np.searchsorted(epoch_starts,tc,side='right')-1
    ball={k:np.empty(nbin) for k in ('yaw','fwd','lat')}
    source_time=np.empty(nbin)
    for eid,(ea,ee,ba,be) in enumerate(zip(eb[:-1],eb[1:],bb[:-1],bb[1:])):
        ix=np.flatnonzero(epoch_id==eid)
        if not len(ix):continue
        source_time[ix]=np.interp(tc[ix],te[ea:ee],source_te[ea:ee])
        for k,factor in [('yaw',.000395/.000436),('fwd',.0051/.000436),('lat',.003/.000436)]:
            ball[k][ix]=np.interp(tc[ix],tb[ba:be],d[k][ba:be],left=np.nan,right=np.nan)*factor
    info['fwd_lat_raw_exact_equal_fraction']=float(np.mean(d['fwd']==d['lat']))
    stim=np.asarray(d['stim'])[starti:endi].reshape(nbin,spb)
    son,stim_unknown,blocked=stimulus_validity(stim,epoch_id)
    valid=~blocked;valid[:50]=False;valid[-50:]=False
    for boundary in epoch_starts[1:]:
        ix=int(round((boundary-start)*HZ));valid[max(0,ix-50):ix+50]=False
    for y in ball.values():valid &= np.isfinite(y)
    finite_stim=stim[np.isfinite(stim)]
    info.update(stim_bin_fraction=float(son.mean()),stim_unknown_bin_fraction=float(stim_unknown.mean()),
                stim_unknown_bins=int(stim_unknown.sum()),valid_no_stim_s=float(valid.sum()/HZ),
                stim_min=float(finite_stim.min()) if finite_stim.size else np.nan,
                stim_max=float(finite_stim.max()) if finite_stim.size else np.nan)
    if not valid.any():info['reasons'].append('no_valid_unstimulated_bins')
    if stim_unknown.all():info['reasons'].append('all_stimulus_bins_unknown')
    chs=[];pairs=[];curves=[];sens=[];data={};plot_data={};spike_times={}
    for idx,lab in enumerate(ns):
        mat_channel='ephys_'+('A' if idx==0 else 'B');prom=5.75 if lab.startswith('a1') else 7.5
        reason=None
        original_voltage=np.asarray(d.get(mat_channel,[])).reshape(-1)
        if mat_channel not in d:reason='missing_voltage_channel'
        elif not len(original_voltage):reason='empty_voltage'
        elif len(original_voltage)!=len(te):reason='voltage_timebase_length_mismatch'
        elif not np.isfinite(original_voltage).all():reason='nonfinite_voltage'
        if not reason:
            try:processed=process_voltage_epochs(original_voltage,fs,prom,spb,eb,starti,endi,normalizer=normalizer)
            except ValueError as exc:reason='voltage_processing_failed:'+str(exc)
        if reason:
            chs.append({'fly':fly,'neuron':lab,'mat_channel':mat_channel,'status':'excluded','analysis_status':'excluded',
                        'reason':reason,'reasons':[reason],'numerical_valid':False,'metrics_computed':False,
                        'n_valid_r150':0,'main_summary_eligible':False,'author_quality_flag':FLAGS.get(fly,'')});continue
        vv=original_voltage[starti:endi]
        proc=processed['proc'];vm=processed['vm'];peak=processed['peaks'];counts=processed['counts'];fr=processed['fr']
        refract=processed['fraction_ISI_under2ms'];noise=processed['noise'];selected_bounds=processed['epoch_bounds']
        cm=valid & np.isfinite(vm)&np.isfinite(fr)
        base={'fly':fly,'neuron':lab,'type':'DNa01' if lab[:2]=='a1' else 'DNa02','side':'left' if lab[-1]=='l' else 'right','mat_channel':mat_channel,'spikes':int(len(peak)),'rate_mean_Hz':float(len(peak)/info['analyzed_s']),'rate_no_stim_mean_Hz':float(counts[cm].mean()*HZ) if cm.any() else np.nan,'fraction_ISI_under2ms':refract,'prominence':prom,'author_quality_flag':FLAGS.get(fly,''),**noise}
        for bk,yy in ball.items():
            mm,rr=metrics(fr,yy,cm,curve=bk=='yaw',epochs=epoch_id)
            base.update({bk+'_'+k:v for k,v in mm.items()})
            if rr is not None:curves.extend({'fly':fly,'signal':lab+'_rate','target':bk,'lag_ms':int(l*10),'r':float(r)} for l,r in zip(LAGS,rr))
        base['yaw_counts_r150']=corr(counts,ball['yaw'],cm,lag=15,epochs=epoch_id)
        base['yaw_vm_r150']=corr(vm,ball['yaw'],cm,lag=15,epochs=epoch_id)
        base['rate_vm_r0']=corr(fr,vm,cm,epochs=epoch_id)
        numerical_validity(base,fr,ball['yaw'],cm,epoch_id,prefix='yaw_')
        # Persistence is assessed within sequential thirds, not new independent flies.
        for j,inds in enumerate(np.array_split(np.arange(nbin),3)):
            sub=np.zeros(nbin,bool);sub[inds]=True
            base[f'yaw_r150_third{j+1}']=corr(fr,ball['yaw'],cm&sub,lag=15,epochs=epoch_id)
        chs.append(base)
        data[lab]={'fr':fr,'counts':counts,'vm':vm,'valid':cm}
        spike_times[lab]=peak/fs+start
        for mult in ([.75,1,1.25,1.5,2,2.5] if lab.startswith('a2') else [.75,1,1.25]):
            if mult==1:pks,cts,rrate,rf=peak,counts,fr,refract
            else:pks,cts,rrate,rf=extract_spikes_by_epoch(proc,fs,prom*mult,spb,selected_bounds)
            sens.append({'fly':fly,'neuron':lab,'prominence_multiplier':mult,'spikes':int(len(pks)),'fraction_ISI_under2ms':rf,'yaw_r150':corr(rrate,ball['yaw'],cm,lag=15,epochs=epoch_id)})
        plot_data[lab]={'raw':vv[:20*fs: max(1,fs//2000)].copy(),'raw_t':te[starti:min(endi,starti+20*fs):max(1,fs//2000)].copy(),'peaks_s':peak[peak<20*fs]/fs+start,'fr':fr[:20*HZ].copy(),'vm':vm[:20*HZ].copy()}
        del proc,processed
    if len(data)==2:
        a,b=[data[n] for n in ns];pm=a['valid']&b['valid']
        paired_kind='same_side_cross_type' if fly.startswith('a1_a2') else 'bilateral_same_type'
        mm,rr=metrics(a['fr'],b['fr'],pm,epochs=epoch_id)
        pair={'fly':fly,'kind':paired_kind,'signal':ns[0]+'_rate','target':ns[1]+'_rate',**mm}
        numerical_validity(pair,a['fr'],b['fr'],pm,epoch_id);pairs.append(pair)
        curves.extend({'fly':fly,'signal':ns[0]+'_rate','target':ns[1]+'_rate','lag_ms':int(l*10),'r':float(r)} for l,r in zip(LAGS,rr))
        for kind,x in [('A_minus_B',a['fr']-b['fr']),('A_plus_B',a['fr']+b['fr'])]:
            mm,rr=metrics(x,ball['yaw'],pm,epochs=epoch_id)
            pair={'fly':fly,'kind':paired_kind,'signal':kind,'target':'yaw',**mm}
            numerical_validity(pair,x,ball['yaw'],pm,epoch_id);pairs.append(pair)
            curves.extend({'fly':fly,'signal':kind,'target':'yaw','lag_ms':int(l*10),'r':float(r)} for l,r in zip(LAGS,rr))
    fig,axs=plt.subplots(len(plot_data)+2,1,figsize=(12,2.15*(len(plot_data)+2)),sharex=True)
    for ax,(lab,pl) in zip(axs,plot_data.items()):
        ax.plot(pl['raw_t'],pl['raw'],lw=.35,color='#7a8fa6',label=lab+' raw voltage')
        ax.plot(tc[:len(pl['vm'])],pl['vm'],lw=1,color='#15284c',label='Vm proxy')
        ax.scatter(pl['peaks_s'],np.interp(pl['peaks_s'],pl['raw_t'],pl['raw']),s=5,color='#e55f35',label='detected spikes')
        ax.set_ylabel('mV');ax.legend(loc='upper right',fontsize=8)
    for lab,pl in plot_data.items():axs[-2].plot(tc[:len(pl['fr'])],pl['fr'],label=lab)
    axs[-2].set_ylabel('Detected rate Hz')
    if plot_data:axs[-2].legend(fontsize=8)
    axs[-1].plot(tc[:20*HZ],ball['yaw'][:20*HZ],label='yaw: raw sign',color='#913a62')
    axs[-1].set_ylabel('yaw deg/s');axs[-1].set_xlabel('time s')
    for ax in axs:ax.grid(alpha=.15)
    fig.suptitle(fly+' | first20s fixed example | orange = current detection');fig.tight_layout();(B/'figures').mkdir(exist_ok=True);fig.savefig(B/'figures'/f'{fly}_first20s.png',dpi=130);plt.close(fig)
    # The entire aligned representation is small enough for parent independent checks.
    aligned={'time_s':tc,'source_time_s':source_time,'epoch_id':epoch_id,'valid':valid,'stim_on':son,'stim_unknown':stim_unknown,**ball}
    for lab,vals in data.items():
        for k,v in vals.items():aligned[lab+'_'+k]=v
    (B/'aligned').mkdir(exist_ok=True)
    np.savez_compressed(B/'aligned'/f'{fly}.npz',**aligned)
    (B/'spikes').mkdir(exist_ok=True)
    np.savez_compressed(B/'spikes'/f'{fly}.npz',**spike_times)
    finalize_inventory(info,chs,pairs)
    info['processing_seconds']=time.time()-t0
    return info,chs,pairs,curves,sens
