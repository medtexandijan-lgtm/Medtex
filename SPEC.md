# Tibbiyot Jihozlari CRM - Loyiha Spetsifikatsiyasi

## 1. Loyiha Umumiy Ma'lumotlari

**Loyiha nomi:** Tibbiyot Jihozlari CRM  
**Tavsif:** Professional tibbiyot jihozlari savdosi dokoni uchun CRM tizimi  
**Til:** O'zbek (ozbek-cha)  
**Foydalanuvchi rollari:** Direktor, Sotuvchi, Omborchi

---

## 2. Rol Va Imkoniyatlar

### Direktor
- Barcha ma'lumotlarni ko'rish va tahrirlash
- Sotuvchilar va omborchilarni boshqarish
- Hisobot va statistikani ko'rish
- Mahsulotlar va kategoriyalarni boshqarish
- Mijozlar ro'yxatini ko'rish

### Sotuvchi
- Yangi sotuvlar qilish
- Mijozlar ro'yxatini ko'rish
- O'z sotuvlar tarixini ko'rish
- Mahsulotlar katalogini ko'rish

### Omborchi
- Mahsulotlar qoldig'ini ko'rish
- Yangi mahsulotlar qo'shish
- Mahsulotlar tahrirlash
- Kirim-chiqim tarixini ko'rish

---

## 3. Funksional Talablar

### 3.1 Kirish (Login)
- Foydalanuvchi nomi va parol
- Rol bo'yicha avtorizatsiya

### 3.2 Boshqaruv Paneli (Dashboard)
- Har bir rol uchun moslashtirilgan ko'rinish
- Tezkor statistika

### 3.3 Mahsulotlar Moduli
- Mahsulotlar ro'yxati (nomi, narxi, soni, kategoriya)
- Qo'shish, tahrirlash, o'chirish
- Qidiruv va filtrlash
- Kategoriyalar boshqaruvi

### 3.4 Sotuvlar Moduli
- Yangi sotuv yaratish
- Sotuvlar tarixi
- Sotuv tafsilotlari
- Qaytarish

### 3.5 Mijozlar Moduli
- Mijozlar ro'yxati
- Mijoz qo'shish/tahrirlash
- Aloqa ma'lumotlari

### 3.6 Ombor Moduli
- Mahsulot qoldiqlari
- Kirim-chiqim qilish
- Tarix

### 3.7 Hisobotlar
- Sotuvlar hisoboti
- Daromad hisoboti
- Mahsulotlar analitikasi

---

## 4. Dizayn Talablari

### 4.1 Rang sxemasi
- Asosiy rang: Ko'k (#2563eb)
- Ikkinchi rang: Oq (#ffffff)
- Orqa fon: Kulrang (#f8fafc)
- Matn: Qora (#1e293b)
- Muvaffaqiyat: Yashil (#16a34a)
- Xato: Qizil (#dc2626)

### 4.2 Tipografiya
- Font: Inter yoki system-ui
- Sarlavhalar: Bold, 24-32px
- Matn: 14-16px

### 4.3 Komponentlar
- Tugmalar: Rounded (8px), hover effektlari
- Jadval: Professional stil, hover effektlari
- Forma: Toza dizayn, validation
- Kartalar: Shadow, rounded corners

---

## 5. Texnik Stack

- **Backend:** Django 5.0
- **Frontend:** HTML, CSS, JavaScript (Django Templates)
- **Ma'lumotlar bazasi:** SQLite (rivojlantirish uchun)
- **CSS Framework:** Custom professional CSS

---

## 6. Sahifalar

1. `login/` - Kirish sahifasi
2. `dashboard/` - Boshqaruv paneli
3. `products/` - Mahsulotlar
4. `sales/` - Sotuvlar
5. `clients/` - Mijozlar
6. `warehouse/` - Ombor
7. `reports/` - Hisobotlar
8. `users/` - Foydalanuvchilar (Direktor uchun)