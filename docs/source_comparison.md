# İklim kaynaklarının karşılaştırılması: NASA POWER ve Open-Meteo (Tekirdağ, 2024)

Bu belge eklentinin iki ızgara iklim kaynağını – NASA POWER ve Open-Meteo
ERA5-Seamless – örnek parseller üzerinde karşılaştırır ve üç etkili yağış
yönteminin (sabit oran 0,8; USDA SCS CROPWAT biçimi; USDA SCS NEH 623) net
sulama ihtiyacına etkisini gösterir. Bütün sayılar eklentinin Processing
algoritmasıyla üretildi; yeniden üretmek için aşağıdaki komutlara bakın.

## Kurulum

- **Parseller:** `sample_data/tekirdag_fields.gpkg` içindeki dört parsel
  (Tekirdağ'ın yaklaşık 5 km batısı, birbirine 500 m içinde). Ekim tarihleri
  bir yıl geri alındı (mısır 20.04.2024, ayçiçeği 15.04.2024, domates
  01.05.2024, kışlık buğday 01.11.2023); bitki ve Tablo 11 bölgeleri aynı.
- **Yıl:** 2024. Karşılaştırmaya alınan istasyon kaydı (aşağıda) 24 Ağustos
  2025'te kesildiği için 2025 sezonu yerine tam 2024 sezonu kullanıldı.
- **NASA POWER:** günlük nokta API'si, topluluk AG; ızgara hücresi yüksekliği
  98 m.
- **Open-Meteo:** Historical Weather API, ERA5-Seamless; nokta yüksekliği 49 m
  (90 m DEM). ETo'yu eklenti kendisi hesaplıyor (10 m rüzgâr Denklem 47 ile
  2 m'ye çevrildi).
- **Net sulama:** dekad bazında (varsayılan), uygulama randımanı yok.
- Aylık girdiler Parsel C'nin içindeki noktada (40,973 K, 27,494 D).

### Sezon toplamları (mm)

| Parsel | Sezon | ETo POWER | ETo Open-Meteo | P POWER | P Open-Meteo |
|---|---|---:|---:|---:|---:|
| Field A (Mısır) | 2024-04-20 – 2024-09-16 | 875 | 795 | 106 | 159 |
| Field B (Ayçiçeği) | 2024-04-15 – 2024-08-22 | 765 | 710 | 89 | 121 |
| Field C (Domates) | 2024-05-01 – 2024-09-22 | 870 | 788 | 72 | 118 |
| Field D (Kışlık buğday) | 2023-11-01 – 2024-06-27 | 606 | 613 | 531 | 526 |

### Etkili yağış ve net sulama (mm)

| Parsel | Pe yöntemi | Pe POWER | Pe Open-Meteo | NIR POWER | NIR Open-Meteo |
|---|---|---:|---:|---:|---:|
| Field A | Fixed 0.8 | 85 | 128 | 745 | 650 |
|  | USDA SCS (CROPWAT) | 83 | 119 | 739 | 641 |
|  | USDA SCS (NEH 623, D = 75 mm) | 53 | 72 | 748 | 652 |
| Field B | Fixed 0.8 | 71 | 97 | 638 | 573 |
|  | USDA SCS (CROPWAT) | 79 | 98 | 633 | 568 |
|  | USDA SCS (NEH 623, D = 75 mm) | 47 | 58 | 640 | 573 |
| Field C | Fixed 0.8 | 58 | 94 | 783 | 662 |
|  | USDA SCS (CROPWAT) | 68 | 106 | 772 | 650 |
|  | USDA SCS (NEH 623, D = 75 mm) | 52 | 84 | 788 | 673 |
| Field D | Fixed 0.8 | 425 | 421 | 350 | 315 |
|  | USDA SCS (CROPWAT) | 416 | 425 | 339 | 305 |
|  | USDA SCS (NEH 623, D = 75 mm) | 182 | 217 | 360 | 333 |

### Aylık girdiler, Parsel C noktası

| Ay | Kaynak | Tmax °C | Tmin °C | Td °C | u2 m/s | Rs MJ/m²/gün | ETo mm | P mm |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2024-04 | POWER | 20,0 | 10,6 | 10,7 | 3,0 | 18,6 | 96 | 47 |
|  | Open-Meteo | 19,5 | 11,5 | 10,3 | 2,7 | 18,8 | 99 | 74 |
| 2024-05 | POWER | 21,4 | 11,6 | 11,5 | 2,9 | 22,2 | 124 | 31 |
|  | Open-Meteo | 20,4 | 12,1 | 11,4 | 2,7 | 22,0 | 119 | 28 |
| 2024-06 | POWER | 31,6 | 19,3 | 16,3 | 3,1 | 28,6 | 207 | 4 |
|  | Open-Meteo | 29,9 | 19,9 | 16,8 | 2,9 | 27,7 | 193 | 13 |
| 2024-07 | POWER | 33,7 | 22,0 | 17,3 | 3,6 | 26,3 | 236 | 8 |
|  | Open-Meteo | 32,0 | 22,8 | 18,6 | 3,4 | 25,5 | 212 | 12 |
| 2024-08 | POWER | 33,1 | 21,5 | 17,4 | 3,3 | 24,1 | 206 | 5 |
|  | Open-Meteo | 30,9 | 22,0 | 18,2 | 3,1 | 22,6 | 183 | 8 |
| 2024-09 | POWER | 28,6 | 19,1 | 16,3 | 2,7 | 17,0 | 127 | 40 |
|  | Open-Meteo | 25,9 | 18,7 | 16,7 | 2,5 | 15,5 | 106 | 66 |
| 2024-10 | POWER | 22,8 | 12,8 | 11,6 | 3,1 | 13,8 | 89 | 4 |
|  | Open-Meteo | 21,2 | 13,3 | 11,3 | 2,8 | 12,9 | 81 | 7 |

Yükseklik (m): POWER 98, Open-Meteo 49

## Bulgular

1. **Sıcak sezon ETo'su POWER'da %7–11 daha yüksek.** Mısır, ayçiçeği ve
   domatesin sezon ETo'su POWER ile 765–875 mm, Open-Meteo ile 710–795 mm
   (domates: 870 ve 788 mm, fark %10,5). Fark Haziran–Eylül'de toplanıyor:
   POWER'ın Tmax'ı 1,7–2,7 °C, Rs'si 0,8–1,5 MJ/m²/gün, u2'si 0,2 m/s daha
   yüksek. POWER'ın meteoroloji hücresi 0,5° × 0,625°, radyasyon hücresi 1° × 1°
   ve iç kesimlerin karasal günlük sıcaklık aralığını taşıyor (domates sezonu
   ortalaması Tmax − Tmin: POWER 11,0 °C, Open-Meteo 8,7 °C); ERA5-Land'in
   0,1° ızgarası kıyıya daha yakın.
2. **Kış sezonunda kaynaklar uyuşuyor.** Kışlık buğdayın ETo'su (606 ve
   613 mm) ve yağışı (531 ve 526 mm) %1,2 içinde.
