"""Master data: 61 toko Mitra10 di 10 zona (Lampiran spesifikasi) + konstanta domain."""

ZONES = ["Sumatera", "Bali - Lombok", "Jakarta", "Bekasi", "Banten",
         "Jawa Barat", "Jawa Timur", "Jawa Tengah", "Sulawesi", "Kalimantan"]

# (nama toko tanpa prefiks "Mitra10", zona, kota, lat, lon, alias tambahan)
_STORES = [
    ("Antasari Lampung", "Sumatera", "Bandar Lampung", -5.3971, 105.2668, ["antasari"]),
    ("Batam", "Sumatera", "Batam", 1.1301, 104.0529, []),
    ("Jakabaring", "Sumatera", "Palembang", -3.0217, 104.7836, []),
    ("JBC Jambi", "Sumatera", "Jambi", -1.6101, 103.6131, ["jambi", "jbc"]),
    ("Medan", "Sumatera", "Medan", 3.5952, 98.6722, []),
    ("Pekanbaru", "Sumatera", "Pekanbaru", 0.5071, 101.4478, ["pku"]),
    ("Rajabasa Lampung", "Sumatera", "Bandar Lampung", -5.3622, 105.2390, ["rajabasa"]),
    ("Tanjung Api Api Palembang", "Sumatera", "Palembang", -2.9201, 104.7206, ["tanjung api api", "tanjung api-api"]),
    ("Bypass Ngurah Rai", "Bali - Lombok", "Denpasar", -8.7206, 115.1843, ["bypass", "ngurah rai"]),
    ("Gatot Subroto Bali", "Bali - Lombok", "Denpasar", -8.6380, 115.2140, ["gatsu bali", "gatot subroto"]),
    ("Mataram", "Bali - Lombok", "Mataram", -8.5833, 116.1167, ["lombok"]),
    ("Imam Bonjol Bali", "Bali - Lombok", "Denpasar", -8.6789, 115.2003, ["imam bonjol"]),
    ("Daan Mogot", "Jakarta", "Jakarta Barat", -6.1555, 106.7310, ["damo"]),
    ("Fatmawati", "Jakarta", "Jakarta Selatan", -6.2925, 106.7975, []),
    ("Pantai Indah Kapuk", "Jakarta", "Jakarta Utara", -6.1103, 106.7404, ["pik"]),
    ("Percetakan Negara", "Jakarta", "Jakarta Pusat", -6.1834, 106.8693, ["percetakan"]),
    ("Pesanggrahan", "Jakarta", "Jakarta Selatan", -6.2522, 106.7608, []),
    ("Pondok Bambu", "Jakarta", "Jakarta Timur", -6.2365, 106.9040, []),
    ("Cibubur", "Bekasi", "Bekasi", -6.3730, 106.8955, []),
    ("Kota Harapan Indah", "Bekasi", "Bekasi", -6.1852, 106.9790, ["harapan indah", "khi"]),
    ("Jati Makmur", "Bekasi", "Bekasi", -6.2585, 106.9470, ["jatimakmur"]),
    ("Kalimalang Baru", "Bekasi", "Bekasi", -6.2470, 106.9930, ["kalimalang"]),
    ("Pondok Betung Bintaro", "Banten", "Tangerang Selatan", -6.2690, 106.7470, ["pondok betung"]),
    ("Bintaro Jaya", "Banten", "Tangerang Selatan", -6.2820, 106.7180, ["bintaro"]),
    ("Bitung", "Banten", "Tangerang", -6.2130, 106.5830, []),
    ("Gading Serpong", "Banten", "Tangerang", -6.2420, 106.6300, ["serpong", "gading"]),
    ("Pasar Baru", "Banten", "Tangerang", -6.1780, 106.6330, []),
    ("Q-Big", "Banten", "Tangerang Selatan", -6.2960, 106.6680, ["qbig", "q big", "bsd"]),
    ("Serang", "Banten", "Serang", -6.1150, 106.1500, []),
    ("Pamulang", "Banten", "Tangerang Selatan", -6.3420, 106.7380, []),
    ("TAV Bandung", "Jawa Barat", "Bandung", -6.9420, 107.6750, ["tav", "bandung"]),
    ("Iskandar Bogor", "Jawa Barat", "Bogor", -6.5600, 106.7930, ["iskandar", "bogor"]),
    ("Cibinong", "Jawa Barat", "Bogor", -6.4820, 106.8540, []),
    ("Cinere", "Jawa Barat", "Depok", -6.3270, 106.7840, []),
    ("Sunan Gunung Jati", "Jawa Barat", "Cirebon", -6.7240, 108.5520, ["cirebon", "gunung jati"]),
    ("Depok", "Jawa Barat", "Depok", -6.3940, 106.8220, []),
    ("Garut", "Jawa Barat", "Garut", -7.2120, 107.9000, []),
    ("Jababeka", "Jawa Barat", "Bekasi", -6.2960, 107.1510, ["cikarang"]),
    ("Telukjambe Timur Karawang", "Jawa Barat", "Karawang", -6.3060, 107.2900, ["karawang", "telukjambe"]),
    ("Tasikmalaya", "Jawa Barat", "Tasikmalaya", -7.3270, 108.2200, ["tasik"]),
    ("Shila Sawangan", "Jawa Barat", "Depok", -6.4160, 106.7650, ["sawangan", "shila"]),
    ("Cibarusah", "Jawa Barat", "Bekasi", -6.4290, 107.0870, []),
    ("Pasir Kaliki", "Jawa Barat", "Bandung", -6.9010, 107.5960, ["pasirkaliki"]),
    ("Ahmad Yani Surabaya", "Jawa Timur", "Surabaya", -7.3150, 112.7310, ["ahmad yani", "a yani"]),
    ("Jenggolo Sidoarjo", "Jawa Timur", "Sidoarjo", -7.4470, 112.7180, ["sidoarjo", "jenggolo"]),
    ("Kebon Sari Malang", "Jawa Timur", "Malang", -8.0050, 112.6250, ["malang", "kebonsari"]),
    ("Kedungdoro", "Jawa Timur", "Surabaya", -7.2590, 112.7350, []),
    ("Madiun", "Jawa Timur", "Madiun", -7.6290, 111.5240, []),
    ("Wiyung", "Jawa Timur", "Surabaya", -7.3100, 112.6900, []),
    ("Tegal", "Jawa Tengah", "Tegal", -6.8690, 109.1400, []),
    ("Purwokerto", "Jawa Tengah", "Purwokerto", -7.4240, 109.2340, ["pwt"]),
    ("Semarang", "Jawa Tengah", "Semarang", -6.9930, 110.4200, ["smg"]),
    ("Solo Baru", "Jawa Tengah", "Sukoharjo", -7.5980, 110.8180, ["solo", "solobaru"]),
    ("Yogyakarta", "Jawa Tengah", "Yogyakarta", -7.7830, 110.3670, ["jogja", "yogya", "jogjakarta"]),
    ("Kendari", "Sulawesi", "Kendari", -3.9780, 122.5150, []),
    ("Tallasa City Makassar", "Sulawesi", "Makassar", -5.1150, 119.4370, ["tallasa"]),
    ("Perintis Makassar", "Sulawesi", "Makassar", -5.1340, 119.4870, ["perintis"]),
    ("Pengayoman Makassar", "Sulawesi", "Makassar", -5.1560, 119.4450, ["pengayoman"]),
    ("Balikpapan Baru", "Kalimantan", "Balikpapan", -1.2510, 116.8650, ["balikpapan"]),
    ("Samarinda", "Kalimantan", "Samarinda", -0.5020, 117.1530, []),
    ("Pal88 Banjarmasin", "Kalimantan", "Banjarmasin", -3.3190, 114.5900, ["pal 88", "banjarmasin"]),
]

