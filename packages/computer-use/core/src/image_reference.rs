//! One bounded immutable reference decode. Current pointer frames never use it.
use std::{
    fs,
    io::{BufReader, Cursor, Read},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
};
type R<T> = Result<T, String>;
const MAX_PIXELS: usize = 16 * 1024 * 1024;
const MAX_ENCODED: usize = 4 * 1024 * 1024;
#[derive(Debug)]
pub(crate) struct Pixels {
    pub width: u32,
    pub height: u32,
    pub channels: usize,
    pub bytes: Vec<u8>,
}
#[derive(Clone, PartialEq, Eq)]
pub(crate) struct Key {
    pub session: String,
    pub epoch: u64,
    pub input_generation: u64,
    pub observation: String,
    pub path: PathBuf,
}
struct Entry {
    key: Key,
    revision: u64,
    encoded: Arc<[u8]>,
    pixels: Arc<Pixels>,
}
#[derive(Default)]
pub(crate) struct Cache {
    revision: AtomicU64,
    entry: Mutex<Option<Entry>>,
    #[cfg(test)]
    decodes: std::sync::atomic::AtomicUsize,
}
impl Cache {
    // Priority invalidation never waits on allocation, file I/O or a cache lock.
    pub fn invalidate(&self) {
        self.revision.fetch_add(1, Ordering::SeqCst);
        if let Ok(mut slot) = self.entry.try_lock() {
            slot.take();
        }
    }
    pub fn evict(&self, observation: &str) {
        let affected = self
            .entry
            .try_lock()
            .map(|slot| {
                slot.as_ref()
                    .is_some_and(|e| e.key.observation == observation)
            })
            .unwrap_or(true);
        if affected {
            self.invalidate();
        }
    }
    fn check(&self, check: &mut impl FnMut() -> R<()>) -> R<()> {
        check().inspect_err(|_| self.invalidate())
    }
    pub fn pixels(&self, key: Key, mut check: impl FnMut() -> R<()>) -> R<Arc<Pixels>> {
        self.check(&mut check)?;
        let revision = self.revision.load(Ordering::SeqCst);
        let mut encoded = Vec::new();
        fs::File::open(&key.path)
            .map_err(|e| format!("Guard image unavailable: {e}"))
            .and_then(|file| {
                file.take((MAX_ENCODED + 1) as u64)
                    .read_to_end(&mut encoded)
                    .map_err(|e| format!("Guard image unavailable: {e}"))
            })
            .inspect_err(|_| self.invalidate())?;
        self.check(&mut check)?;
        let prior = {
            let mut slot = self
                .entry
                .lock()
                .map_err(|_| "Reference decode cache poisoned")?;
            if slot.as_ref().is_some_and(|e| e.revision != revision) {
                slot.take();
            }
            slot.as_ref()
                .filter(|e| e.key == key)
                .map(|e| (e.encoded.clone(), e.pixels.clone()))
        };
        if let Some((original, pixels)) = prior {
            if encoded.as_slice() != original.as_ref() {
                self.invalidate();
                return Err("Prior capture artifact changed; fresh observation required".into());
            }
            self.check(&mut check)?;
            // Invalidation may race a read-only crop; a pointer caller still
            // rechecks its bound epoch/generation before capture and dispatch.
            return Ok(pixels);
        }
        #[cfg(test)]
        self.decodes.fetch_add(1, Ordering::SeqCst);
        let pixels = if encoded.len() <= MAX_ENCODED {
            decode(Cursor::new(&encoded))
        } else {
            // No new image refusal at the cache limit: keep the old decoder.
            self.invalidate();
            read_pixels(&key.path)
        }
        .inspect_err(|_| self.invalidate())?;
        self.check(&mut check)?;
        let pixels = Arc::new(pixels);
        if encoded.len() <= MAX_ENCODED && pixels.bytes.len() <= MAX_PIXELS {
            let mut slot = self
                .entry
                .lock()
                .map_err(|_| "Reference decode cache poisoned")?;
            if self.revision.load(Ordering::SeqCst) == revision {
                *slot = Some(Entry {
                    key,
                    revision,
                    encoded: encoded.into(),
                    pixels: pixels.clone(),
                });
            }
        } else {
            self.invalidate();
        }
        self.check(&mut check)?;
        Ok(pixels)
    }
    #[cfg(test)]
    pub fn retained_bytes(&self) -> usize {
        self.entry
            .lock()
            .unwrap()
            .as_ref()
            .map_or(0, |e| e.encoded.len() + e.pixels.bytes.len())
    }
    #[cfg(test)]
    pub fn decodes(&self) -> usize {
        self.decodes.load(Ordering::SeqCst)
    }
}
pub(crate) fn read_pixels(path: &Path) -> R<Pixels> {
    let file = fs::File::open(path).map_err(|e| format!("Guard image unavailable: {e}"))?;
    decode(BufReader::new(file))
}
fn decode(input: impl std::io::BufRead + std::io::Seek) -> R<Pixels> {
    let mut decoder = png::Decoder::new(input);
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = decoder
        .read_info()
        .map_err(|e| format!("Guard PNG decode failed: {e}"))?;
    let size = reader
        .output_buffer_size()
        .ok_or("Guard PNG size overflow")?;
    if size > 128 * 1024 * 1024 {
        return Err("Guard PNG exceeds 128MiB".into());
    }
    let mut bytes = vec![0; size];
    let info = reader
        .next_frame(&mut bytes)
        .map_err(|e| format!("Guard PNG pixels unavailable: {e}"))?;
    let channels = match info.color_type {
        png::ColorType::Rgb => 3,
        png::ColorType::Rgba => 4,
        png::ColorType::Grayscale => 1,
        png::ColorType::GrayscaleAlpha => 2,
        _ => return Err("Unsupported guard PNG color type".into()),
    };
    bytes.truncate(info.buffer_size());
    Ok(Pixels {
        width: info.width,
        height: info.height,
        channels,
        bytes,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicUsize;
    static SERIAL: AtomicUsize = AtomicUsize::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let dir = std::env::temp_dir().join(format!(
                "weasel-reference-cache-{}-{}",
                std::process::id(),
                SERIAL.fetch_add(1, Ordering::SeqCst)
            ));
            fs::create_dir(&dir).unwrap();
            Self(dir)
        }
        fn key(&self, name: &str) -> Key {
            Key {
                session: "offline-session".into(),
                epoch: 7,
                input_generation: 9,
                observation: name.into(),
                path: self.0.join(name),
            }
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    fn png(path: &Path, width: u32, height: u32, color: png::ColorType, data: &[u8]) {
        let mut encoder = png::Encoder::new(fs::File::create(path).unwrap(), width, height);
        encoder.set_color(color);
        encoder.set_depth(png::BitDepth::Eight);
        encoder.set_compression(png::Compression::Fast);
        encoder
            .write_header()
            .unwrap()
            .write_image_data(data)
            .unwrap();
    }
    #[test]
    fn equal_bytes_reuse_one_decode_for_all_supported_formats() {
        let f = Fixture::new();
        let cache = Cache::default();
        for (i, color, n) in [
            (0, png::ColorType::Rgb, 3),
            (1, png::ColorType::Rgba, 4),
            (2, png::ColorType::Grayscale, 1),
            (3, png::ColorType::GrayscaleAlpha, 2),
        ] {
            let key = f.key(&format!("{i}.png"));
            let data = vec![57; 8 * 5 * n];
            png(&key.path, 8, 5, color, &data);
            let a = cache.pixels(key.clone(), || Ok(())).unwrap();
            let b = cache.pixels(key, || Ok(())).unwrap();
            assert!(Arc::ptr_eq(&a, &b));
            assert_eq!(a.bytes, data);
            assert_eq!(a.channels, n);
            assert!(cache.retained_bytes() <= MAX_PIXELS + MAX_ENCODED);
        }
        assert_eq!(cache.decodes(), 4);
    }
    #[test]
    fn changed_equal_length_file_and_missing_artifact_never_hit() {
        let f = Fixture::new();
        let cache = Cache::default();
        let key = f.key("frame.png");
        png(&key.path, 8, 5, png::ColorType::Rgb, &[57; 120]);
        cache.pixels(key.clone(), || Ok(())).unwrap();
        let mut changed = fs::read(&key.path).unwrap();
        let n = changed.len();
        changed[n - 1] ^= 1;
        fs::write(&key.path, &changed).unwrap();
        assert!(cache
            .pixels(key.clone(), || Ok(()))
            .unwrap_err()
            .contains("artifact changed"));
        assert_eq!(cache.retained_bytes(), 0);
        png(&key.path, 8, 5, png::ColorType::Rgb, &[57; 120]);
        cache.pixels(key.clone(), || Ok(())).unwrap();
        fs::remove_file(&key.path).unwrap();
        assert!(cache
            .pixels(key, || Ok(()))
            .unwrap_err()
            .contains("unavailable"));
        assert_eq!(cache.retained_bytes(), 0);
    }
    #[test]
    fn different_path_and_binding_never_share_pixels() {
        let f = Fixture::new();
        let cache = Cache::default();
        let mut key = f.key("a.png");
        png(&key.path, 8, 5, png::ColorType::Rgb, &[57; 120]);
        let a = cache.pixels(key.clone(), || Ok(())).unwrap();
        let path = f.0.join("b.png");
        png(&path, 8, 5, png::ColorType::Rgb, &[93; 120]);
        key.path = path;
        let b = cache.pixels(key.clone(), || Ok(())).unwrap();
        assert!(!Arc::ptr_eq(&a, &b));
        assert_eq!(b.bytes, [93; 120]);
        for field in 0..4 {
            let prior = cache.pixels(key.clone(), || Ok(())).unwrap();
            match field {
                0 => key.session.push('x'),
                1 => key.epoch += 1,
                2 => key.input_generation += 1,
                _ => key.observation.push('x'),
            };
            let next = cache.pixels(key.clone(), || Ok(())).unwrap();
            assert!(!Arc::ptr_eq(&prior, &next));
        }
        assert_eq!(cache.decodes(), 6);
    }
    #[test]
    fn pixel_limit_uses_uncached_original_decode() {
        let f = Fixture::new();
        let cache = Cache::default();
        let key = f.key("large.png");
        let data = vec![25; 2100 * 2100 * 4];
        png(&key.path, 2100, 2100, png::ColorType::Rgba, &data);
        let a = cache.pixels(key.clone(), || Ok(())).unwrap();
        let b = cache.pixels(key, || Ok(())).unwrap();
        assert_eq!(a.bytes, data);
        assert!(!Arc::ptr_eq(&a, &b));
        assert_eq!(cache.retained_bytes(), 0);
        assert_eq!(cache.decodes(), 2);
    }
    #[test]
    fn compressed_limit_uses_uncached_original_decode() {
        let f = Fixture::new();
        let cache = Cache::default();
        let key = f.key("noisy.png");
        let mut data = vec![0; 1300 * 1200 * 3];
        let mut random = 123456789u32;
        for b in &mut data {
            random ^= random << 13;
            random ^= random >> 17;
            random ^= random << 5;
            *b = random as u8;
        }
        png(&key.path, 1300, 1200, png::ColorType::Rgb, &data);
        assert!(fs::metadata(&key.path).unwrap().len() > MAX_ENCODED as u64);
        let a = cache.pixels(key.clone(), || Ok(())).unwrap();
        let b = cache.pixels(key, || Ok(())).unwrap();
        assert_eq!(a.bytes, data);
        assert!(!Arc::ptr_eq(&a, &b));
        assert_eq!(cache.retained_bytes(), 0);
    }
    #[test]
    fn eviction_invalidation_and_cancel_remove_slot_without_waiting() {
        let f = Fixture::new();
        let cache = Cache::default();
        let key = f.key("a.png");
        png(&key.path, 8, 5, png::ColorType::Rgb, &[57; 120]);
        cache.pixels(key.clone(), || Ok(())).unwrap();
        cache.evict("unrelated");
        assert!(cache.retained_bytes() > 0);
        cache.evict(&key.observation);
        assert_eq!(cache.retained_bytes(), 0);
        cache.pixels(key.clone(), || Ok(())).unwrap();
        let slot = cache.entry.lock().unwrap();
        cache.invalidate();
        drop(slot);
        let previous = cache.decodes();
        cache.pixels(key.clone(), || Ok(())).unwrap();
        assert_eq!(cache.decodes(), previous + 1);
        assert!(cache
            .pixels(key, || Err("canceled".into()))
            .unwrap_err()
            .contains("canceled"));
        assert_eq!(cache.retained_bytes(), 0);
    }
    #[test]
    fn cancel_during_file_read_or_decode_does_not_retain_reference() {
        let f = Fixture::new();
        let cache = Cache::default();
        let key = f.key("a.png");
        png(&key.path, 8, 5, png::ColorType::Rgb, &[57; 120]);
        for stop_at in [2, 3, 4] {
            let mut calls = 0;
            assert!(cache
                .pixels(key.clone(), || {
                    calls += 1;
                    if calls == stop_at {
                        Err("deadline".into())
                    } else {
                        Ok(())
                    }
                })
                .is_err());
            assert_eq!(cache.retained_bytes(), 0);
        }
    }
}
