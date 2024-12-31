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

    # Convert `ngayDangKy` to datetime for filtering and sorting
    leave_df['ngayDangKy'] = pd.to_datetime(leave_df['ngayDangKy'], errors='coerce')

    # Horizontal layout for date filters
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Ngày bắt đầu", value=pd.Timestamp.now().normalize(), key="start_date")
    with col2:
        end_date = st.date_input(
            "Ngày kết thúc",
            value=(pd.Timestamp(start_date) + pd.DateOffset(months=6)).normalize(),
            key="end_date"
        )

    # Filter rows by the date range
    filtered_leaves = leave_df[
        (leave_df['ngayDangKy'] >= pd.to_datetime(start_date)) &
        (leave_df['ngayDangKy'] <= pd.to_datetime(end_date))
    ].sort_values(by='ngayDangKy', ascending=True)  # Sort by `ngayDangKy` ASC

    # Rename columns for display (apply to filtered_leaves)
    filtered_leaves = filtered_leaves.rename(columns={
        'tenNhanVien': 'Họ tên',
        'ngayDangKy': 'Ngày đăng ký',
        'loaiPhep': 'Loại phép',
        'thoiGianDangKy': 'Thời gian đăng ký',
        'DuyetPhep': 'Duyệt'
    })

    # Highlight approved leaves
    def highlight_approved(row):
        return ['background-color: lightgreen' if row['Duyệt'] == 'Duyệt' else '' for _ in row]

    st.write("### Danh sách đăng ký phép:")
    if not filtered_leaves.empty:
        styled_df = filtered_leaves[['Họ tên', 'Ngày đăng ký', 'Loại phép', 'Thời gian đăng ký', 'Duyệt']].style.apply(highlight_approved, axis=1)
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.write("Không có đăng ký phép nào trong khoảng thời gian này.")



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
        canceled_count = user_leaves[user_leaves['Hủy phép'] == 'Hủy'].shape[0]
        if canceled_count < 2:
            st.write(f"Bạn có thể hủy thêm {2 - canceled_count} lần.")
            
            # Allow user to select a leave to cancel
            if not user_leaves.empty:
                cancel_row = st.selectbox(
                    "Chọn dòng để hủy:",
                    user_leaves.index,
                    format_func=lambda x: f"Ngày đăng ký: {user_leaves.loc[x, 'Ngày đăng ký']}"
                )

                if st.button("Hủy phép"):
                    # Update the specific row in the Google Sheet
                    row_index = cancel_row + 2  # Account for 1-based indexing in Google Sheets and header row
                    sheets_service.spreadsheets().values().update(
                        spreadsheetId=LEAVE_SHEET_ID,
                        range=f"Sheet1!G{row_index}:H{row_index}",
                        valueInputOption="RAW",
                        body={"values": [["Hủy", user_maNVYT]]}  # Update HuyPhep and nguoiHuy columns
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
        
        # Ensure maNVYT is a string and matches exactly what is fetched
        new_registration = [
            [
                str(user_info['maNVYT']),  # Ensure maNVYT is stored as a string
                user_info['tenNhanVien'],
                str(registration_date),
                leave_type,
                timestamp,
                "",  # DuyetPhep column (default empty)
                "",  # HuyPhep column (default empty)
                ""   # nguoiHuy column (default empty)
            ]
        ]

        try:
            append_to_sheet(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE, new_registration)
            st.success("Đăng ký thành công!")
        except Exception as e:
            st.error(f"Lỗi khi ghi dữ liệu vào Google Sheets: {e}")

# Admin approval page
def admin_approval_page():
    # Fetch leave data
    leave_df = fetch_sheet_data(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE)

    # Ensure required columns exist
    required_columns = ['maNVYT', 'tenNhanVien', 'ngayDangKy', 'loaiPhep', 'thoiGianDangKy', 'DuyetPhep', 'HuyPhep']
    for col in required_columns:
        if col not in leave_df.columns:
            leave_df[col] = ""  # Add missing columns with default values

    # Convert `ngayDangKy` to datetime for filtering
    leave_df['ngayDangKy'] = pd.to_datetime(leave_df['ngayDangKy'], errors='coerce')

    # Side-by-side layout for date filters
    st.write("### Bộ lọc thời gian:")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Ngày bắt đầu", value=pd.Timestamp.now().normalize(), key="start_date")
    with col2:
        end_date = st.date_input(
            "Ngày kết thúc", 
            value=(pd.Timestamp.now() + pd.DateOffset(months=6)).normalize(),  # Default 6 months from now
            key="end_date"
        )

    # Filter rows where `DuyetPhep` and `HuyPhep` are empty, and `ngayDangKy` falls within the selected range
    filtered_leaves = leave_df[
        (leave_df['DuyetPhep'] == "") & 
        (leave_df['HuyPhep'] == "") & 
        (leave_df['ngayDangKy'] >= pd.to_datetime(start_date)) & 
        (leave_df['ngayDangKy'] <= pd.to_datetime(end_date))
    ].sort_values(by='ngayDangKy', ascending=True)  # Sort by `ngayDangKy` ASC

    st.write("### Danh sách đăng ký phép (Chưa duyệt):")
    if not filtered_leaves.empty:
        # Iterate over rows to display with a "Duyệt" button for each row
        for index, row in filtered_leaves.iterrows():
            # Display the row information
            st.write(f"""
                **Họ tên:** {row['tenNhanVien']}  
                **Ngày đăng ký:** {row['ngayDangKy'].strftime('%Y-%m-%d')}  
                **Loại phép:** {row['loaiPhep']}  
                **Thời gian đăng ký:** {row['thoiGianDangKy']}
            """)

            # "Duyệt" button
            if st.button("Duyệt", key=f"approve_{index}"):
                # Update the specific row in the Google Sheet
                row_index = index + 2  # Account for 1-based indexing in Google Sheets and header row
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=LEAVE_SHEET_ID,
                    range=f"Sheet1!F{row_index}:F{row_index}",
                    valueInputOption="RAW",
                    body={"values": [["Duyệt"]]} 
                ).execute()
                st.success(f"Duyệt thành công cho {row['tenNhanVien']}")

                # Re-fetch data to show updated table without refreshing the page
                leave_df = fetch_sheet_data(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE)
                leave_df['ngayDangKy'] = pd.to_datetime(leave_df['ngayDangKy'], errors='coerce')
                filtered_leaves = leave_df[
                    (leave_df['DuyetPhep'] == "") & 
                    (leave_df['HuyPhep'] == "") & 
                    (leave_df['ngayDangKy'] >= pd.to_datetime(start_date)) & 
                    (leave_df['ngayDangKy'] <= pd.to_datetime(end_date))
                ].sort_values(by='ngayDangKy', ascending=True)  # Re-apply filters
    else:
        st.write("Không có đăng ký phép nào trong khoảng thời gian này.")




