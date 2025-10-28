#!/usr/bin/env python3
# updated_dengetv54_auto_discovery.py
"""Tam otomatik discovery pipeline ve M3U üretici.
- Çoklu pasif kaynak (crt.sh, certspotter, rapiddns scraping)
- dengetv sayfalarını hem HTML regex ile hem Playwright (opsiyonel) ile render ederek tarama
- concurrency limit, retry/backoff, cache ve logging
- domains.txt (opsiyonel) -> öncelik verir
"""

import os
import re
import json
import time
import asyncio
import random
import logging
from datetime import datetime
from typing import List, Set, Optional
from urllib.parse import quote_plus
from httpx import AsyncClient, RequestError

# ---------------- CONFIG ----------------
CACHE_FILE = "cache.json"
CACHE_TTL_SECONDS = 12 * 60 * 60  # 12 saat default
CONCURRENCY = 20
REQUEST_TIMEOUT = 8.0
PLAYWRIGHT_ENABLED = True  # Eğer ortamda playwright kuruluysa True bırak
BRUTE_FORCE_ONLY_IF_EMPTY = True  # Eğer diğer yöntemler boşsa brute-force çalışsın
MANUAL_DOMAINS_FILE = "domains.txt"  # varsa öncelikle bu listeden dener
LOG_FILE = "dengetv_auto.log"

# candidate discovery params
DENGETV_START = 67
DENGETV_END = 200
DENGETV_MAX_PAGES = 40

# brute-force params
COMMON_SUBS = ["cdn","media","stream","live","player","video","kodiaq","tible","kodi"]
TLDs = ["sbs", "xyz", "fun", "cam", "live"]

# ----------------------------------------

# logging setup
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console.setFormatter(formatter)
logging.getLogger().addHandler(console)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
]

def _load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        logging.warning("Cache yüklenemedi: %s", e)
        return {}

