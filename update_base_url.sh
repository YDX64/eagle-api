#!/bin/bash
# URL Configuration Update Script
# Bu script .env dosyasındaki NOWGOAL_BASE_URL'i günceller

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     NOWGOAL_BASE_URL Configuration Update Script          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Mevcut değeri göster
current_url=$(grep "^NOWGOAL_BASE_URL" .env | cut -d'=' -f2)
echo "📍 Mevcut URL: $current_url"
echo ""

# Seçenekleri göster
echo "Lütfen yeni URL'i seçin:"
echo ""
echo "  1) https://goaloo.com (Önerilen)"
echo "  2) https://www.goaloo.com"
echo "  3) https://nowgoal.com"
echo "  4) https://live.nowgoal26.com (Mevcut)"
echo "  5) Özel URL gir"
echo "  6) İptal"
echo ""

read -p "Seçiminiz (1-6): " choice

case $choice in
    1)
        new_url="https://goaloo.com"
        ;;
    2)
        new_url="https://www.goaloo.com"
        ;;
    3)
        new_url="https://nowgoal.com"
        ;;
    4)
        new_url="https://live.nowgoal26.com"
        ;;
    5)
        read -p "Özel URL girin (örn: https://example.com): " new_url
        ;;
    6)
        echo "❌ İptal edildi."
        exit 0
        ;;
    *)
        echo "❌ Geçersiz seçim!"
        exit 1
        ;;
esac

# Trailing slash kontrolü
if [[ $new_url == */ ]]; then
    echo ""
    echo "⚠️  UYARI: URL trailing slash (/) içeriyor!"
    echo "   Trailing slash kaldırılıyor: ${new_url%/}"
    new_url="${new_url%/}"
fi

# Onay
echo ""
echo "Yeni URL: $new_url"
read -p "Devam etmek istiyor musunuz? (y/n): " confirm

if [[ $confirm != "y" && $confirm != "Y" ]]; then
    echo "❌ İptal edildi."
    exit 0
fi

# Backup oluştur
backup_file=".env.backup.$(date +%Y%m%d_%H%M%S)"
cp .env "$backup_file"
echo "✅ Backup oluşturuldu: $backup_file"

# URL'i güncelle
sed -i.tmp "s|^NOWGOAL_BASE_URL=.*|NOWGOAL_BASE_URL=$new_url|" .env
rm -f .env.tmp

echo "✅ .env dosyası güncellendi"
echo ""
echo "📋 Yeni ayar:"
grep "^NOWGOAL_BASE_URL" .env
echo ""
echo "🔄 Değişikliklerin etkili olması için Gunicorn'i restart edin:"
echo "   sudo systemctl restart your-gunicorn-service"
echo "   # veya"
echo "   pkill -HUP gunicorn"
echo ""
