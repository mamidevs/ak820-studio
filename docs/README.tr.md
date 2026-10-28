# AK820 Studio — kullanım ve durum

Bu depo, AJAZZ AK820 Pro için hazırlanan yerel macOS panelini ve özel QMK ekran kaynaklarını içerir. Arayüz Türkçedir. Güncel kaynak tabanı **studio-v3.2**; bu sürümün 11 Ekim 2026'da tek bir cihazda yükleme checksum'u ve canlı USB köprüsü doğrulanmıştır. Başka cihaz revizyonları için uyumluluk garantisi verilmez.

## Başlatma

Python 3.12 veya üzeriyle `studio` klasöründe:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python start.py
```

Panel: [127.0.0.1:8765](http://127.0.0.1:8765). Kurulumdan sonra `AK820 Studio.command` çift tıklanabilir. Servis yalnız bu bilgisayarda çalışır; genel bir açılış servisi kurulmaz.

**Durum** sayfası pil, şarj, bağlantı ve AI verisini gösterir. **Bağlantılar** bölümündeki Bağla/Kes/Yenile işlemleri yalnız Studio'ya veri aktarımını yönetir; hesaplardan çıkış yapmaz. Claude Code bağlantısı mevcut durum satırı komutunu koruyan yerel bir alıcı kurar. Kota gelmemesi durumunda “veri yok” gösterilir; model isteği gönderilmez.

## Klavye

- Fn + düğmeye basma menüyü açar/kapatır. Çevirme seçimi, basma ilgili sayfayı açmayı sağlar.
- Ana ekranda halkalar/saat yüzü, Codex/Claude sayfaları, pil ve bağlantı bilgileri bulunur.
- Işık sayfası klavyenin RGB ayarlarını yönetir; düğme modu ve ekran ayarları da menüdedir.
- Canlı kullanım verisi USB kablosu üzerinden gider. Bluetooth/2.4 GHz bu veri kanalını taşımaz; kablo yokken önceki veri eskimiş olarak gösterilir.

## Açık sınırlar

**QMK'ye görsel/GIF gönderme kapalıdır.** Deneysel aktarım kodu kaynakta bulunsa da harici belleğe yazma yolu donanımda doğrulanmamıştır. Görsel düzenleme ve önizleme kullanılabilir. Stok firmware'de daha önce doğrulanan görsel/RGB davranışı yeni QMK için doğrulama sayılmaz.

**QMK RGB ayarları klavye ekranından yapılır.** Masaüstü QMK RGB adaptörü kullanılabilirlik bildirmez. Claude kullanım pencereleri hesap/istemci verisine bağlıdır; eksik pencere sıfır olarak gösterilmez. Ekrandaki bazı kablosuz geçiş/eşleştirme ve bilgisayar medya eylemlerinin cihaz bazında doğrulanması gerekir.

## Firmware güncelleme

Bu depoda hazır firmware BIN'i veya yükleme programı yoktur. Kaynak, sabit upstream sürümü ve derleme yönergeleri [firmware rehberindedir](../firmware/README.md).

1. Devam eden aktarımı bitirin ve Studio'yu durdurun.
2. Test edilen özel firmware'de **Fn + Esc** ile bootloader'a girilir. Normal güncellemede fiziksel boot temaslarını kısa devre yapmak gerekmez.
3. Bootloader USB kimliği `0c45:7140`, normal QMK kimliği `0c45:8009` / `0100` olmalıdır. Yalnız ürün adına bakarak dosya seçmeyin.
4. Tam donanımınıza uygun, derlemesi ve hash'i doğrulanmış dosyayı uygun yükleyiciyle kullanın. İşlem sonrası checksum/çıkış sonucu ve yeniden açılan cihazı kontrol edin.
5. Studio'yu açıp canlı köprünün yanıtını, tuşları, düğmeyi ve ekranı kontrol edin.

Boot temasları yalnız ayrıca doğrulanacak kurtarma seçeneğidir. Test edilen üniteye tam uyan orijinal stok dönüş dosyası doğrulanmadı; rastgele bir stok BIN güvenilir yedek değildir.

## Komutlar

Studio açıkken `studio` klasöründe:

```sh
.venv/bin/python connect.py all status
.venv/bin/python connect.py codex connect
.venv/bin/python connect.py codex refresh
.venv/bin/python connect.py codex disconnect
.venv/bin/python connect.py claude_code connect
.venv/bin/python connect.py claude_code refresh
.venv/bin/python connect.py claude_code disconnect
.venv/bin/python stop.py
```

Yerel kullanım verileri, yüklenen görseller, durum satırı yedekleri ve günlükler Git'e dahil edilmez. Açık kaynak paketi ayrı hazırlanmıştır; özgün çalışma dosyaları korunmuştur.
