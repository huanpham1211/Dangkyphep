import streamlit as st
import pandas as pd
from datetime import datetime
import json
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
import time

# Google Sheets document IDs and ranges
KPI_SHEET_ID = '1f38fTxOkuP2PFKDSyrxp1aRXi8iz9rZqMJesDkJjC14'
KPI_SHEET_RANGE = 'Sheet1'

REGISTRATION_SHEET_ID = '1Cq6J5gOqErerq4M4JqkwiE5aOC-bg1s6uqPB41_DzXs'
REGISTRATION_SHEET_RANGE = 'Sheet1'

NHANVIEN_SHEET_ID = '1kzfwjA0nVLFoW8T5jroLyR2lmtdZp8eaYH-_Pyb0nbk'
NHANVIEN_SHEET_RANGE = 'Sheet1'

# Load Google credentials from Streamlit Secrets
google_credentials = st.secrets["GOOGLE_CREDENTIALS"]
credentials_info = json.loads(google_credentials)

# Authenticate using the service account credentials
credentials = service_account.Credentials.from_service_account_info(
    credentials_info,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

# Initialize the Google Sheets API client
sheets_service = build('sheets', 'v4', credentials=credentials)

# Function to fetch data from a Google Sheet
def fetch_sheet_data(sheet_id, range_name):
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=range_name
    ).execute()
    values = result.get('values', [])
    
    # Convert to DataFrame
    if not values:
        st.error("No data found.")
        return pd.DataFrame()
    else:
        headers = values[0]
        data = values[1:]
        return pd.DataFrame(data, columns=headers)

# Function to append data to a Google Sheet
def append_to_sheet(sheet_id, range_name, values):
    body = {'values': values}
    sheets_service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()

# Load Google Sheets data into Streamlit session state
if 'nhanvien_df' not in st.session_state:
    st.session_state['nhanvien_df'] = fetch_sheet_data(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)

if 'kpitarget_df' not in st.session_state:
    st.session_state['kpitarget_df'] = fetch_sheet_data(KPI_SHEET_ID, KPI_SHEET_RANGE)

if 'registration_df' not in st.session_state:
    st.session_state['registration_df'] = fetch_sheet_data(REGISTRATION_SHEET_ID, REGISTRATION_SHEET_RANGE)

# Helper function to check login
def check_login(username, password):
    nhanvien_df = st.session_state['nhanvien_df']
    user = nhanvien_df[(nhanvien_df['taiKhoan'].astype(str) == str(username)) & 
                       (nhanvien_df['matKhau'].astype(str) == str(password))]
    return user if not user.empty else None

# Function to display the user's registered targets
def display_user_registrations():
    st.session_state['registration_df'] = fetch_sheet_data(REGISTRATION_SHEET_ID, REGISTRATION_SHEET_RANGE)
    registration_df = st.session_state['registration_df']
    user_registrations = registration_df[registration_df['maNVYT'] == str(st.session_state['user_info']['maNVYT'])]

    st.write("### Chỉ tiêu đã đăng ký:")
    if not user_registrations.empty:
        user_registrations = user_registrations.rename(columns={'Target': 'Chỉ tiêu', 'TimeStamp': 'Thời gian đăng ký'})
        st.dataframe(user_registrations[['Chỉ tiêu', 'Thời gian đăng ký']].style.set_table_styles([
            {'selector': 'th', 'props': [('font-size', '14px'), ('text-align', 'center')]},
            {'selector': 'td', 'props': [('font-size', '14px'), ('text-align', 'left')]}
        ]), width=800)
    else:
        st.write("Bạn chưa đăng ký chỉ tiêu nào!")

