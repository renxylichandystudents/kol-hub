"""
KOL Hub - Streamlit Application with Real Authentication
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import os
import hashlib
import re

# Page configuration
st.set_page_config(
    page_title="KOL Hub - Mitra10 Digital Marketing",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1e3a8a;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'user' not in st.session_state:
    st.session_state.user = None
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'page' not in st.session_state:
    st.session_state.page = 'login'

# Database connection settings
DB_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    """Get database connection"""
    if not DB_URL:
        st.error("DATABASE_URL environment variable not set!")
        return None
    
    try:
        import psycopg2
        conn = psycopg2.connect(DB_URL)
        return conn
    except Exception as e:
        st.error(f"Database connection error: {str(e)}")
        return None

def hash_password(password):
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(email, password):
    """Verify user credentials against database"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        
        cursor.execute("""
            SELECT id, name, email, role, is_active
            FROM users
            WHERE email = %s AND password_hash = %s AND is_active = TRUE
        """, (email, password_hash))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return {
                'id': user[0],
                'name': user[1],
                'email': user[2],
                'role': user[3],
                'is_active': user[4]
            }
        return None
    except Exception as e:
        st.error(f"Login error: {str(e)}")
        conn.close()
        return None

def create_user(name, email, password, role='ecommerce'):
    """Create new user in database"""
    conn = get_db_connection()
    if not conn:
        return False, "Database connection failed"
    
    try:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        
        # Check if email already exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            conn.close()
            return False, "Email already registered"
        
        # Insert new user
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, role, is_active)
            VALUES (%s, %s, %s, %s, TRUE)
            RETURNING id
        """, (name, email, password_hash, role))
        
        user_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        
        return True, "User created successfully"
    except Exception as e:
        conn.close()
        return False, f"Error creating user: {str(e)}"

def login_page():
    """Login page with real authentication"""
    st.markdown('<h1 class="main-header">🎯 KOL Hub</h1>', unsafe_allow_html=True)
    st.markdown('<p style="font-size: 1.2rem; color: #666;">Mitra10 Digital Marketing Platform</p>', unsafe_allow_html=True)
    
    st.divider()
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        st.subheader("🔐 Login")
        
        email = st.text_input("Email", placeholder="contoh: user@mitra10.co.id")
        password = st.text_input("Password", type="password")
        
        col_a, col_b, col_c = st.columns([1, 2, 1])
        with col_b:
            if st.button("Login", use_container_width=True, type="primary"):
                if not email or not password:
                    st.error("Please enter email and password")
                else:
                    user = verify_user(email, password)
                    if user:
                        st.session_state.user = user
                        st.session_state.logged_in = True
                        st.session_state.page = 'dashboard'
                        st.success(f"Welcome back, {user['name']}!")
                        st.rerun()
                    else:
                        st.error("Invalid email or password")
    
    with tab2:
        st.subheader("📝 Register New Account")
        
        name = st.text_input("Full Name")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        role = st.selectbox("Role", ["ecommerce", "asst_manager", "manager", "store", "finance"])
        
        if st.button("Register", use_container_width=True, type="primary"):
            if not all([name, email, password, confirm_password]):
                st.error("Please fill all fields")
            elif password != confirm_password:
                st.error("Passwords do not match")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters")
            else:
                success, message = create_user(name, email, password, role)
                if success:
                    st.success(message)
                    st.info("You can now login with your credentials")
                else:
                    st.error(message)

def dashboard_page():
    """Dashboard page with KPIs"""
    st.markdown('<h1 class="main-header">📊 Dashboard</h1>', unsafe_allow_html=True)
    
    # User info
    st.sidebar.markdown(f"### 👤 {st.session_state.user['name']}")
    st.sidebar.markdown(f"📧 {st.session_state.user['email']}")
    st.sidebar.markdown(f"🏷️ {st.session_state.user['role'].replace('_', ' ').title()}")
    st.sidebar.divider()
    
    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total KOLs", "156", "+12 this month")
    with col2:
        st.metric("Active Campaigns", "23", "+5 this week")
    with col3:
        st.metric("Avg Engagement", "4.8%", "+0.3%")
    with col4:
        st.metric("Total Budget", "Rp 2.5M", "78% used")
    
    st.divider()
    
    # Charts placeholder
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Campaign Performance")
        df_chart = pd.DataFrame({
            'Month': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
            'Engagement': [3.2, 3.8, 4.1, 4.5, 4.7, 4.8]
        })
        st.line_chart(df_chart.set_index('Month'))
    
    with col2:
        st.subheader("🎯 Top Performing KOLs")
        df_kols = pd.DataFrame({
            'KOL Name': ['KOL A', 'KOL B', 'KOL C', 'KOL D', 'KOL E'],
            'Platform': ['Instagram', 'TikTok', 'Instagram', 'TikTok', 'Instagram'],
            'Engagement Rate': ['5.2%', '4.8%', '4.5%', '4.3%', '4.1%'],
            'Score': [95, 92, 88, 85, 82]
        })
        st.dataframe(df_kols, use_container_width=True)

def kol_database_page():
    """KOL Database page"""
    st.markdown('<h1 class="main-header">📱 KOL Database</h1>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        search = st.text_input("🔍 Search KOL", placeholder="Name, username, or platform")
    with col2:
        platform = st.selectbox("Platform", ["All", "Instagram", "TikTok", "Portal News"])
    with col3:
        status = st.selectbox("Status", ["All", "Active", "Blocked"])
    
    st.divider()
    
    st.subheader("KOL Accounts")
    
    kols_data = [
        {
            'name': 'Foodie Indonesia',
            'platform': 'Instagram',
            'username': '@foodieindo',
            'followers': '1.2M',
            'engagement': '5.2%',
            'category': 'Food',
            'status': 'Active',
            'score': 95
        },
        {
            'name': 'Tech Review ID',
            'platform': 'TikTok',
            'username': '@techreviewid',
            'followers': '850K',
            'engagement': '4.8%',
            'category': 'Technology',
            'status': 'Active',
            'score': 92
        }
    ]
    
    df_kols = pd.DataFrame(kols_data)
    
    for idx, row in df_kols.iterrows():
        with st.expander(f"{row['name']} - {row['platform']} ({row['username']})"):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Followers", row['followers'])
            col2.metric("Engagement", row['engagement'])
            col3.metric("Category", row['category'])
            col4.metric("Score", row['score'])

def kol_analysis_page():
    """KOL Analysis page"""
    st.markdown('<h1 class="main-header">🔬 KOL Analysis & Scoring</h1>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        zone = st.selectbox("Zone", ["All Zones", "Jakarta", "Bali-Lombok", "Jawa Barat"])
    with col2:
        category = st.selectbox("Category", ["All Categories", "Food", "Technology", "Lifestyle"])
    with col3:
        min_score = st.slider("Minimum Score", 0, 100, 70)
    
    st.divider()
    
    with st.expander("📊 Scoring Methodology", expanded=False):
        st.markdown("""
        **KOL Score Calculation:**
        1. Engagement Rate (30%)
        2. Content Quality (25%)
        3. Audience Match (25%)
        4. Past Performance (20%)
        """)
    
    st.subheader("🎯 Recommended KOLs")
    
    analysis_data = [
        {
            'rank': 1,
            'name': 'Foodie Indonesia',
            'platform': 'Instagram',
            'engagement_score': 95,
            'content_score': 90,
            'audience_score': 92,
            'performance_score': 88,
            'total_score': 91.2,
            'estimated_cost': 'Rp 15M',
            'estimated_roi': '3.5x'
        }
    ]
    
    df_analysis = pd.DataFrame(analysis_data)
    st.dataframe(df_analysis, use_container_width=True)

def campaign_page():
    """Campaign Management page"""
    st.markdown('<h1 class="main-header">📢 Campaign Management</h1>', unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["Active Campaigns", "Draft Campaigns", "Create New"])
    
    with tab1:
        st.subheader("Active Campaigns")
        campaigns_data = [
            {
                'name': 'Summer Sale 2024',
                'start_date': '2024-06-01',
                'end_date': '2024-06-30',
                'budget': 'Rp 50M',
                'status': 'In Progress',
                'kols_count': 12
            }
        ]
        df_campaigns = pd.DataFrame(campaigns_data)
        st.dataframe(df_campaigns, use_container_width=True)
    
    with tab2:
        st.subheader("Draft Campaigns")
        st.info("No draft campaigns")
    
    with tab3:
        st.subheader("Create New Campaign")
        with st.form("campaign_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Campaign Name")
                start_date = st.date_input("Start Date")
                budget = st.number_input("Budget (in millions)", min_value=0)
            with col2:
                category = st.selectbox("Category", ["Product Launch", "Seasonal Sale", "Brand Awareness"])
                end_date = st.date_input("End Date")
                objective = st.text_area("Campaign Objective")
            
            submitted = st.form_submit_button("Create Campaign", type="primary")
            if submitted:
                st.success("Campaign created successfully!")

def logout():
    """Logout function"""
    st.session_state.user = None
    st.session_state.logged_in = False
    st.session_state.page = 'login'
    st.rerun()

# Main app logic
def main():
    # Check database connection
    if st.session_state.page != 'login' and not DB_URL:
        st.error("⚠️ DATABASE_URL not set! Please set environment variable in Streamlit Cloud Settings.")
        st.info("To fix: Go to Settings → Secrets → Add DATABASE_URL")
        return
    
    # Sidebar navigation
    if st.session_state.logged_in:
        with st.sidebar:
            st.title("🎯 KOL Hub")
            st.divider()
            
            page = st.radio(
                "Navigation",
                ["Dashboard", "KOL Database", "KOL Analysis", "Campaigns"],
                label_visibility="collapsed"
            )
            
            st.divider()
            
            if st.button("🚪 Logout", use_container_width=True):
                logout()
        
        # Page routing
        if page == "Dashboard":
            dashboard_page()
        elif page == "KOL Database":
            kol_database_page()
        elif page == "KOL Analysis":
            kol_analysis_page()
        elif page == "Campaigns":
            campaign_page()
    else:
        login_page()

if __name__ == "__main__":
    main()
