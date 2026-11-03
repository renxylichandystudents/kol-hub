# KOL Hub - Deployment Checklist untuk Streamlit Cloud

## ✅ File yang Sudah Siap

### 1. Streamlit App Files
- ✅ `app.py` - Main Streamlit application
- ✅ `requirements.txt` - Python dependencies
- ✅ `.streamlit/config.toml` - Streamlit configuration

### 2. Documentation
- ✅ `STREAMLIT_DEPLOYMENT.md` - Panduan deployment lengkap
- ✅ `README.md` - Project overview
- ✅ `SETUP_COMPLETE.md` - Setup status

## 🚀 Langkah Deployment (Ikuti Langkah Ini)

### Step 1: Setup Supabase Database (FREE)

1. **Buka Supabase**
   - URL: https://supabase.com/
   - Sign up (FREE tier - 500MB database, 1GB bandwidth)

2. **Buat Project**
   - Klik "New Project"
   - Name: `kol-hub`
   - Database Password: (pilih password yang kuat dan simpan!)
   - Region: Singapore (terdekat ke Indonesia)
   - Wait for project initialization (1-2 menit)

3. **Copy Database Credentials**
   - Buka Settings → Database
   - Copy:
     - Connection string format: `postgresql://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres`
     - Atau klik "URI" untuk copy full connection string

4. **Setup Database Schema**
   - Buka SQL Editor di Supabase
   - Copy dan paste SQL schema dari file ini:

```sql
-- Create enum for user roles
CREATE TYPE userrole AS ENUM ('ecommerce', 'asst_manager', 'manager', 'store', 'finance', 'super_user');

-- Zones table
CREATE TABLE zones (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Stores table
CREATE TABLE stores (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    zone_id INTEGER REFERENCES zones(id),
    city VARCHAR(100) NOT NULL,
    lat NUMERIC(10, 7),
    lon NUMERIC(10, 7),
    alias JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    totp_secret VARCHAR(255),
    role userrole NOT NULL,
    scope_zone_id INTEGER REFERENCES zones(id),
    scope_store_id INTEGER REFERENCES stores(id),
    is_active BOOLEAN DEFAULT TRUE,
    is_2fa_enabled BOOLEAN DEFAULT FALSE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- KOL Accounts table
CREATE TABLE kol_accounts (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    username VARCHAR(255) NOT NULL,
    link VARCHAR(500) NOT NULL,
    category VARCHAR(50),
    niche VARCHAR(255),
    city_domisili VARCHAR(100),
    status VARCHAR(20) DEFAULT 'aktif',
    alasan_blokir TEXT,
    blocked_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Insert Zones
INSERT INTO zones (name) VALUES
('Sumatera'), ('Bali - Lombok'), ('Jakarta'), ('Bekasi'),
('Banten'), ('Jawa Barat'), ('Jawa Timur'), ('Jawa Tengah'),
('Sulawesi'), ('Kalimantan');

-- Insert sample stores
INSERT INTO stores (code, name, zone_id, city) VALUES
('M001', 'Mitra10 Antasari Lampung', 1, 'Lampung'),
('M002', 'Mitra10 Batam', 1, 'Batam'),
('M003', 'Mitra10 Daan Mogot', 3, 'Jakarta'),
('M004', 'Mitra10 Fatmawati', 3, 'Jakarta'),
('M005', 'Mitra10 Bintaro Jaya', 4, 'Bekasi');
```

5. **Execute SQL**
   - Klik "Run" atau CTRL+Enter
   - Verifikasi semua tables berhasil dibuat di Table Editor

### Step 2: Setup GitHub Repository

1. **Buat GitHub Repository**
   - Buka: https://github.com/new
   - Repository name: `kol-hub`
   - Public/Private: Private (untuk internal team)
   - Klik "Create repository"

2. **Setup Git Lokal**
   Buka terminal dan jalankan:

```bash
cd "/Users/mardeliaastriani/Documents/digital marketing/kol-hub"

# Initialize git
git init

# Add semua file
git add app.py requirements.txt .streamlit/ STREAMLIT_DEPLOYMENT.md README.md

# Commit
git commit -m "Initial commit - KOL Hub Streamlit app"

# Add remote (ganti YOUR_USERNAME dengan GitHub username Anda)
git remote add origin https://github.com/YOUR_USERNAME/kol-hub.git

# Push ke GitHub
git branch -M main
git push -u origin main
```