STORES = [
    {"kode": f"M{i + 1:03d}", "nama": f"Mitra10 {n}", "short": n, "zona": z, "kota": k,
     "lat": la, "lon": lo, "alias": [n.lower()] + al}
    for i, (n, z, k, la, lo, al) in enumerate(_STORES)
]

assert len(STORES) == 61, len(STORES)

KATEGORI = ["comedy", "beauty", "lifestyle", "culinary", "general"]
KATEGORI_LABEL = {"comedy": "Comedy", "beauty": "Beauty", "lifestyle": "Lifestyle",
                  "culinary": "Culinary", "general": "General"}
DELIVERABLES = ["video", "reels", "story", "artikel"]
PLATFORMS = ["Instagram", "TikTok", "Portal News"]

ROLES = {
    "ecommerce": "E-commerce",
    "asst_manager": "Asisten Manager",
    "manager": "Manager",
    "store": "Store",
    "finance": "Finance",
    "super_user": "Super User",
}

PROD_STAGES = [("pitching", "Pitching"), ("brief", "Brief"), ("take", "Take konten"),
               ("review", "Review"), ("posting", "Posting"), ("lapor", "Pelaporan")]

BRIEF_SECTIONS = ["Objective", "Pesan utama", "Target audiens", "Toko & promo", "Storyboard per scene",
                  "Wajib & dilarang", "Caption & hashtag", "Deliverable & timeline", "Referensi"]