# Function to display the registration form
def display_registration_form():
    user_info = st.session_state['user_info']
    kpitarget_df = st.session_state['kpitarget_df']
    registration_df = st.session_state['registration_df']

    # Calculate remaining registration slots for each target
    target_slots = {}
    for _, row in kpitarget_df.iterrows():
        target = row['Target']
        max_reg = int(row['MaxReg'])
        registered_count = registration_df[registration_df['Target'] == target].shape[0]
        remaining_slots = max_reg - registered_count
        target_slots[target] = remaining_slots

    # Determine already registered targets by the user
    registered_targets = registration_df[registration_df['maNVYT'] == str(user_info['maNVYT'])]['Target'].tolist()

    # Display available targets with remaining slots as wide checkboxes
    st.write("### Chọn chỉ tiêu (Số vị trí còn lại):")
    selected_targets = []
    for target, remaining_slots in target_slots.items():
        if remaining_slots > 0 and target not in registered_targets:
            label = f"{target} ({remaining_slots} vị trí trống còn lại)"
            is_selected = st.checkbox(label, key=f"target_{target}")
            if is_selected:
                selected_targets.append(target)

    # Enforce a maximum of 2 registrations
    if len(registered_targets) + len(selected_targets) > 2:
        st.error("Bạn chỉ có thể đăng ký tối đa 2 chỉ tiêu.")
        return

    # Confirmation dialog before registration
    if selected_targets:
        confirmation = st.radio("Bạn có muốn đăng ký chỉ tiêu đã chọn (Lưu ý không thể hủy chỉ tiêu đã đăng ký)?", ("Không", "Có"))

        if confirmation == "Có" and st.button("Xác nhận đăng ký"):
            # Get Vietnam timezone-aware timestamp
            vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
            timestamp = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

            # Prepare new registration entries
            new_registrations = [
                [
                    int(user_info['maNVYT']),
                    user_info['tenNhanVien'],
                    target,
                    timestamp
                ]
                for target in selected_targets
            ]

            # Append to Google Sheets
            try:
                append_to_sheet(REGISTRATION_SHEET_ID, REGISTRATION_SHEET_RANGE, new_registrations)
                st.success("Đăng ký thành công!")
                st.session_state['page'] = "CHỈ TIÊU KPI ĐÃ ĐĂNG KÝ"
            except Exception as e:
                st.error(f"Lỗi khi ghi dữ liệu vào Google Sheets: {e}")



# Check for login and show the login section if the user is not logged in
if not st.session_state.get('is_logged_in', False):
    st.title("Đăng nhập")
    username = st.text_input("Tài khoản")
    password = st.text_input("Mật khẩu", type="password")
    
    login_button = st.button("Login")
    if login_button:
        # Display loading message and check credentials
        with st.spinner("Logging in, please wait..."):
            time.sleep(1)  # Simulate loading time
            user = check_login(username, password)
            if user is not None:
                st.session_state['user_info'] = {
                    "maNVYT": user.iloc[0]["maNVYT"],
                    "tenNhanVien": user.iloc[0]["tenNhanVien"],
                    "chucVu": user.iloc[0]["chucVu"]
                }
                st.session_state['is_logged_in'] = True
                st.session_state['show_sidebar'] = True
                st.sidebar.success("Đăng nhập thành công")  # Show successful login in sidebar
            else:
                st.error("Sai tên tài khoản hoặc mật khẩu")
else:
    # Display sidebar after login
    if st.session_state.get('show_sidebar', False):
        # Sidebar navigation
        page = st.sidebar.radio("", ["CHỈ TIÊU KPI ĐÃ ĐĂNG KÝ", "ĐĂNG KÝ MỚI"])
        
        # Display content based on selected tab
        if page == "CHỈ TIÊU KPI ĐÃ ĐĂNG KÝ":
            st.title("CHỈ TIÊU KPI ĐÃ ĐĂNG KÝ")
            display_user_registrations()
        elif page == "ĐĂNG KÝ MỚI":
            st.title("ĐĂNG KÝ MỚI")
            display_registration_form()

# Footer at the sidebar with developer information
st.sidebar.markdown("---")
st.sidebar.markdown("<div style='text-align: center; font-size: small;'>Developed by HuanPham</div>", unsafe_allow_html=True)