def _save_cache(data: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error("Cache kaydedilemedi: %s", e)

def load_manual_domains() -> List[str]:
    if not os.path.exists(MANUAL_DOMAINS_FILE):
        return []
    try:
        with open(MANUAL_DOMAINS_FILE, "r", encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    except Exception as e:
        logging.warning("domains.txt yüklenemedi: %s", e)
        return []

async def _get_with_retries(client: AsyncClient, url: str, attempts: int = 2, timeout: float = REQUEST_TIMEOUT):
    backoff = 0.6
    for i in range(attempts):
        try:
            r = await client.get(url, timeout=timeout, headers={"User-Agent": random.choice(USER_AGENTS)})
            return r
        except Exception as e:
            logging.debug("GET hata (%s) %s -> %s", i, url, e)
            await asyncio.sleep(backoff)
            backoff *= 1.9
    return None

class AutoDiscovery:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(CONCURRENCY)

    async def query_crtsh(self, pattern="zirvedesin") -> Set[str]:
        """crt.sh public JSON sorgusu"""
        q = quote_plus(f"%{pattern}%")
        url = f"https://crt.sh/?q={q}&output=json"
        found = set()
        async with AsyncClient(timeout=20) as client:
            r = await _get_with_retries(client, url, attempts=2)
            if not r or r.status_code != 200:
                logging.info("crt.sh boş veya erişilemedi.")
                return set()
            try:
                entries = r.json()
            except Exception as e:
                logging.info("crt.sh JSON parse hatası: %s", e)
                return set()
        for e in entries if isinstance(entries, list) else []:
            nv = e.get("name_value", "")
            for line in str(nv).splitlines():
                candidate = line.strip().lstrip("*.")
                if "zirvedesin" in candidate and any(candidate.endswith("." + t) for t in TLDs + ["sbs"]):
                    found.add(candidate)
        logging.info("crt.sh ile bulunan: %d", len(found))
        return found

    async def query_certspotter(self, domain="zirvedesin.sbs") -> Set[str]:
        """Certspotter public API (rate-limited olabilir)"""
        url = f"https://api.certspotter.com/v1/issuances?domain={domain}&include_subdomains=true&expand=dns_names"
        found = set()
        async with AsyncClient(timeout=20) as client:
            r = await _get_with_retries(client, url, attempts=2)
            if not r or r.status_code != 200:
                logging.info("certspotter boş veya erişilemedi.")
                return set()
            try:
                data = r.json()
            except Exception as e:
                logging.info("certspotter JSON parse hatası: %s", e)
                return set()
        for e in data if isinstance(data, list) else []:
            for name in e.get("dns_names", []):
                candidate = str(name).lstrip("*.")
                if "zirvedesin" in candidate:
                    found.add(candidate)
        logging.info("certspotter ile bulunan: %d", len(found))
        return found

    async def query_rapiddns_search(self, q="zirvedesin") -> Set[str]:
        """Basit rapiddns.io HTML scraping (public arama sayfası) - eğer public sayfa değişirse bozulur."""
        url = f"https://rapiddns.io/search?search={quote_plus(q)}&full=1"
        found = set()
        async with AsyncClient(timeout=15) as client:
            r = await _get_with_retries(client, url, attempts=2, timeout=15)
            if not r or r.status_code != 200:
                logging.info("rapiddns boş veya erişilemedi.")
                return set()
            text = r.text
        # basit host extraction
        for m in re.findall(r'([a-z0-9\-\_\.]+zirvedesin[0-9]*\.[a-z]{2,6})', text, flags=re.I):
            found.add(m.lstrip("*."))
        logging.info("rapiddns ile bulunan: %d", len(found))
        return found

    async def extract_from_dengetv_pages(self, start=DENGETV_START, end=DENGETV_END, max_pages=DENGETV_MAX_PAGES) -> Set[str]:
        """dengetvXX.live sayfalarını tarar; Playwright varsa render edip JS ile çıkan url'leri de yakalar."""
        found = set()
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        async with AsyncClient(timeout=10) as client:
            count = 0
            for i in range(start, end+1):
                url = f"https://dengetv{i}.live/"
                try:
                    r = await _get_with_retries(client, url, attempts=1, timeout=8)
                    if not r or r.status_code != 200:
                        continue
                    text = r.text or ""
                    # İlk seviye regex (host-only)
                    for match in re.findall(r'([a-z0-9\-\_\.]+zirvedesin[0-9]*\.[a-z]{2,6})', text, flags=re.IGNORECASE):
                        found.add(match.lstrip("*."))
                    # Daha spesifik url pattern'leri
                    for match in re.findall(r'https?://[a-z0-9\-\_\.]+zirvedesin[0-9]*\.[a-z]{2,6}[:/][^\s"\']*', text, flags=re.IGNORECASE):
                        host = re.sub(r'^https?://', '', match).split('/')[0].lstrip("*.")
                        found.add(host)
                    count += 1
                    if count >= max_pages:
                        break
                except Exception:
                    continue

        # Playwright fallback: sayfa render edilince JS ile gelen embed'leri yakala
        if PLAYWRIGHT_ENABLED:
            try:
                from playwright.async_api import async_playwright
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
                    page = await browser.new_page()
                    count = 0
                    for i in range(start, end+1):
                        url = f"https://dengetv{i}.live/"
                        try:
                            await page.goto(url, timeout=15000)
                            content = await page.content()
                            # regex benzeri tarama
                            for m in re.findall(r'https?://[a-z0-9\-\_\.]+zirvedesin[0-9]*\.[a-z]{2,6}[:/][^\s"\']*', content, flags=re.I):
                                host = re.sub(r'^https?://', '', m).split('/')[0].lstrip("*.")
                                found.add(host)
                            count += 1
                            if count >= max_pages:
                                break
                        except Exception:
                            continue
                    await browser.close()
            except Exception as e:
                logging.info("Playwright çalıştırılamadı veya hata: %s", e)

        logging.info("dengetv sayfalarından bulunan: %d", len(found))
        return found

    def generate_bruteforce_candidates(self) -> Set[str]:
        found = set()
        for sub in COMMON_SUBS:
            for tld in TLDs:
                for n in range(10, 100):
                    found.add(f"{sub}.zirvedesin{n}.{tld}")
                    found.add(f"{sub}.zirvedesin{n}.sbs")
        logging.info("bruteforce candidate sayısı: %d", len(found))
        return found

    async def validate_host(self, client: AsyncClient, host: str, path: str = "/yayinzirve.m3u8") -> Optional[str]:
        """Host'u test eder; başarılıysa base url döner (https://..../)"""
        url = f"https://{host}{path}"
        try:
            r = await client.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": random.choice(USER_AGENTS)})
            if r.status_code == 200 and r.text and r.text.strip():
                # küçük bir sanity check: içerikte m3u8 veya #EXTM3U gibi marker olabilir
                if "EXTM3U" in r.text or ".m3u8" in r.text or "#EXTINF" in r.text:
                    logging.info("Doğrulandı: %s", host)
                    return f"https://{host}/"
                # bazı sunucular sadece index atıyor; yine kabul et
                return f"https://{host}/"
        except RequestError:
            return None
        except Exception:
            return None
        return None

    async def validate_hosts_concurrent(self, hosts: List[str]) -> Optional[str]:
        """Concurrent validate (semaphore ile) - dönen ilk çalışan host'u return eder."""
        async with AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            async def _check(h):
                async with self.semaphore:
                    try:
                        return await self.validate_host(client, h)
                    except Exception:
                        return None

            tasks = [asyncio.create_task(_check(h)) for h in hosts]
            # as_completed ile ilk bulunanı al
            for coro in asyncio.as_completed(tasks):
                res = await coro
                if isinstance(res, str) and res:
                    # cancel remaining
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    return res
        return None

    async def discover_base(self) -> str:
        # cache check
        cache = _load_cache()
        now_ts = time.time()
        if cache.get("base_stream_url") and now_ts - cache.get("base_ts", 0) < CACHE_TTL_SECONDS:
            logging.info("Cache'den base alındı: %s", cache["base_stream_url"])
            return cache["base_stream_url"]

        candidates = set()

        # 1) manual domains (yüksek öncelik)
        manual = load_manual_domains()
        for m in manual:
            candidates.add(m)

        # 2) crt.sh
        try:
            crt = await self.query_crtsh("zirvedesin")
            candidates.update(crt)
        except Exception as e:
            logging.info("crt.sh sorgu hatası: %s", e)

        # 3) certspotter
        try:
            cs = await self.query_certspotter("zirvedesin.sbs")
            candidates.update(cs)
        except Exception as e:
            logging.info("certspotter hata: %s", e)

        # 4) rapiddns scraping
        try:
            rpd = await self.query_rapiddns_search("zirvedesin")
            candidates.update(rpd)
        except Exception as e:
            logging.info("rapiddns hata: %s", e)

        # 5) dengetv page scraping (+ playwright)
        try:
            dpg = await self.extract_from_dengetv_pages(start=DENGETV_START, end=DENGETV_END, max_pages=DENGETV_MAX_PAGES)
            candidates.update(dpg)
        except Exception as e:
            logging.info("dengetv extract hata: %s", e)

        # 6) bruteforce (yalnızca diğerleri boşsa veya explicit istenirse)
        if (not candidates and BRUTE_FORCE_ONLY_IF_EMPTY) or (not BRUTE_FORCE_ONLY_IF_EMPTY and True):
            bf = self.generate_bruteforce_candidates()
            candidates.update(bf)

        # normalize
        candidates = sorted(set([c.strip().lstrip("*.") for c in candidates if c and isinstance(c, str)]))
        logging.info("Toplam candidate sayısı: %d", len(candidates))

        # validate concurrently
        if candidates:
            valid = await self.validate_hosts_concurrent(candidates)
            if valid:
                cache.update({"base_stream_url": valid, "base_ts": now_ts, "candidates": candidates})
                _save_cache(cache)
                logging.info("✅ Bulundu ve cache'lendi: %s", valid)
                return valid

        # fallback default
        default = "https://kodiaq.zirvedesin24.sbs/"
        cache.update({"base_stream_url": default, "base_ts": now_ts, "candidates": candidates})
        _save_cache(cache)
        logging.warning("Hiçbiri çalışmadı, varsayılan kullanılıyor: %s", default)
        return default

# ---------------- M3U üretici (kendi orijinal kodundan adapte) ----------------
class Dengetv54Manager:
    def __init__(self):
        # orijinal channel list
        self.channel_files = {
            1: "yayinzirve.m3u8", 2: "yayin1.m3u8", 3: "yayininat.m3u8", 4: "yayinb2.m3u8",
            5: "yayinb3.m3u8", 6: "yayinb4.m3u8", 7: "yayinb5.m3u8", 8: "yayinbm1.m3u8",
            9: "yayinbm2.m3u8", 10: "yayinss.m3u8", 11: "yayinss2.m3u8", 13: "yayint1.m3u8",
            14: "yayint2.m3u8", 15: "yayint3.m3u8", 16: "yayinsmarts.m3u8", 17: "yayinsms2.m3u8",
            18: "yayintrtspor.m3u8", 19: "yayintrtspor2.m3u8", 20: "yayintrt1.m3u8",
            21: "yayinas.m3u8", 22: "yayinatv.m3u8", 23: "yayintv8.m3u8", 24: "yayintv85.m3u8",
            25: "yayinf1.m3u8", 26: "yayinnbatv.m3u8", 27: "yayineu1.m3u8", 28: "yayineu2.m3u8",
            29: "yayinex1.m3u8", 30: "yayinex2.m3u8", 31: "yayinex3.m3u8", 32: "yayinex4.m3u8",
            33: "yayinex5.m3u8", 34: "yayinex6.m3u8", 35: "yayinex7.m3u8", 36: "yayinex8.m3u8"
        }
        self.base_stream_url = None
        self.dengetv_url = None
        self.auto = AutoDiscovery()

    async def find_working_dengetv(self, start=67, end=200):
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        async with AsyncClient(timeout=8) as client:
            for i in range(start, end+1):
                url = f"https://dengetv{i}.live/"
                try:
                    r = await client.get(url, headers=headers, timeout=6)
                    if r.status_code == 200 and r.text and "m3u8" in r.text:
                        logging.info("Dengetv domain bulundu -> %s", url)
                        return url
                except Exception:
                    continue
        logging.warning("Dengetv domain bulunamadı, varsayılan kullanılıyor.")
        return "https://dengetv67.live/"

    async def calistir(self):
        # discovery
        self.base_stream_url = await self.auto.discover_base()
        self.dengetv_url = await self.find_working_dengetv()

        m3u = [
            "#EXTM3U",
            f"# Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"# Base URL: {self.base_stream_url}",
            f"# Source dengetv: {self.dengetv_url}"
        ]

        for _, file_name in self.channel_files.items():
            channel_name = re.sub(r'(\d+)', r' \1', file_name.replace(".m3u8", "")).title()
            m3u.append(f'#EXTINF:-1 group-title="Dengetv54",{channel_name}')
            m3u.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0')
            m3u.append(f'#EXTVLCOPT:http-referrer={self.dengetv_url}')
            m3u.append(f'{self.base_stream_url}{file_name}')

        # xplatin.m3u ekle (orijinal davranış)
        try:
            async with AsyncClient(timeout=10) as client:
                r = await client.get("https://raw.githubusercontent.com/smtv62/smtv/refs/heads/main/xplatin.m3u")
                if r.status_code == 200 and r.text:
                    m3u.append("\n# --- Xplatin M3U Başlangıcı ---")
                    m3u.append(r.text.strip())
                    m3u.append("# --- Xplatin M3U Sonu ---\n")
                else:
                    logging.warning("xplatin.m3u indirilemedi, HTTP: %s", getattr(r, "status_code", None))
        except Exception as e:
            logging.warning("xplatin.m3u indirme hatası: %s", e)

        os.makedirs("output", exist_ok=True)
        output_path = "output/dengetv54.m3u"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(m3u))

        logging.info("✅ M3U dosyası güncellendi → %s", output_path)
        return "\n".join(m3u)

# --------------- CLI ---------------
if __name__ == "__main__":
    mgr = Dengetv54Manager()
    try:
        asyncio.run(mgr.calistir())
    except KeyboardInterrupt:
        logging.info("Kullanıcı iptal etti.")
