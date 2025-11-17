from prometheus_client import start_http_server, Gauge
import os
import re
import sys
import subprocess
import json
import logging

# Engine key compatibility helper (MTL/Xe vs legacy /0 keys)
# Returns first present value from candidate engine keys and coerces to float.
def eng_val(data, names, field):
    e = data.get("engines", {})
    for n in names:
        v = e.get(n, {}).get(field)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0



igpu_device_id = Gauge(
    "igpu_device_id", "Intel GPU device id"
)

igpu_engines_blitter_0_busy = Gauge(
    "igpu_engines_blitter_0_busy", "Blitter 0 busy utilisation %"
)
igpu_engines_blitter_0_sema = Gauge(
    "igpu_engines_blitter_0_sema", "Blitter 0 sema utilisation %"
)
igpu_engines_blitter_0_wait = Gauge(
    "igpu_engines_blitter_0_wait", "Blitter 0 wait utilisation %"
)

igpu_engines_render_3d_0_busy = Gauge(
    "igpu_engines_render_3d_0_busy", "Render 3D 0 busy utilisation %"
)
igpu_engines_render_3d_0_sema = Gauge(
    "igpu_engines_render_3d_0_sema", "Render 3D 0 sema utilisation %"
)
igpu_engines_render_3d_0_wait = Gauge(
    "igpu_engines_render_3d_0_wait", "Render 3D 0 wait utilisation %"
)

igpu_engines_video_0_busy = Gauge(
    "igpu_engines_video_0_busy", "Video 0 busy utilisation %"
)
igpu_engines_video_0_sema = Gauge(
    "igpu_engines_video_0_sema", "Video 0 sema utilisation %"
)
igpu_engines_video_0_wait = Gauge(
    "igpu_engines_video_0_wait", "Video 0 wait utilisation %"
)

igpu_engines_video_enhance_0_busy = Gauge(
    "igpu_engines_video_enhance_0_busy", "Video Enhance 0 busy utilisation %"
)
igpu_engines_video_enhance_0_sema = Gauge(
    "igpu_engines_video_enhance_0_sema", "Video Enhance 0 sema utilisation %"
)
igpu_engines_video_enhance_0_wait = Gauge(
    "igpu_engines_video_enhance_0_wait", "Video Enhance 0 wait utilisation %"
)

igpu_frequency_actual = Gauge("igpu_frequency_actual", "Frequency actual MHz")
igpu_frequency_requested = Gauge("igpu_frequency_requested", "Frequency requested MHz")

igpu_imc_bandwidth_reads = Gauge("igpu_imc_bandwidth_reads", "IMC reads MiB/s")
igpu_imc_bandwidth_writes = Gauge("igpu_imc_bandwidth_writes", "IMC writes MiB/s")

igpu_interrupts = Gauge("igpu_interrupts", "Interrupts/s")

igpu_period = Gauge("igpu_period", "Period ms")

igpu_power_gpu = Gauge("igpu_power_gpu", "GPU power W")
igpu_power_package = Gauge("igpu_power_package", "Package power W")

igpu_rc6 = Gauge("igpu_rc6", "RC6 %")

igpu_engines_busy_max = Gauge(
    "igpu_engines_busy_max", "Maximum busy utilisation % across all engines"
)