3. **Verifikasi di GitHub**
   - Buka repository di GitHub
   - Pastikan file app.py, requirements.txt, dan .streamlit/ sudah terupload

### Step 3: Deploy ke Streamlit Cloud

1. **Buka Streamlit Cloud**
   - URL: https://share.streamlit.io/
   - Login dengan GitHub account (sama dengan repo GitHub)

2. **Deploy New App**
   - Klik "New app" (di dashboard)
   - Pilih:
     - Repository: `kol-hub`
     - Branch: `main`
     - Main file path: `app.py`
   - Klik "Deploy"

3. **Tunggu Deployment**
   - Streamlit akan pull dari GitHub
   - Install dependencies dari requirements.txt
   - App akan berjalan dalam 1-2 menit

4. **Set Environment Variables**
   - Setelah deploy selesai, buka app settings
   - Klik "Secrets" atau "Environment Variables"
   - Add new secret:
     - Name: `DATABASE_URL`
     - Value: (paste connection string dari Supabase)
     - Contoh: `postgresql://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres`

5. **Restart App**
   - Setelah secrets di-set, klik "Restart" atau "Rerun"
   - App akan reload dengan database connection

### Step 4: Test Aplikasi

1. **Buka App URL**
   - App akan diakses di: `https://[app-name].streamlit.app`
   - App name biasanya auto-generated dari repo name

2. **Test Login**
   - Masukkan email apa saja (demo mode)
   - Masukkan password apa saja
   - Klik "Login"

3. **Test Pages**
   - Dashboard: Cek KPI cards dan charts
   - KOL Database: Cek list KOLs
   - KOL Analysis: Cek scoring methodology
   - Campaigns: Cek campaign management

4. **Share dengan Team**
   - Share URL Streamlit Cloud ke team
   - Semua user bisa akses tanpa localhost

## 🔐 Security Recommendations

### Untuk Production:

1. **Implement Real Authentication**
   - Gunakan Supabase Auth (FREE)
   - Atau implement JWT dengan FastAPI terpisah

2. **Add Environment Variables**
   - `DATABASE_URL` - Sudah di-set
   - `SECRET_KEY` - Untuk session encryption
   - `SUPABASE_URL` - Supabase project URL
   - `SUPABASE_KEY` - Supabase anon key

3. **Enable Row Level Security (RLS) di Supabase**
   - Restrict data access per user
   - Implement scope restrictions (zone/store level)

## 📊 Cost Estimation

### Streamlit Cloud
- **FREE**: 1 app, unlimited public access
- **Pro**: $10/month untuk private apps (optional)

### Supabase
- **FREE**: 500MB database, 1GB bandwidth/month
- **Pro**: $25/month untuk 8GB database (opsional)

**Total untuk deployment: FREE**

## 🆘 Troubleshooting

### App Failed to Deploy
- Check requirements.txt format (hanya satu line per package)
- Verify app.py is in root directory
- Check .streamlit/config.toml location

### Database Connection Error
- Verify DATABASE_URL format di secrets
- Check Supabase project status (active/suspended)
- Test connection dengan psql client

### App Shows Blank Screen
- Check Streamlit Cloud logs
- Verify all dependencies installed
- Check for Python errors in logs

## 📝 Next Steps Setelah Deploy

1. **Connect Real Data**
   - Ganti sample data dengan query ke Supabase
   - Implement CRUD operations untuk KOL database
   - Add file upload untuk traffic data

2. **Add Real Authentication**
   - Integrate Supabase Auth
   - Implement role-based access control
   - Add 2FA (TOTP)

3. **Enhance Features**
   - Add export to Excel/PDF
   - Implement approval workflow
   - Add analytics dengan real data
   - Integrate Instagram/TikTok API

4. **Monitor & Maintain**
   - Monitor app usage di Streamlit Cloud
   - Check database usage di Supabase
   - Backup data secara regular

---

**Status:** Siap untuk deployment
**Files siap:** app.py, requirements.txt, .streamlit/config.toml
**Langkah berikutnya:** Setup Supabase → Setup GitHub → Deploy ke Streamlit Cloud
