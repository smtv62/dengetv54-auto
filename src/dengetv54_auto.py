# --- REPLACE validate_host with this improved version ---
async def validate_host(self, client: AsyncClient, host: str, paths: list = None) -> Optional[str]:
    """Daha güçlü host doğrulama:
    - https + http dener
    - birden fazla path dener (default /yayinzirve.m3u8 + örnek channel dosyaları + index)
    - önce HEAD deneyip, ardından GET ile sanity check
    """
    if not host:
        return None

    # normalize
    host = host.strip().lstrip("*.")
    if paths is None:
        # temel path'ler + birkaç alternatif
        sample_files = [
            "/yayinzirve.m3u8",
            "/yayin1.m3u8",
            "/index.m3u8",
            "/playlist.m3u8",
        ]
        # eğer manager alanında channel_files varsa birkaç örnek ekle
        try:
            sample_files.extend(list(getattr(self, "channel_files", {}).values())[:4])
        except Exception:
            pass
        paths = sample_files

    schemes = ["https://", "http://"]
    for scheme in schemes:
        for p in paths:
            url = f"{scheme}{host}{p}"
            try:
                # önce HEAD isteği (hız)
                r = await client.head(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": random.choice(USER_AGENTS)}, follow_redirects=True)
            except Exception:
                r = None
            # fallback GET if HEAD not allowed or returned non-200
            if not r or r.status_code not in (200, 206, 301, 302):
                try:
                    r = await client.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": random.choice(USER_AGENTS)}, follow_redirects=True)
                except Exception:
                    r = None
            if r and r.status_code in (200, 206):
                text = ""
                try:
                    # kısa sanity: body olabilir veya content-type m3u
                    ct = r.headers.get("content-type", "")
                    if "application/vnd.apple.mpegurl" in ct or "audio/mpegurl" in ct or ".m3u8" in ct or r.text:
                        text = (r.text or "")[:4000]
                except Exception:
                    text = ""
                # içerikte m3u8 marker veya kanal dosya isimleri varsa kabul et
                if text and ("EXTM3U" in text or ".m3u8" in text or "#EXTINF" in text):
                    logging.info("Doğrulandı: %s via %s (path=%s)", host, scheme.rstrip('://'), p)
                    return f"{scheme}{host}/"
                # eğer HEAD 200 ama gövde yoksa da kabul edebiliriz (bazı indexler)
                if r.request and r.status_code == 200:
                    logging.info("Doğrulandı (200): %s via %s (path=%s) - content-type: %s", host, scheme.rstrip('://'), p, r.headers.get("content-type"))
                    return f"{scheme}{host}/"
    return None

# --- REPLACE discover_base with this more aggressive workflow ---
async def discover_base(self) -> str:
    cache = _load_cache()
    now_ts = time.time()

    # Eğer cache'de base varsa ve TTL geçmemişse al
    if cache.get("base_stream_url") and now_ts - cache.get("base_ts", 0) < CACHE_TTL_SECONDS:
        base = cache["base_stream_url"]
        # Eğer base cached default ise ve candidate listesi daha önce boş kaldıysa
        # hemen yeniden denemek için kısa TTL uygulayalım (prevent permanent default lock).
        if base and "kodiaq.zirvedesin24.sbs" in base and cache.get("candidates"):
            logging.info("Cache'de default bulundu ama candidates mevcut; tekrar deneme atlanıyor.")
            return base
        if base and "kodiaq.zirvedesin24.sbs" in base and not cache.get("candidates"):
            # Default cache'lenmiş ama candidates boştu: kısa TTL ile yeniden dene
            if now_ts - cache.get("base_ts", 0) < 300:  # 5 dakika
                logging.info("Kısa TTL içinde varsayılan görüldü, kullanılıyor: %s", base)
                return base
            logging.info("Varsayılan önbelleği görüldü, ancak candidates yok — yeniden discovery başlatılıyor.")
            # düşür cache ve devam (daha agresif dene)
            cache.pop("base_stream_url", None)
            cache.pop("base_ts", None)
            _save_cache(cache)

    candidates = set()

    # manual list
    manual = load_manual_domains()
    candidates.update(manual)

    # crt.sh
    try:
        crt = await self.query_crtsh("zirvedesin")
        candidates.update(crt)
    except Exception as e:
        logging.info("crt.sh sorgu hatası: %s", e)

    # certspotter
    try:
        cs = await self.query_certspotter("zirvedesin.sbs")
        candidates.update(cs)
    except Exception as e:
        logging.info("certspotter hata: %s", e)

    # rapiddns
    try:
        rpd = await self.query_rapiddns_search("zirvedesin")
        candidates.update(rpd)
    except Exception as e:
        logging.info("rapiddns hata: %s", e)

    # dengetv pages
    try:
        dpg = await self.extract_from_dengetv_pages(start=DENGETV_START, end=DENGETV_END, max_pages=DENGETV_MAX_PAGES)
        candidates.update(dpg)
    except Exception as e:
        logging.info("dengetv extract hata: %s", e)

    # normalize
    candidates = sorted(set([c.strip().lstrip("*.") for c in candidates if c and isinstance(c, str)]))
    logging.info("Toplam candidate sayısı (ilk tur): %d", len(candidates))

    # Eğer hiç candidate yoksa bruteforce + http brute-force ile genişlet
    if not candidates:
        logging.info("Candidates boş - bruteforce genişletiliyor.")
        bf = self.generate_bruteforce_candidates()
        candidates.update(bf)
        # ayrıca http versiyonlarını deneyebilmek için tlds farklı varyasyon
        http_bf = set()
        for c in list(bf)[:400]:  # tümünü değil, ilk 400'ünü dene (performans)
            http_bf.add(c)
            # varyasyonlar: remove number suffix or swap tld to sbs
            http_bf.add(c.replace(".xyz", ".sbs").replace(".fun", ".sbs"))
        candidates.update(http_bf)

    logging.info("Toplam candidate sayısı (son): %d", len(candidates))

    # concurrent validate - burada paths paramı ile channel dosyalarını da gönder
    if candidates:
        async with AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            # validate_hosts_concurrent kullanabiliriz ama burada biraz daha kontrollü davranalım
            # ki hem https hem http path testleri doğru yapılsın
            for h in candidates:
                try:
                    valid = await self.validate_host(client, h)
                    if valid:
                        cache.update({"base_stream_url": valid, "base_ts": now_ts, "candidates": list(candidates)})
                        _save_cache(cache)
                        logging.info("✅ Bulundu ve cache'lendi: %s", valid)
                        return valid
                except Exception:
                    continue

    # fallback: default (ama cache'e kalıcı yazma - kısa TTL)
    default = "https://kodiaq.zirvedesin24.sbs/"
    cache.update({"base_stream_url": default, "base_ts": now_ts, "candidates": list(candidates)})
    _save_cache(cache)
    logging.warning("Hiçbiri çalışmadı, varsayılan kullanılıyor: %s", default)
    return default
