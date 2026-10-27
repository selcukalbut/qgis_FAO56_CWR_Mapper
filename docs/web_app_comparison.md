# Eklenti – Sulama Programlama web uygulaması karşılaştırması

v0.1 kabul ölçütü: "bir parselde web uygulamasıyla karşılaştırma tablosu hazır".
Tarih: 27 Ekim 2026 · Eklenti v0.0.12 · NASA POWER API v2.10.1 (MERRA2, SYN1DEG, POWER)

## Kurulum

- **Web uygulaması:** `sulama-ders.html` (NASA POWER kipi). Hesap kodu, siteden
  kaldırılmadan önceki son sürümle (`835d193^`) birebir aynı: `sulamaEto`,
  `sulamaKc`, `sulamaFetchPower`, bitki listesi. Uygulamanın **kendi JavaScript
  kodu** Chrome'da başsız (puppeteer) çalıştırıldı.
- **Eklenti:** Aynı konum, ekim tarihi ve sezon; web uygulamasının Kc ve evre
  süreleri kullanıcı girdisi olarak verildi. Böylece fark yalnızca yöntemden gelir.
- **Konum:** Tekirdağ, 40,98 K – 27,51 D; POWER hücre yüksekliği 98,23 m (ikisinde de).
- **Etkili yağış:** Web uygulamasında "yağışı düş" açık.

| Durum | Kc ini / mid / end | Evreler (gün) | Sezon |
|---|---|---|---|
| Domates | 0,60 / 1,15 / 0,80 | 30 / 40 / 40 / 25 | 01.05 – 12.09.2025 (135 gün) |
| Mısır (dane) | 0,30 / 1,20 / 0,60 | 20 / 35 / 40 / 30 | 20.04 – 22.08.2025 (125 gün) |

## Sonuçlar (mm, sezon toplamı)

| | ETo | ETc | P | Pe | Net sulama |
|---|---|---|---|---|---|
| Domates – web uygulaması | 827,8 | 785,4 | 73,0 | 64,5 | **720,9** |
| Domates – eklenti | 874,5 | 831,8 | 73,0 | 58,4 | **773,4** |
| Mısır – web uygulaması | 754,2 | 703,6 | 67,6 | 60,3 | **643,3** |
| Mısır – eklenti | 796,0 | 741,2 | 67,6 | 54,1 | **689,6** |

Eklenti, net sulamayı domateste %7,3 (+52,5 mm), mısırda %7,2 (+46,3 mm) yüksek buluyor.
Yağış (P) iki programda aynı.

## Farkın kaynakları

**1. Kod doğruluğu: fark yok.** Eklenti gerçek buhar basıncını web uygulaması gibi
ortalama bağıl nemden (FAO-56 Eq. 19) hesapladığında, 135 günün her birinde günlük
ETo farkı en çok 1,8 × 10⁻¹⁵ mm (makine duyarlığı). İki uygulamanın Penman-Monteith
zinciri (Δ, γ, Ra, Rso, Rnl, Rn) birebir aynı sonucu veriyor.

**2. Gerçek buhar basıncı (eₐ) yöntemi: farkın büyük bölümü.**

| | Web uygulaması | Eklenti |
|---|---|---|
| eₐ | RH2M ile Eq. 19 (RHmean) | T2MDEW ile Eq. 14 (çiy noktası) |
| Günlük ETo farkı | – | ortalama +0,34 mm, en çok +0,84 mm |

FAO-56 (Bölüm 3) Eq. 19 için "Equations 17 or 18'den daha az tercih edilir"
diyor; Eq. 14 ise eₐ'yı doğrudan veriyor. Ayrıca POWER'ın RH2M değeri saatlik
nemlerin günlük ortalamasıdır, FAO-56'nın tanımladığı (RHmax + RHmin)/2 değil.
Eklentinin çiy noktası tercihi bu nedenle korunuyor; daha önce Open-Meteo'nun
kendi çiy noktası girdileriyle yapılan kontrol de bu yolu doğrulamıştı (%0,1).

**3. Kc gün sayımı: ihmal edilebilir.** Web uygulaması ekim gününü 0. gün sayıp
Kc_ini'yi Lini + 1 gün uyguluyor; eklenti FAO-56 Eq. 66'daki gibi 1. günden sayıyor.
Etkisi: domates +1,9 mm, mısır +0,4 mm.

**4. Etkili yağış ve net sulama dönemi.**

| | Web uygulaması | Eklenti |
|---|---|---|
| Pe | USDA SCS aylık formülü, **sezon toplamına** uygulanmış | 0,80 × P, dekad bazında |
| Net sulama | max(0, ΣETc − Pe), sezon bütünü | max(0, ΣETc − ΣPe), her dekad için |

SCS formülü aylık toplamlar için tanımlı; sezon toplamına uygulanması bir
basitleştirme (kodda da böyle not edilmiş). Etkisi: domates +6,1 mm, mısır +8,7 mm.

### Ayrıştırma (eklenti – web)

| | Domates | Mısır |
|---|---|---|
| eₐ yöntemi (ETc üzerinden) | +44,5 | +37,2 |
| Kc gün sayımı | +1,9 | +0,4 |
| Pe ve net sulama dönemi | +6,1 | +8,7 |
| **Toplam** | **+52,5** | **+46,3** |

## Sonuç

- İki uygulamanın FAO-56 Penman-Monteith hesabı aynı girdilerle birebir aynı sonucu veriyor.
- Net sulamadaki yaklaşık %7'lik fark yöntem seçimlerinden geliyor, en çok eₐ'dan.
  Eklentinin seçimleri (çiy noktası, Eq. 66 gün sayımı, dekad bazında Pe) FAO-56'ya daha yakın.
- Web uygulaması ileride yeniden yayımlanırsa üç öneri:
  1. eₐ için T2MDEW (Eq. 14) kullanılmalı.
  2. Kc günü 1'den sayılmalı.
  3. SCS aylık toplamlara uygulanmalı ya da sabit oran seçeneği eklenmeli.

## Yeniden üretme

```bash
# web uygulamasının klasöründen (puppeteer-core orada kurulu)
NODE_PATH=$PWD/node_modules node ../tools/validation/run_web_app.js "$PWD/sulama-ders.html" web.json \
  '[{"name":"tomato","lat":40.98,"lon":27.51,"crop":"tomato","plant":"2025-05-01","start":"2025-05-01","end":"2025-09-12"},
    {"name":"maize","lat":40.98,"lon":27.51,"crop":"maize","plant":"2025-04-20","start":"2025-04-20","end":"2025-08-22"}]'
python3 ../tools/validation/compare_web_app.py web.json result.json
```
