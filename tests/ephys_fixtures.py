"""Small, artificial MATLAB inputs; these do not model biological ground truth."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import savemat


def synthetic_record(root, case="finite_control", fly="a2_d_08", seconds=21, fs=1000):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(8127)
    t = np.arange(seconds * fs) / fs
    a, b = rng.normal(0, .08, (2, len(t)))
    shape = np.array([.1, .4, 1.5, 4., 1.5, .4, .1])
    for start, stride, voltage in ((151, 131, a), (281, 173, b)):
        for peak in range(start, len(t) - 7, stride):
            voltage[peak:peak + 7] += shape
    stim = np.zeros(len(t))
    if case == "all_voltage_nan": a[:] = b[:] = np.nan
    elif case == "one_voltage_nan": b[:] = np.nan
    elif case == "all_stim_nan": stim[:] = np.nan
    elif case == "all_stim_on": stim[:] = 5.
    elif case == "some_stim_nan": stim[5 * fs:6 * fs] = np.nan
    elif case == "empty_voltage": a = b = np.empty(0)
    tb = np.arange(seconds * 100) / 100
    d = {"ephys_SR": fs, "ball_SR": 100, "t_ephys": t, "t_ball": tb,
         "ephys_A": a, "ephys_B": b, "stim": stim,
         "yaw": rng.normal(size=len(tb)), "fwd": rng.normal(size=len(tb)),
         "lat": rng.normal(size=len(tb))}
    if case == "clock_reset":
        d["t_ephys"][len(t) // 2:] -= seconds / 2
        d["t_ball"][len(tb) // 2:] -= seconds / 2
    elif case == "constant_yaw": d["yaw"][:] = 1.
    elif case == "missing_voltage": del d["ephys_B"]
    elif case == "missing_yaw": del d["yaw"]
    p = root / (fly + ".mat")
    savemat(p, d)
    md5 = hashlib.md5(p.read_bytes()).hexdigest()
    p.with_suffix(".mat.receipt.json").write_text(
        json.dumps({"status": "verified", "md5": md5}) + "\n", encoding="utf-8")
    return {"directoryLabel": "/ephys_data_" + fly,
            "dataFile": {"filename": p.name, "id": 1, "filesize": p.stat().st_size,
                         "checksum": {"value": md5}}}


def cross_epoch_prominence(fs=1000):
    """A peak cannot descend far enough on its right within its source epoch."""
    first = np.interp(np.arange(10 * fs), [0, 8.9 * fs, 9 * fs, 10 * fs - 1], [0., 0., 10., 8.])
    second = np.zeros(10 * fs)
    return np.r_[first, second], np.array([0, 10 * fs, 20 * fs])
