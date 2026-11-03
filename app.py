"""
KOL Hub - Streamlit Application
Main application file for Streamlit Cloud deployment
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import os

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
# These will be replaced with environment variables in production
DB_URL = os.environ.get("DATABASE_URL", "postgresql://kolhub:kolhub_dev@localhost:5432/kolhub")

def login_page():
    """Login page"""
    st.markdown('<h1 class="main-header">🎯 KOL Hub</h1>', unsafe_allow_html=True)
    st.markdown('<p style="font-size: 1.2rem; color: #666;">Mitra10 Digital Marketing Platform</p>', unsafe_allow_html=True)

    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.subheader("🔐 Login")

        email = st.text_input("Email", placeholder="contoh: superuser@mitra10.co.id")
        password = st.text_input("Password", type="password")

        col_a, col_b, col_c = st.columns([1, 2, 1])
        with col_b:
            if st.button("Login", use_container_width=True, type="primary"):
                # For demo purposes, accept any email/password
                # In production, this should validate against database
                if email and password:
                    st.session_state.user = {
                        'name': 'Super User',
                        'email': email,
                        'role': 'super_user'
                    }
                    st.session_state.logged_in = True
                    st.session_state.page = 'dashboard'
                    st.rerun()
                else:
                    st.error("Please enter email and password")

        st.markdown("---")
        st.info("💡 For demo: Enter any email and password to login")

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
        st.info("Campaign performance chart will be displayed here")
        # Placeholder for chart
        df_chart = pd.DataFrame({
            'Month': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
            'Engagement': [3.2, 3.8, 4.1, 4.5, 4.7, 4.8]
        })
        st.line_chart(df_chart.set_index('Month'))

    with col2:
        st.subheader("🎯 Top Performing KOLs")
        st.info("Top KOLs table will be displayed here")
        # Placeholder for table
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

    # Search and filter
    col1, col2, col3 = st.columns(3)
    with col1:
        search = st.text_input("🔍 Search KOL", placeholder="Name, username, or platform")
    with col2:
        platform = st.selectbox("Platform", ["All", "Instagram", "TikTok", "Portal News"])
    with col3:
        status = st.selectbox("Status", ["All", "Active", "Blocked"])

    st.divider()

    # KOL list
    st.subheader("KOL Accounts")

    # Sample data - in production, this would come from database
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
        },
        {
            'name': 'Lifestyle Vlogger',
            'platform': 'Instagram',
            'username': '@lifestyleid',
            'followers': '2.1M',
            'engagement': '4.1%',
            'category': 'Lifestyle',
            'status': 'Active',
            'score': 88
        }
    ]

    df_kols = pd.DataFrame(kols_data)

    # Display with styling
    for idx, row in df_kols.iterrows():
        with st.expander(f"{row['name']} - {row['platform']} ({row['username']})"):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Followers", row['followers'])
            col2.metric("Engagement", row['engagement'])
            col3.metric("Category", row['category'])
            col4.metric("Score", row['score'])

            col_a, col_b = st.columns(2)
            with col_a:
                st.button(f"View Details - {row['name']}", key=f"view_{idx}")
            with col_b:
                st.button(f"Edit - {row['name']}", key=f"edit_{idx}")

    # Add new KOL button
    st.divider()
    if st.button("➕ Add New KOL", use_container_width=True, type="primary"):
        st.info("Add KOL form will be displayed here")

def kol_analysis_page():
    """KOL Analysis page"""
    st.markdown('<h1 class="main-header">🔬 KOL Analysis & Scoring</h1>', unsafe_allow_html=True)

    # Analysis parameters
    col1, col2, col3 = st.columns(3)
    with col1:
        zone = st.selectbox("Zone", ["All Zones", "Jakarta", "Bali-Lombok", "Jawa Barat"])
    with col2:
        category = st.selectbox("Category", ["All Categories", "Food", "Technology", "Lifestyle"])
    with col3:
        min_score = st.slider("Minimum Score", 0, 100, 70)

    st.divider()

    # Scoring methodology
    with st.expander("📊 Scoring Methodology", expanded=False):
        st.markdown("""
        **KOL Score Calculation:**

        1. **Engagement Rate (30%)**
           - Average likes + comments / followers
           - Weight: 30%

        2. **Content Quality (25%)**
           - Relevance to brand
           - Professionalism
           - Creativity
           - Weight: 25%

        3. **Audience Match (25%)**
           - Demographic alignment
           - Geographic relevance
           - Interest matching
           - Weight: 25%

        4. **Past Performance (20%)**
           - Historical campaign results
           - Delivery reliability
           - ROI track record
           - Weight: 20%
        """)

    # Analysis results
    st.subheader("🎯 Recommended KOLs")

    # Sample analysis results
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
        },
        {
            'rank': 2,
            'name': 'Tech Review ID',
            'platform': 'TikTok',
            'engagement_score': 88,
            'content_score': 92,
            'audience_score': 85,
            'performance_score': 90,
            'total_score': 88.8,
            'estimated_cost': 'Rp 12M',
            'estimated_roi': '3.2x'
        },
        {
            'rank': 3,
            'name': 'Lifestyle Vlogger',
            'platform': 'Instagram',
            'engagement_score': 85,
            'content_score': 88,
            'audience_score': 90,
            'performance_score': 85,
            'total_score': 87.0,
            'estimated_cost': 'Rp 18M',
            'estimated_roi': '2.8x'
        }
    ]

    df_analysis = pd.DataFrame(analysis_data)
    st.dataframe(df_analysis, use_container_width=True)

    # Action buttons
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.button("📥 Export to Excel", use_container_width=True)
    with col2:
        st.button("📊 Run Full Analysis", use_container_width=True, type="primary")
    with col3:
        st.button("🔄 Refresh Data", use_container_width=True)

def campaign_page():
    """Campaign Management page"""
    st.markdown('<h1 class="main-header">📢 Campaign Management</h1>', unsafe_allow_html=True)

    # Campaign tabs
    tab1, tab2, tab3 = st.tabs(["Active Campaigns", "Draft Campaigns", "Create New"])

    with tab1:
        st.subheader("Active Campaigns")
        st.info("Active campaigns will be displayed here")

        campaigns_data = [
            {
                'name': 'Summer Sale 2024',
                'start_date': '2024-06-01',
                'end_date': '2024-06-30',
                'budget': 'Rp 50M',
                'status': 'In Progress',
                'kols_count': 12
            },
            {
                'name': 'New Product Launch',
                'start_date': '2024-07-01',
                'end_date': '2024-07-15',
                'budget': 'Rp 30M',
                'status': 'Planning',
                'kols_count': 8
            }
        ]

        df_campaigns = pd.DataFrame(campaigns_data)
        st.dataframe(df_campaigns, use_container_width=True)

    with tab2:
        st.subheader("Draft Campaigns")
        st.info("Draft campaigns will be displayed here")

    with tab3:
        st.subheader("Create New Campaign")
        with st.form("campaign_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Campaign Name")
                start_date = st.date_input("Start Date")
                budget = st.number_input("Budget (in millions)", min_value=0)
            with col2:
                category = st.selectbox("Category", ["Product Launch", "Seasonal Sale", "Brand Awareness", "Other"])
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
