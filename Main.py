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

LEAVE_SHEET_ID = '1WFaY0f6Mlkin5PE-l1KvN5sq0yteJfOSVwkzr_TYplo'
LEAVE_SHEET_RANGE = 'Sheet1'

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

# Login helper function
def check_login(username, password):
    nhanvien_df = st.session_state['nhanvien_df']
    user = nhanvien_df[(nhanvien_df['taiKhoan'].astype(str) == str(username)) & 
                       (nhanvien_df['matKhau'].astype(str) == str(password))]
    if not user.empty:
        return user.iloc[0]
    return None

# Display user registrations
def display_user_registrations():
    st.session_state['registration_df'] = fetch_sheet_data(REGISTRATION_SHEET_ID, REGISTRATION_SHEET_RANGE)
    registration_df = st.session_state['registration_df']
    user_registrations = registration_df[registration_df['maNVYT'] == str(st.session_state['user_info']['maNVYT'])]

    st.write("### Chỉ tiêu đã đăng ký:")
    if not user_registrations.empty:
        user_registrations = user_registrations.rename(columns={'Target': 'Chỉ tiêu', 'TimeStamp': 'Thời gian đăng ký'})
        st.dataframe(user_registrations[['Chỉ tiêu', 'Thời gian đăng ký']])
    else:
        st.write("Bạn chưa đăng ký chỉ tiêu nào!")

# Registration form for leaves
def display_registration_form():
    user_info = st.session_state['user_info']

    st.write("### Chọn ngày đăng ký:")
    registration_date = st.date_input("Ngày đăng ký", key="registration_date")

    st.write("### Chọn loại phép:")
    leave_type = st.selectbox("Loại phép", options=["Phép", "Bù"], key="leave_type")

    if st.button("Xác nhận đăng ký"):
        timestamp = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
        new_registration = [
            [
                int(user_info['maNVYT']),
                user_info['tenNhanVien'],
                str(registration_date),
                leave_type,
                timestamp
            ]
        ]
        try:
            append_to_sheet(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE, new_registration)
            st.success("Đăng ký thành công!")
        except Exception as e:
            st.error(f"Lỗi khi ghi dữ liệu vào Google Sheets: {e}")

# Admin approval page
def admin_approval_page():
    st.write("### Duyệt phép")
    st.write("Chức năng duyệt phép đang được phát triển.")

# Main app logic
if not st.session_state.get('is_logged_in', False):
    st.title("Đăng nhập")
    username = st.text_input("Tài khoản")
    password = st.text_input("Mật khẩu", type="password")
    
    if st.button("Login"):
        with st.spinner("Logging in, please wait..."):
            time.sleep(1)
            user = check_login(username, password)
            if user is not None:
                st.session_state['user_info'] = {
                    "maNVYT": user["maNVYT"],
                    "tenNhanVien": user["tenNhanVien"],
                    "chucVu": user["chucVu"]
                }
                st.session_state['is_logged_in'] = True
                st.sidebar.success("Đăng nhập thành công")
            else:
                st.error("Sai tên tài khoản hoặc mật khẩu")
else:
    user_info = st.session_state['user_info']
    role = user_info['chucVu']

    pages = ["CHỈ TIÊU KPI ĐÃ ĐĂNG KÝ", "ĐĂNG KÝ MỚI"]
    if role == "admin":
        pages.append("Duyệt phép")

    page = st.sidebar.radio("", pages)

    if page == "CHỈ TIÊU KPI ĐÃ ĐĂNG KÝ":
        st.title("CHỈ TIÊU KPI ĐÃ ĐĂNG KÝ")
        display_user_registrations()
    elif page == "ĐĂNG KÝ MỚI":
        st.title("ĐĂNG KÝ MỚI")
        display_registration_form()
    elif page == "Duyệt phép" and role == "admin":
        st.title("Duyệt phép")
        admin_approval_page()
