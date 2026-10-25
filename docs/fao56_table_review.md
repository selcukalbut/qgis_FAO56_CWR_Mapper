# FAO-56 Tablo 11 / 12 kontrol listesi

Kaynak: https://www.fao.org/3/x0490e/x0490e0b.htm (FAO-56 Bölüm 6, HTML sürümü).
Çıkarım: `tools/extract_fao56_tables.py` → `fao56_cwr_mapper/data/*.csv`
(Tablo 12: 124 satır, Tablo 11: 167 satır). Değerler HTML'deki metinle birebir;
dipnot işaretleri ayrı sütunda.

Otomatik kontroller: evre toplamı = toplam süre, Kc 0.1–1.4 aralığında, en fazla
2 ondalık, sayı biçimi. Aşağıdaki maddeler bu kontrollerden geçemedi.
Onaylanan düzeltmeler `tools/fao56_corrections.csv` dosyasına gerekçesiyle yazılır.

Durum: ☐ kitapla kontrol bekliyor · ☑ onaylandı

## A. Tablo 11 – basılı kitapla karşılaştırma (tamamlandı)

Tablo 11'in tamamı basılı kitabın sayfalarıyla (5 sayfa) satır satır
karşılaştırıldı: tüm sayılar HTML ile aynı. Aşağıdakiler kitapta da böyle
basılmış; düzeltme veya not `tools/fao56_corrections.csv` dosyasında.

| # | Bitki (satır) | Kitapta | Sonuç |
|---|---|---|---|
| A1 ☑ | Egg plant (1) | toplam "130\14" | dizgi hatası, 140'ın parçası alt satıra kaymış → 130 |
| A2 ☑ | Egg plant (2) | toplam "0" | aynı dizgi hatası → 140 |
| A3 ☑ | Rice (2) | gelişme 30 | HTML'deki "30." → 30 |
| A4 ☑ | Olives | toplam 270 + dipnot 5 | HTML'deki "2705" → 270 |
| A5 ☑ | Maize sweet (4, Idaho) | son 10 + dipnot 3, toplam 110 | son evre → 10; toplam tutarsızlığı FAO-56 orijinalinde (100 ≠ 110), not eklendi |
| A6 ☑ | Green gram, cowpeas | toplam 110 | orijinal tutarsızlık (100 ≠ 110), not eklendi |
| A7 ☑ | Sesame | toplam 100 | orijinal tutarsızlık (110 ≠ 100), not eklendi |
| A8 ☑ | Sorghum (1) | toplam 130 | orijinal tutarsızlık (125 ≠ 130), not eklendi |
| A9 ☑ | Sorghum (2) | toplam 140 | orijinal tutarsızlık (130 ≠ 140), not eklendi |

Hesapta evre süreleri kullanılır, toplam sütunu yalnızca bilgi amaçlıdır;
A5–A9'daki tutarsızlık sonucu etkilemez ama kullanıcıya not olarak gösterilir.

## B. Tablo 11 – iki seçenekli değerler ("a/b") – kitapla aynı ☑

Carrots (1): orta 50/30, toplam 100 · Spinach (1): orta 15/25, toplam 60/70 ·
Sweet peppers (1): başlangıç 25/30 · Potato (1): orta 30/45, toplam 115/130 ·
Soybeans (2): gelişme 30/35 · Maize sweet (3): orta 50/30, toplam 90.

Kitapta da aynı biçimde basılmış. Evre toplamı basılı toplamla şu seçenekte
tutuyor: Carrots orta 30 (100) · Spinach 15→60, 25→70 · Sweet peppers
başlangıç 30 (125) · Potato 30→115, 45→130 · Soybeans gelişme 35 (140) ·
Maize sweet orta 30 (90).

Öneri: her seçenek ayrı satır olsun; toplamla tutan seçenek varsayılan.

## T12. Tablo 12 – basılı kitapla karşılaştırma (tamamlandı)

Tablo 12'nin tamamı kitabın 110–114. sayfalarıyla (docs/Fao56.pdf, yerel kopya)
satır satır karşılaştırıldı; Kc ve bitki boyu değerleri HTML ile aynı.

| # | Satır | Kitapta | Sonuç |
|---|---|---|---|
| T12-1 ☑ | k. Sugar Cane | grup satırında 0.40 · 1.25 · 0.75, h = 3 | çıkarım betiği grup satırlarını atlıyordu; düzeltildi, satır eklendi |
| T12-2 ☑ | Walnut Orchard Kc_end | 0.65 + dipnot 18 | HTML'deki "0.6518" → 0.65 |
| T12-3 ☑ | Open Water (> 5 m) Kc_mid / Kc_end | 0.65 / 1.25 + dipnot 25 | HTML'deki "0.6525" / "1.2525" → 0.65 / 1.25 |
| T12-4 ☐ | Peas – Dry/Seed Kc_ini | boş; 0.5 yalnızca "Fresh" satırında | şimdilik grup değeri 0.4 kullanılıyor (karar: 0.4 mü, 0.5 mi?) |
| T12-5 ☑ | Maize, Field Kc_end | "0.60,0.35" (virgül) | HTML'de "0.60-0.35"; anlamı aynı (dipnot 11: iki ayrı durum), aşağıdaki C grubunda |

Kc_ini'si boş olan bitkiler grup satırındaki Kc_ini'yi alır (`kc_ini_from_group = yes`);
kitabın tablo düzeni de böyle okunmayı gerektiriyor.

## C. Tablo 12 – aralık olarak verilen Kc değerleri

Dipnotu anlamı belirleyenler (öneri: ayrı varyant satırları):

| Bitki | Kc | Dipnot | Öneri |
|---|---|---|---|
| Maize, field (grain) | end 0.60–0.35 | 11: yüksek nemde hasat / tarlada kurutma | iki varyant: 0.60 ve 0.35 |
| Green gram, cowpeas | end 0.60–0.35 | 6: taze hasat / kuru hasat | iki varyant: 0.60 ve 0.35 |
| Spring & winter wheat | end 0.25–0.4 | 10: yüksek değer elle hasat | makine 0.25 / elle 0.40 |
| Rapeseed, safflower, sunflower | mid 1.0–1.15 | 9: düşük değer yağışa dayalı, seyrek | sulu 1.15 / yağışa dayalı 1.0 |

Dipnotu olmayanlar (karar sizin):
Tomato end 0.70–0.90 · Cotton mid 1.15–1.20, end 0.70–0.50 · Rice end 0.90–0.60 ·
Sorghum grain mid 1.00–1.10 · Rotated grazing mid 0.85–1.05 · Sisal mid/end 0.4–0.7.

## D. Kapsam dışı bırakılması önerilen satırlar

Open Water (2 satır): Kc_ini yok (değerler kitapla düzeltildi, bkz. T12-3).
Bitki sulama hesabıyla ilgisi olmadığından eklentideki bitki listesine alınmasın.

## E. Sonraki adım (karar sonrası)

Tablo 11 ve 12'de bitki adları farklı (ör. "Egg plant" / "Egg Plant",
"Sugarbeet" / "Sugar Beet", "Barley/Oats/Wheat"). Eklentinin bitki listesi
için iki tablo arasında açık bir eşleme dosyası gerekecek.
