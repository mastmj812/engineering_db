"""BOX step 21b — the PREREGISTRATION §10 harness command, run unchanged, with the raw `mid_r2` months OBSERVED.

    python -m scripts.box_step21b_harness <the scripts.box_acceptance arguments, verbatim>

Why: the frozen harness keeps uptime-free monthly arrays for box_v2 only (`months_<tag>.npz`), while §5's D106 guard (the D92
g(48) of the median location) and §7's D107 water (ratio on raw mid_r2 oil, D108) need mid_r2's months. This module calls
`scripts.box_acceptance.main(argv)` exactly as §10 does; the only addition is a pass-through wrapper on
`box.analog.monthly_arrays_v2` (it returns the very object the frozen code computed) that copies the mid_r2 oil / gas months of
each fold's SCORED view (the first call per cutoff; the second is the F(k) training sample) into
`<out>/months_mid_r2.npz` (keys <yyyy>_api10 / <yyyy>_oil / <yyyy>_gas). Nothing the harness computes or writes changes: the
step-21b driver proves it by running one group (MID_WCC) both ways and comparing every output (decompressed content;
the build timestamps aside).
F(k) is not copied: at a scored horizon k it is pred_mid_r2_<s><k> / cumsum(months)[k-1], identical for every well of a cutoff
(box/step21b.f_from_view checks that before anything is scored).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

from box import acceptance as ac
from box import analog as an
from box import step21 as st

_orig_arrays = an.monthly_arrays_v2
_orig_add = ac.add_analog_predictions_v2
_CAP: dict[str, dict[str, np.ndarray]] = {}
_CUR: dict[str, Any] = {}


def _add(conn: Any, view: Any, f: Any, cutoff: Any, *args: Any, **kw: Any) -> Any:
    _CUR.update({"cutoff": str(cutoff), "api10": view["api10"].astype(str).to_numpy(), "calls": 0})
    return _orig_add(conn, view, f, cutoff, *args, **kw)


def _arrays(preds: Any, k: int, variants: Any = an.VARIANTS_V2) -> Any:
    out = _orig_arrays(preds, k, variants)
    if _CUR and _CUR["calls"] == 0 and st.RAW in out:  # the scored view (pv); the next call is the training sample (pt)
        ids = np.array([str(p["api10"]) for p in preds])
        if not np.array_equal(ids, _CUR["api10"]):
            raise RuntimeError(f"{_CUR['cutoff']}: captured predictions are not in view order")
        y = _CUR["cutoff"][:4]
        _CAP[y] = {"api10": ids, "oil": out[st.RAW]["oil"].copy(), "gas": out[st.RAW]["gas"].copy()}
    if _CUR:
        _CUR["calls"] += 1
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = Path(argv[argv.index("--out") + 1])
    an.monthly_arrays_v2 = _arrays  # looked up as an attribute at call time by box/acceptance
    ac.add_analog_predictions_v2 = _add
    from scripts import box_acceptance

    rc = box_acceptance.main(argv)
    np.savez_compressed(out / "months_mid_r2.npz", **{f"{y}_{k}": v for y, d in sorted(_CAP.items()) for k, v in d.items()})
    print(f"captured mid_r2 months for cutoffs {sorted(_CAP)} -> {out / 'months_mid_r2.npz'}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