def update(data):
    # Resolve engine metrics across old/new key formats
    blit_busy = eng_val(data, ["Blitter/0", "Blitter"], "busy")
    blit_sema = eng_val(data, ["Blitter/0", "Blitter"], "sema")
    blit_wait = eng_val(data, ["Blitter/0", "Blitter"], "wait")
    r3d_busy = eng_val(data, ["Render/3D/0", "Render/3D"], "busy")
    r3d_sema = eng_val(data, ["Render/3D/0", "Render/3D"], "sema")
    r3d_wait = eng_val(data, ["Render/3D/0", "Render/3D"], "wait")
    vid_busy = eng_val(data, ["Video/0", "Video"], "busy")
    vid_sema = eng_val(data, ["Video/0", "Video"], "sema")
    vid_wait = eng_val(data, ["Video/0", "Video"], "wait")
    ven_busy = eng_val(data, ["VideoEnhance/0", "VideoEnhance"], "busy")
    ven_sema = eng_val(data, ["VideoEnhance/0", "VideoEnhance"], "sema")
    ven_wait = eng_val(data, ["VideoEnhance/0", "VideoEnhance"], "wait")

    igpu_engines_blitter_0_busy.set(blit_busy)
    igpu_engines_blitter_0_sema.set(blit_sema)
    igpu_engines_blitter_0_wait.set(blit_wait)

    igpu_engines_render_3d_0_busy.set(r3d_busy)
    igpu_engines_render_3d_0_sema.set(r3d_sema)
    igpu_engines_render_3d_0_wait.set(r3d_wait)

    igpu_engines_video_0_busy.set(vid_busy)
    igpu_engines_video_0_sema.set(vid_sema)
    igpu_engines_video_0_wait.set(vid_wait)

    igpu_engines_video_enhance_0_busy.set(ven_busy)
    igpu_engines_video_enhance_0_sema.set(ven_sema)
    igpu_engines_video_enhance_0_wait.set(ven_wait)

    igpu_frequency_actual.set(data.get("frequency", {}).get("actual", 0))
    igpu_frequency_requested.set(data.get("frequency", {}).get("requested", 0))
    igpu_imc_bandwidth_reads.set(data.get("imc-bandwidth", {}).get("reads", 0))
    igpu_imc_bandwidth_writes.set(data.get("imc-bandwidth", {}).get("writes", 0))
    igpu_interrupts.set(data.get("interrupts", {}).get("count", 0))
    igpu_period.set(data.get("period", {}).get("duration", 0))
    igpu_power_gpu.set(data.get("power", {}).get("GPU", 0))
    igpu_power_package.set(data.get("power", {}).get("Package", 0))

    # RC6 percent (0-100)
    try:
        rc6_value = float(data.get("rc6", {}).get("value", 0) or 0)
    except Exception:
        rc6_value = 0.0
    igpu_rc6.set(rc6_value)

    # Optional fallback: derive non-idle percent from RC6 for targets with zero busy
    try:
        fb = os.getenv("FALLBACK_FROM_RC6", "0").lower() in ("1","true","yes","on")
        targets = [t.strip() for t in os.getenv("FALLBACK_TARGETS", "Video").split(',') if t.strip()]
    except Exception:
        fb = False
        targets = []
    if fb:
        active = max(0.0, 100.0 - rc6_value)
        if "Video" in targets and vid_busy <= 0:
            igpu_engines_video_0_busy.set(active)
        if ("Render/3D" in targets or "Render" in targets) and r3d_busy <= 0:
            igpu_engines_render_3d_0_busy.set(active)
        if "Blitter" in targets and blit_busy <= 0:
            igpu_engines_blitter_0_busy.set(active)
        if "VideoEnhance" in targets and ven_busy <= 0:
            igpu_engines_video_enhance_0_busy.set(active)

    # Calculate maximum busy utilization across all engines
    busy_values = [
        blit_busy,
        r3d_busy,
        vid_busy,
        ven_busy,
    ]
    igpu_engines_busy_max.set(max(busy_values))


if __name__ == "__main__":
    if os.getenv("DEBUG", False):
        debug = logging.DEBUG
    else:
        debug = logging.INFO
    logging.basicConfig(format="%(asctime)s - %(message)s", level=debug)

    start_http_server(8080)

    period = os.getenv("REFRESH_PERIOD_MS", 1000)

    cmd = "intel_gpu_top -L"
    out, _ = subprocess.Popen(
        cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ).communicate()
    out = out.decode()

    m = re.search(r"(?:device0|device)=(\w+)", out) or re.search(r"pci:vendor=\w+,device=(\w+)", out)
    device_id = int("0x" + m.group(1), 16) if m else 0

    igpu_device_id.set(device_id)

    cmd = "intel_gpu_top -J -s {}".format(int(period))
    process = subprocess.Popen(
        cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    logging.info("Started " + cmd)
    # Robust streaming JSON parse: bracket-depth framing
    buf = ''
    depth = 0
    started = False
    while True:
        chunk = process.stdout.read(4096)
        if not chunk:
            break
        for ch in chunk.decode('utf-8', 'ignore'):
            if not started:
                if ch == '{':
                    started = True
                    depth = 1
                    buf = '{'
            else:
                buf += ch
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            data = json.loads(buf)
                            logging.debug(data)
                            update(data)
                        except Exception:
                            pass
                        buf = ''
                        started = False
    process.kill()

    if process.returncode != 0:
        logging.error("Error: " + process.stderr.read().decode("utf-8"))

    logging.info("Finished")