3. **Yaz yağışı kaynaklar arasında belirgin farklı.** Sıcak sezon yağışı
   POWER'da 72–106 mm, Open-Meteo'da 118–159 mm. Mutlak fark net sulamada
   doğrudan yer alıyor (sabit oranla domateste 36 mm Pe farkı); bu kadar kurak
   bir sezonda yağış küçük olduğundan NIR farkının çoğu ETo'dan geliyor.
4. **Net sulama:** sıcak sezon bitkilerinde POWER, Open-Meteo'dan 65–121 mm
   (%11–18) daha yüksek NIR veriyor; buğdayda fark 35 mm.
5. **Etkili yağış yöntemleri:**
   - USDA SCS (CROPWAT) küçük dekad yağışlarında yağışın %85–100'ünü etkili
     sayıyor (30 mm'lik bir dekadda %86), büyüklerde daha azını. Yaz
     bitkilerinde sezon Pe'si sabit orandan −9 ile +12 mm farklı; Pe'nin
     ihtiyaçlı dekadlarda daha yüksek kalması nedeniyle NIR 5–12 mm daha düşük.
   - NEH 623 Pe'yi yağışla ve dekadın ETc'siyle sınırlıyor ve D = 75 mm'de
     küçük yağışlara düşük etki veriyor; yaz bitkilerinde Pe sabit orandan
     %10–44 düşük, NIR −1 ile +11 mm farklı.
   - Kışlık buğdayda NEH 623 en büyük farkı yaratıyor: kışın ETc düşük olduğu
     için Pe yaklaşık 530 mm yağışın yalnız 182–217 mm'si (sabit oran: 421–425 mm). Bu
     NIR'ı yalnız 10–18 mm artırıyor, çünkü kış dekadlarında ihtiyaç zaten
     yağışla karşılanıyor ve fazla yağış eklentide (toprak su dengesi olmadan)
     sonraki dekadlara aktarılmıyor.

## Yorum ve sınırlılıklar

- Bu karşılaştırma tek nokta ve tek yıl; kaynaklardan hangisinin daha doğru
  olduğunu göstermez. Doğruluk için yerel ölçümlerle (tercihen radyasyon
  ölçen bir istasyonla) karşılaştırma gerekir.
- İki ızgara kaynağı arasındaki %10 civarındaki ETo farkı, kıyıya yakın
  alanlarda kaynak seçiminin net sulamayı tek başına %10–20 değiştirebileceğini
  gösteriyor; raporun “Limitations” bölümündeki uyarılar bu nedenle var.
- Etkili yağış yöntemleri arasındaki NIR farkı kurak sezonda küçük (≤ 12 mm),
  yağışlı sezonda Pe'de büyük ama NIR'da sınırlı; toprak su dengesi (v0.3)
  kışlık bitkilerde daha anlamlı bir karşılaştırma sağlayacak.

## İstasyon karşılaştırması (yalnız yerel)

Aynı betik, NOAA GSOD'daki Tekirdağ sinoptik istasyonu (WMO 17056) kaydını da
üçüncü kaynak olarak çalıştırıyor (radyasyon yok; Rs FAO-56 Denklem 50 ile,
kıyı için kRs = 0,19). GSOD belgesine göre ABD dışı istasyonların verileri WMO
Kararı 40 kapsamında paylaşılıyor ve veriler ya da türetilmiş ürünler başka
kullanıcılara verilmemeli. Bu nedenle indirilen veri, dönüştürülen CSV ve
istasyon sonuçları depoya girmiyor; `tools/validation/local/` ve `docs/local/`
altında (gitignore) kalıyor.

## Yeniden üretme

```bash
PYTHONPATH=/Applications/QGIS.app/Contents/Resources/qgis/python/plugins:. /Applications/QGIS.app/Contents/MacOS/python tools/validation/compare_sources.py --year 2024
```

```bash
python3 tools/validation/render_source_comparison.py
```

İlk komut verileri indirir (NASA POWER, Open-Meteo, GSOD), algoritmayı üç
kaynak × üç Pe yöntemiyle çalıştırır ve sonuçları
`tools/validation/local/source_comparison.json` dosyasına yazar; ikincisi bu
belgedeki tabloları üretir (`--station` ile istasyon sütunları da eklenir,
yalnız yerel kullanım için).

Open-Meteo verisi: Weather data by Open-Meteo.com, CC BY 4.0; generated using
Copernicus Climate Change Service information. NASA POWER: These data were
obtained from the NASA Langley Research Center (LaRC) POWER Project funded
through the NASA Earth Science/Applied Science Program.
