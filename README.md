# 🛰️ Dengetv54 Otomatik M3U Güncelleme Botu

Bu repo, **dengetv54** kaynaklı canlı yayın akışlarını (M3U) otomatik olarak keşfeder ve günceller.  
Bot, `GitHub Actions` üzerinden **her 2 saatte bir** çalışarak:

1. Güncel stream domainlerini bulur (crt.sh, certspotter, dengetv sayfaları, vb.)
2. Çalışan kaynakları doğrular
3. `output/dengetv54.m3u` dosyasını oluşturur
4. Repo’ya commit eder

## Kurulum (manuel test etmek istersen)

```bash
git clone https://github.com/<kullanici>/dengetv54-auto.git
cd dengetv54-auto
pip install -r requirements.txt
python src/dengetv54_auto.py
```

Oluşan M3U dosyası:  
`output/dengetv54.m3u`

## Otomatik Güncelleme

Repo, GitHub Actions ile her 2 saatte bir çalışır.  
İstersen manuel olarak “Run workflow” butonuna basabilirsin.

## Lisans

MIT
