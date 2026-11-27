# Kütüphane (Git)

Bu klasördeki JSON dosyaları **kullanıcı stratejileri** ve **coin listeleridir**.
Veritabanının tamamı değildir; API anahtarı, işlem geçmişi veya ayar içermez.

- `strategies/` — görsel strateji tanımları (AL/SAT kuralları + risk bloğu)
- `coinlists/` — kullanıcı coin listeleri

## Güncelleme

```bash
python scripts/library_sync.py export
git add library
git commit -m "chore: strateji ve coin listelerini güncelle"
git push
```

## Geri yükleme

```bash
python scripts/library_sync.py import          # önizleme
python scripts/library_sync.py import --apply  # uygula
```

Ayrıntılı kurallar: [../docs/LIBRARY.md](../docs/LIBRARY.md)

> Dosya adındaki `--<kimlik>` bölümünü değiştirmeyin; botlar stratejileri bu
> kimlikle referans alır. `name` alanı serbestçe düzenlenebilir.
