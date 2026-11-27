# Strateji ve Coin Listesi Kütüphanesi

Veritabanının tamamını yedeklemek yerine **yalnızca kullanıcı stratejileri**
ve **coin listeleri** Git dostu JSON dosyalarına aktarılır. Böylece:

- stratejilerin değişiklik geçmişi Git'te tutulur (diff'ler okunabilir),
- coin listeleri başka bir kuruluma/sunucuya taşınabilir,
- veritabanı dosyası (`.db`) repoya girmez; sadece tanımlar paylaşılır.

Hazır (builtin) stratejiler kodda (`Stratejiler.py`, `app/strategies/`) ve
hazır coin listeleri `app/coin_lists.py` içinde tanımlıdır; bu yüzden varsayılan
olarak dışa aktarılmazlar.

## Açılışta otomatik içe aktarma

Sunucu her açıldığında `library/` klasörü taranır ve **eksik** strateji/coin
listeleri veritabanına eklenir. Böylece repoyu klonlayan kişi elle `import`
çalıştırmadan stratejilere ve coin listelerine erişir.

- Yalnızca **olmayan** kayıtlar eklenir; panelden düzenlenmiş bir kayıt
  dosyadaki eski sürümle **ezilmez**.
- Kapatmak için: `LIBRARY_AUTO_IMPORT=0`.
- Ayrıntılı log: sunucu çıktısında `Kütüphaneden N kayıt eklendi` satırı.

> Dosyaları elle güncelleyip var olan kayıtları da değiştirmek isterseniz
> `python scripts/library_sync.py import --apply` komutunu kullanın.

## Dışa aktarma

```bash
python scripts/library_sync.py export
```

`library/` altında iki klasör oluşur:

```txt
library/
  strategies/<isim>--<kimlik>.json
  coinlists/<isim>--<kimlik>.json
```

- Dosya adındaki **kimlik korunur** (`custom_...`, `lst_...`). Botların
  strateji referansları içe aktarma sonrasında da geçerli kalır.
- Strateji adı değişirse eski dosya otomatik silinir.
- Artık veritabanında olmayan dosyaları da temizlemek için:

```bash
python scripts/library_sync.py export --prune
```

Seçenekler:

| Seçenek | Anlamı |
|---|---|
| `--no-archived` | Arşivlenmiş stratejileri dışa aktarma |
| `--include-builtin-lists` | Hazır coin listelerini de yaz |
| `--prune` | Veritabanında olmayan JSON dosyalarını sil |

## GitHub'a gönderme

```bash
python scripts/library_sync.py export
git add library
git commit -m "chore: strateji ve coin listelerini güncelle"
git push
```

## Geri yükleme (başka makine / sunucu)

Önce **önizleme** (hiçbir şey yazılmaz):

```bash
python scripts/library_sync.py import
```

Uygula:

```bash
python scripts/library_sync.py import --apply
```

Eşleştirme kuralları:

1. Dosyadaki `id` veritabanında varsa → o strateji **güncellenir**
   (yeni sürüm oluşur).
2. `id` yoksa ama **ad** varsa → adla eşleşen kayıt güncellenir.
3. İkisi de yoksa → aynı `id` boştaysa onunla, değilse yeni kimlikle
   **oluşturulur**.
4. Tanım birebir aynıysa → **atlanır** (sürüm şişmez, komut idempotenttir).

Hazır bir coin listesiyle aynı ad/ID gelirse hazır liste değiştirilmez;
`(içe aktarma)` ekli bir **kullanıcı kopyası** oluşturulur.

## Dosya biçimi

Strateji:

```json
{
  "kind": "strategy",
  "schema": 1,
  "id": "custom_a601d0e770",
  "name": "Tillson T3 & QQE MOD",
  "version": 6,
  "status": "active",
  "definition": { "name": "...", "buy": {}, "sell": {}, "risk": {} }
}
```

Coin listesi:

```json
{
  "kind": "coinlist",
  "schema": 1,
  "id": "lst_f08ce94332",
  "name": "Trend 4h",
  "coins": ["BTCUSDT", "SOLUSDT"]
}
```

> Dosyalar **deterministiktir**: değişiklik yoksa yeniden dışa aktarma Git'te
> diff üretmez. Elle düzenlerken `id` ve `definition` yapısını bozmamaya dikkat
> edin; `name` alanı serbestçe değiştirilebilir.

## Neden veritabanı yedeği değil?

Tam DB yedeği; bot durumları, işlem geçmişi, ayarlar ve AI modellerini de
taşır. Bu kütüphane yalnızca **taşınabilir tanımları** paylaşır:

- sır içermez (API anahtarı, oturum, cüzdan yok),
- Git diff'i okunabilir,
- farklı makinelerde çakışma kuralları bellidir.

İşlem geçmişi/ayarlar için mevcut tam yedekleme özelliğini kullanın.
