Mock tool result for `calibrate_dimmer`:

- `status`: returns dimmer channels (`device_id`, `module_ip`, `channel`, `uitgang`, `dim_min`, `dim_max`, `dim_gamma`, `default_fade`).
- `sweep`: with `confirmed=false` previews camera setup, duration, and temporary linear mode; with `confirmed=true` runs sync pulse + dimmer steps and writes `sweep_log_path`.
- `analyze`: extracts `10 Hz` luma (`YAVG`) from `video_path` via `ffprobe` and recommends `dim_min`, `dim_max`, and `dim_gamma`.
- `apply`: with `confirmed=false` previews exact changes; with `confirmed=true` writes module `dimMin`/`dimMax` (keeping `descr` and `gr`) and patches gateway `dim_gamma`/`default_fade`.
