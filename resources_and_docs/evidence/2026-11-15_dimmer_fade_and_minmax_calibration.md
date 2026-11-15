# Dimmer fade calibration & `dimMin`/`dimMax` scaling (2026-11-15)

**Target:** `10.10.1.40-1` (`Bureau [40.1.2]`, IP0300PoE fw 5.4) via Gateway `1.8.1` (`192.168.1.3:8080`).  
**Method:** Fixed-exposure SDR video (`AE/AF Lock`, 1080p 25 fps) analyzed with `ffprobe` (`fps=10,scale=64:36,signalstats` → `YAVG` luma per 0.1 s).

---

## 1. Fade duration calibration (`dimMin = 20`, `dimMax = 70`)

Sweep executed at `09:47:01`–`09:48:58` (`module_confirmed: true` on all 10 commands, `confirm_ms` 12–45 ms).  
Baseline luma: `OFF` ≈ `325–365`, `DIM 50%` ≈ `743`, `ON 100%` ≈ `754`.

| Action | `fade` | Total time from command | Initial plateau / dead time | Visible ramp |
|---|---:|---|---|---|
| `ON 0→100%` | `0` | `< 0.2 s` | — | instant |
| `OFF 100→0%` | `0` | `< 0.2 s` | — | instant |
| `ON 0→100%` | `10` | `~2.1 s` | `~0.5 s` | `~1.6 s` |
| `OFF 100→0%` | `10` | `~5.5 s` | `~1.7 s` (at full brightness) | `~3.8 s` |
| `ON 0→100%` | `30` | `~4.0 s` | `~0.8 s` | `~3.2 s` |
| `OFF 100→0%` | `30` | `~9.0 s` | `~3.1 s` (at full brightness) | `~5.9 s` |
| `DIM 0→50%` | `30` | `~3.9 s` | `~0.8 s` | `~3.1 s` |
| `OFF 50→0%` | `30` | `~5.8 s` | `~0.4 s` | `~5.4 s` |
| `ON 0→100%` | `60` | `~6.7 s` | `~1.2 s` | `~5.5 s` |
| `OFF 100→0%` | `60` | `~13.9 s` | `~5.4 s` (at full brightness) | `~8.5 s` |

### Key findings (fade)
1. **Not proportional to `0.2 s × fade`:** Full `100→0%` duration (`fade > 0`) fits **`duration_s ≈ 3.8 + 0.17 × fade`** (`10 → 5.5 s`, `30 → 9.0 s`, `60 → 13.9 s`).
2. **Rate, not fixed total duration:** `OFF 50→0%` (`~5.8 s`) is significantly shorter than `OFF 100→0%` (`~9.0 s`) at `fade = 30`.
3. **No automatic Soft AAN (15%) / Soft UIT (70%) jump on `S`/`C` with `fade > 0`:** The module ramps continuously across the full range. Because this LED already reaches ~97% brightness (`743` vs `754`) at 50% command, `OFF 100→0%` stays visually flat for `1.7 s` / `3.1 s` / `5.4 s` before dimming visibly.

---

## 2. `dimMin` / `dimMax` behavior (`dimMin = 0`, `dimMax = 25`)

Step test executed at `10:24:37`–`10:24:55` (`fade = 0`, 3 s per step, `IMG_8058.MOV`):

| Video time | Command | Mean luma (`YAVG`) | Physical lamp |
|---|---|---:|---|
| `0.0–1.4 s` | *(pre-test `ON 100%`)* | `612` | ON |
| `1.5 s` | `OFF 0%` | `565` | OFF |
| `3.5 s` | `DIM 10%` | `566` | OFF |
| `6.6 s` | `DIM 25%` | `568` | OFF |
| `9.7 s` | `DIM 50%` | `569` | OFF |
| `12.7 s` | `DIM 75%` | `569` | OFF |
| `16.2 s` | `ON 100%` | `633` | **ON** |
| `18.8 s` | `OFF 0%` | `566` | OFF |

### Key finding (`dimMin` / `dimMax`)
- **The IP0300PoE scales `1–100%` into `[dimMin .. dimMax]`** (it does **not** clamp at `dimMax`). If it had clamped at `25%`, `DIM 25%`, `50%`, `75%`, and `ON 100%` would all have produced the same output (`633`). Instead, only `ON 100%` crossed the LED ignition threshold.