# Main app logic
if not st.session_state.get('is_logged_in', False):
    st.title("Đăng nhập")
    username = st.text_input("Tài khoản")
    password = st.text_input("Mật khẩu", type="password")
    
    if st.button("Login"):
        with st.spinner("Logging in, please wait..."):
            time.sleep(1)
            # Fetch the user
            user = check_login(username, password)
            if user is not None:
                # Ensure maNVYT is handled as a string
                st.session_state['user_info'] = {
                    "maNVYT": str(user["maNVYT"]),  # Preserve as string
                    "tenNhanVien": user["tenNhanVien"],
                    "chucVu": user["chucVu"]
                }
                st.session_state['is_logged_in'] = True
                st.sidebar.success("Đăng nhập thành công")
            else:
                st.error("Sai tên tài khoản hoặc mật khẩu")
else:
    # Display greeting at the top of the main page
    user_info = st.session_state['user_info']
    role = user_info.get('chucVu', '').lower()  # Default to empty string if chucVu is missing
    
    st.sidebar.write(f"Xin chào, **{user_info['tenNhanVien']}**")

    # Logout button
    if st.sidebar.button("Đăng xuất"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]  # Clear all session state keys
        st.sidebar.write("Bạn đã đăng xuất. Làm mới trang để đăng nhập lại.")
        st.stop()  # Stop the app to ensure the session is cleared

    # Define pages
    pages = ["Danh sách đăng ký phép", "Phép của tôi", "Đăng ký phép mới"]
    if role == "admin":
        pages.append("Duyệt phép")

    # Sidebar navigation
    page = st.sidebar.radio("Chọn trang", pages)

    # Page navigation logic
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

    # Footer
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='text-align: center; font-size: small;'>Developed by HuanPham</div>",
        unsafe_allow_html=True
    )




