# KOL Hub - Streamlit Cloud Deployment Guide

## 📋 Overview

KOL Hub telah dikonversi menjadi Streamlit application untuk deployment ke Streamlit Cloud.

**Architecture:**
- **Frontend:** Streamlit (di Streamlit Cloud)
- **Database:** Supabase PostgreSQL (FREE tier)
- **Authentication:** Streamlit session state (simple version)

## 🚀 Deployment Steps

### Step 1: Setup Supabase Database (FREE)

1. **Buat Akun Supabase**
   - Buka: https://supabase.com/
   - Sign up (FREE tier)
   - Buat new project: "kol-hub"

2. **Get Database Credentials**
   - Setelah project dibuat, buka Settings → Database
   - Catat:
     - Database URL
     - Database password
     - Database host
     - Database port (default: 5432)

3. **Run Database Schema**
   - Buka SQL Editor di Supabase dashboard
   - Copy dan paste schema dari file: `services/api/alembic/versions/001_initial_schema.py`
   - Execute SQL script

4. **Seed Master Data**
   - Di SQL Editor, run script dari: `services/api/scripts/seed_master_data.py`
   - Atau gunakan Supabase seed data feature

### Step 2: Setup GitHub Repository

1. **Initialize Git (jika belum)**
   ```bash
   cd "/Users/mardeliaastriani/Documents/digital marketing/kol-hub"
   git init
   git add .
   git commit -m "Initial commit - KOL Hub Streamlit app"
   ```

2. **Create GitHub Repository**
   - Buka: https://github.com/new
   - Create repository: `kol-hub`
   - Push local repo:
     ```bash
     git remote add origin https://github.com/YOUR_USERNAME/kol-hub.git
     git branch -M main
     git push -u origin main
     ```

3. **Update File Structure**
   Buat struktur folder berikut di root repo:
   ```
   kol-hub/
   ├── app.py                  # Streamlit main app (copy dari apps/streamlit/app.py)
   ├── requirements.txt         # Streamlit requirements (copy dari apps/streamlit/requirements.txt)
   ├── .streamlit/
   │   └── config.toml        # Streamlit config (copy dari apps/streamlit/.streamlit/config.toml)
   └── README.md
   ```

   Run commands:
   ```bash
   cd "/Users/mardeliaastriani/Documents/digital marketing/kol-hub"
   cp apps/streamlit/app.py app.py
   cp apps/streamlit/requirements.txt requirements.txt
   cp -r apps/streamlit/.streamlit .streamlit
   git add app.py requirements.txt .streamlit/
   git commit -m "Add Streamlit app to root for deployment"
   git push
   ```

### Step 3: Deploy ke Streamlit Cloud

1. **Buka Streamlit Cloud**
   - Buka: https://share.streamlit.io/
   - Login dengan GitHub account

2. **Deploy New App**
   - Klik "New app"
   - Pilih repository: `kol-hub`
   - Pilih branch: `main`
   - Main file path: `app.py`
   - Klik "Deploy"

3. **Set Environment Variables**
   - Setelah deploy, buka Settings → Secrets
   - Add secret:
     - Name: `DATABASE_URL`
     - Value: `postgresql://postgres:[PASSWORD]@[HOST]:5432/[DATABASE]`
     - (Ganti dengan credentials dari Supabase)

4. **Restart App**
   - Setelah secrets di-set, restart app
   - App akan berjalan di: `https://your-app-name.streamlit.app`

### Step 4: Test Deployment

1. **Buka App URL**
   - App akan diakses di: `https://[app-name].streamlit.app`
   - Test login dengan email/password apa saja (demo mode)

2. **Test Pages**
   - Dashboard: Cek KPI cards dan charts
   - KOL Database: Cek list KOLs
   - KOL Analysis: Cek scoring methodology
   - Campaigns: Cek campaign management

## 🔐 Security Notes

### Current Implementation (Demo Mode)
- Login menggunakan email/password apa saja (tanpa validasi database)
- Tidak ada 2FA
- Tidak ada role-based access control (RBAC)
- Data menggunakan sample data (dummy)

### Production Improvements (Recommended)
Untuk production, tambahkan:

1. **Real Authentication**
   - Integrate Supabase Auth
   - Atau implement JWT token validation
   - Add 2FA (TOTP)

2. **Database Connection**
   - Use Supabase Python client
   - Implement proper connection pooling
   - Add error handling

3. **Role-Based Access**
   - Implement RBAC di Supabase
   - Restrict page access based on user role
   - Add scope restrictions (zone/store level)

4. **Data Validation**
   - Connect to real database
   - Replace sample data with actual data
   - Implement data caching

## 📊 Supabase Schema

### Required Tables
Buat tabel berikut di Supabase SQL Editor:

```sql
-- Zones
CREATE TABLE zones (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Stores
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

-- Users
CREATE TYPE userrole AS ENUM ('ecommerce', 'asst_manager', 'manager', 'store', 'finance', 'super_user');

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

-- KOL Accounts
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
```

### Seed Data

```sql
-- Insert Zones
INSERT INTO zones (name) VALUES
('Sumatera'), ('Bali - Lombok'), ('Jakarta'), ('Bekasi'),
('Banten'), ('Jawa Barat'), ('Jawa Timur'), ('Jawa Tengah'),
('Sulawesi'), ('Kalimantan');

-- Insert Stores (sample)
INSERT INTO stores (code, name, zone_id, city) VALUES
('M001', 'Mitra10 Antasari Lampung', 1, 'Lampung'),
('M002', 'Mitra10 Batam', 1, 'Batam'),
('M003', 'Mitra10 Daan Mogot', 3, 'Jakarta');
```

## 🎯 Next Steps

### Immediate (Post-Deployment)
1. ✅ Test semua pages di Streamlit Cloud
2. ✅ Verify database connection ke Supabase
3. ✅ Add real authentication (Supabase Auth)
4. ✅ Connect real data dari database

### Short-term (1-2 weeks)
1. Implement real KOL data integration
2. Add file upload untuk traffic data
3. Implement approval workflow
4. Add analytics charts with real data

### Long-term (1-2 months)
1. Integrate Instagram/TikTok API
2. Add ML scoring with real models
3. Implement payment processing
4. Add export to PDF/Excel

## 📝 Environment Variables

Add these secrets in Streamlit Cloud:

```
DATABASE_URL=postgresql://postgres:[PASSWORD]@[HOST]:5432/[DATABASE]
SECRET_KEY=your-secret-key-here
```

## 🆘 Troubleshooting

### Deployment Failed
- Check requirements.txt format
- Verify app.py is in root directory
- Check .streamlit/config.toml location

### Database Connection Error
- Verify DATABASE_URL format
- Check Supabase project status
- Verify database credentials

### App Not Loading
- Check Streamlit Cloud logs
- Verify all dependencies in requirements.txt
- Check for Python version compatibility

## 📚 Resources

- Streamlit Cloud Docs: https://docs.streamlit.io/streamlit-cloud
- Supabase Docs: https://supabase.com/docs
- Streamlit Authentication: https://docs.streamlit.io/library/advanced-features/authentication

---

**Deployment Status:** Ready for deployment
**Platform:** Streamlit Cloud + Supabase
**Cost:** FREE (Streamlit Cloud + Supabase FREE tier)
