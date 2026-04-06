use std::env;
use std::fs;
use std::path::PathBuf;

use image::DynamicImage;
use xcap::Monitor;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let out_dir = env::args()
        .nth(1)
        .map(PathBuf::from)
        .or_else(|| env::var_os("XCAP_PROBE_OUT_DIR").map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from("xcap-probe-output"));

    fs::create_dir_all(&out_dir)?;

    let monitors = Monitor::all()?;
    println!("found_monitors={}", monitors.len());

    for monitor in monitors {
        let id = monitor.id().unwrap_or(0);
        let name = monitor.name().unwrap_or_default();
        let width = monitor.width().unwrap_or(0);
        let height = monitor.height().unwrap_or(0);
        let x = monitor.x().unwrap_or(0);
        let y = monitor.y().unwrap_or(0);
        let is_primary = monitor.is_primary().unwrap_or(false);

        println!(
            "monitor id={} name={:?} width={} height={} x={} y={} primary={}",
            id, name, width, height, x, y, is_primary
        );

        match monitor.capture_image() {
            Ok(image) => {
                let path = out_dir.join(format!("monitor-{id}.png"));
                DynamicImage::ImageRgba8(image).save(&path)?;
                println!("capture_ok id={} path={}", id, path.display());
            }
            Err(err) => {
                println!("capture_err id={} error={}", id, err);
            }
        }
    }

    Ok(())
}
