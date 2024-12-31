import streamlit as st
import pandas as pd
from datetime import datetime
import json
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
import time

# Google Sheets document IDs and ranges

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
        st.error("No data found in the specified range.")
        return pd.DataFrame()

    headers = values[0]
    data = values[1:]

    # Ensure all rows have the same number of columns as headers
    data = [row + [""] * (len(headers) - len(row)) for row in data]

    # Create DataFrame
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

# Login helper function
def check_login(username, password):
    nhanvien_df = st.session_state['nhanvien_df']
    user = nhanvien_df[(nhanvien_df['taiKhoan'].astype(str) == str(username)) & 
                       (nhanvien_df['matKhau'].astype(str) == str(password))]
    if not user.empty:
        return user.iloc[0]
    return None

# Display all leaves with highlighting for approved ones
def display_all_leaves():
    leave_df = fetch_sheet_data(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE)

    # Ensure required columns exist
    required_columns = ['maNVYT', 'tenNhanVien', 'ngayDangKy', 'loaiPhep', 'thoiGianDangKy', 'DuyetPhep']
    for col in required_columns:
        if col not in leave_df.columns:
            leave_df[col] = ""  # Add missing columns with default values

    # Rename columns for display
    leave_df = leave_df.rename(columns={
        'tenNhanVien': 'Họ tên',
        'ngayDangKy': 'Ngày đăng ký',
        'loaiPhep': 'Loại phép',
        'thoiGianDangKy': 'Thời gian đăng ký',
        'DuyetPhep': 'Duyệt'
    })

    # Highlight approved leaves
    def highlight_approved(row):
        return ['background-color: lightgreen' if row['Duyệt'] == '1' else '' for _ in row]

    st.write("### Danh sách đăng ký phép:")
    if not leave_df.empty:
        styled_df = leave_df[['Họ tên', 'Ngày đăng ký', 'Loại phép', 'Thời gian đăng ký', 'Duyệt']].style.apply(highlight_approved, axis=1)
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.write("Không có đăng ký phép nào.")


# Display user's leaves with the ability to cancel
def display_user_leaves():
    # Fetch leave data
    leave_df = fetch_sheet_data(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE)
    user_info = st.session_state['user_info']

    # Ensure the `maNVYT` column exists and filter data by the logged-in user's `maNVYT`
    if 'maNVYT' in leave_df.columns:
        # Convert both to strings for consistent comparison
        leave_df['maNVYT'] = leave_df['maNVYT'].astype(str)
        user_maNVYT = str(user_info['maNVYT'])
        user_leaves = leave_df[leave_df['maNVYT'] == user_maNVYT]
    else:
        st.error("Column 'maNVYT' is missing in the Google Sheet.")
        return

    st.write("### Danh sách phép của bạn:")
    if not user_leaves.empty:
        # Rename columns for display
        user_leaves = user_leaves.rename(columns={
            'tenNhanVien': 'Họ tên',
            'ngayDangKy': 'Ngày đăng ký',
            'loaiPhep': 'Loại phép',
            'thoiGianDangKy': 'Thời gian đăng ký',
            'DuyetPhep': 'Duyệt',
            'HuyPhep': 'Hủy phép'
        })

        # Display user's leaves
        st.dataframe(user_leaves[['Họ tên', 'Ngày đăng ký', 'Loại phép', 'Thời gian đăng ký', 'Duyệt', 'Hủy phép']], use_container_width=True)

        # Allow the user to cancel a maximum of 2 leaves
        canceled_count = user_leaves[user_leaves['Hủy phép'] == '1'].shape[0]
        if canceled_count < 2:
            st.write(f"Bạn có thể hủy thêm {2 - canceled_count} lần.")
            
            # Ensure valid selection for cancellation
            if not user_leaves.empty:
                cancel_row = st.selectbox(
                    "Chọn dòng để hủy:",
                    user_leaves.index,
                    format_func=lambda x: f"Ngày đăng ký: {user_leaves.loc[x, 'Ngày đăng ký']}"
                )

                if st.button("Hủy phép"):
                    leave_df.at[cancel_row, 'HuyPhep'] = '1'
                    leave_df.at[cancel_row, 'nguoiHuy'] = user_maNVYT

                    # Update Google Sheet
                    body = {'values': leave_df.values.tolist()}
                    sheets_service.spreadsheets().values().update(
                        spreadsheetId=LEAVE_SHEET_ID,
                        range=LEAVE_SHEET_RANGE,
                        valueInputOption="RAW",
                        body=body
                    ).execute()
                    st.success("Đã hủy phép thành công.")
        else:
            st.warning("Bạn đã đạt giới hạn hủy phép.")
    else:
        st.write("Không có phép nào được đăng ký bởi bạn.")



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

    # Define pages
    pages = ["Danh sách đăng ký phép", "Phép của tôi", "Đăng ký phép mới"]
    if role == "admin":
        pages.append("Duyệt phép")

    # Sidebar navigation
    page = st.sidebar.radio("", pages)

    if page == "Danh sách đăng ký phép":
        st.title("Danh sách đăng ký phép")
        display_all_leaves()
    elif page == "Phép của tôi":
        st.title("Phép của tôi")
        display_user_leaves()
    elif page == "Đăng ký phép mới":
        st.title("Đăng ký phép mới")
        display_registration_form()
    elif page == "Duyệt phép" and role == "admin":
        st.title("Duyệt phép")
        admin_approval_page()

