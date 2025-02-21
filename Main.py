import streamlit as st
import pandas as pd
from datetime import datetime
import json
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import time
import locale


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


def fetch_sheet_data(sheet_id, range_name, max_retries=3, cache_time=60):
    """Fetch Google Sheets data with caching and error handling."""
    
    # Use session state to cache the data
    cache_key = f"sheet_data_{sheet_id}_{range_name}"
    if cache_key in st.session_state and time.time() - st.session_state[cache_key]["timestamp"] < cache_time:
        return st.session_state[cache_key]["data"]

    attempt = 0
    while attempt < max_retries:
        try:
            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            values = result.get('values', [])

            if not values:
                st.warning("⚠️ Không tìm thấy dữ liệu trong phạm vi được chỉ định.")
                return pd.DataFrame()

            headers = values[0]
            data = values[1:]
            data = [row + [""] * (len(headers) - len(row)) for row in data]

            df = pd.DataFrame(data, columns=headers)

            # Cache the result in session state
            st.session_state[cache_key] = {"data": df, "timestamp": time.time()}
            return df

        except HttpError as e:
            attempt += 1
            if "RATE_LIMIT_EXCEEDED" in str(e):
                wait_time = 10  # Wait longer to avoid rate limit
                st.warning(f"🔄 Quota exceeded. Thử lại sau {wait_time} giây...")
                time.sleep(wait_time)
            else:
                st.error(f"❌ Lỗi API: {e}")
                return pd.DataFrame()

    return pd.DataFrame()  # Return empty DataFrame if all retries fail




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
    required_columns = ['maNVYT', 'tenNhanVien', 'ngayDangKy', 'loaiPhep', 'thoiGianDangKy', 'DuyetPhep', 'HuyPhep']
    for col in required_columns:
        if col not in leave_df.columns:
            leave_df[col] = ""  # Add missing columns with default values

    # Convert `ngayDangKy` and `thoiGianDangKy` to datetime for filtering and formatting
    leave_df['ngayDangKy'] = pd.to_datetime(leave_df['ngayDangKy'], errors='coerce')
    leave_df['thoiGianDangKy'] = pd.to_datetime(leave_df['thoiGianDangKy'], errors='coerce')

    # Filter out rows where `HuyPhep` is not empty
    leave_df = leave_df[leave_df['HuyPhep'].isnull() | (leave_df['HuyPhep'] == "")]

    # Horizontal layout for date filters
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Ngày bắt đầu", 
            value=pd.Timestamp.now().normalize(), 
            key="start_date"
        )
    with col2:
        end_date = st.date_input(
            "Ngày kết thúc",
            value=(pd.Timestamp(start_date) + pd.DateOffset(months=6)).normalize(),
            key="end_date"
        )

    # Filter rows by the date range
    filtered_leaves = leave_df[
        (leave_df['ngayDangKy'] >= pd.Timestamp(start_date)) &
        (leave_df['ngayDangKy'] <= pd.Timestamp(end_date))
    ].sort_values(by=['ngayDangKy', 'thoiGianDangKy'], ascending=[True, True])  # Sort by `ngayDangKy` and then `thoiGianDangKy` ASC


    # Format dates as `dd/mm/yyyy`
    filtered_leaves['ngayDangKy'] = filtered_leaves['ngayDangKy'].dt.strftime('%d/%m/%Y')
    filtered_leaves['thoiGianDangKy'] = filtered_leaves['thoiGianDangKy'].dt.strftime('%d/%m/%Y %H:%M:%S')

    # Rename columns for display (apply to filtered_leaves)
    filtered_leaves = filtered_leaves.rename(columns={
        'tenNhanVien': 'Họ tên',
        'ngayDangKy': 'Ngày đăng ký',
        'loaiPhep': 'Loại phép',
        'thoiGianDangKy': 'Thời gian đăng ký',
        'DuyetPhep': 'Duyệt'
    })

    # Highlight approved and rejected leaves
    def highlight_approved(row):
        if row['Duyệt'] == 'Duyệt':
            return ['background-color: lightgreen' for _ in row]
        elif row['Duyệt'] == 'Không duyệt':
            return ['background-color: lightcoral' for _ in row]  # Light red background
        else:
            return ['' for _ in row]  # No background

    # Display filtered table
    if not filtered_leaves.empty:
        styled_df = filtered_leaves[
            ['Họ tên', 'Ngày đăng ký', 'Loại phép', 'Thời gian đăng ký', 'Duyệt']
        ].style.apply(highlight_approved, axis=1)

        # Make the table larger
        st.dataframe(styled_df, use_container_width=True, hide_index = True, height=600)
    else:
        st.write("Không có đăng ký phép nào trong khoảng thời gian này.")



# Display user's leaves with the ability to cancel
def display_user_leaves():
    # Fetch leave data
    leave_df = fetch_sheet_data(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE)
    user_info = st.session_state['user_info']

    # Ensure the maNVYT column exists and filter data by the logged-in user's maNVYT
    if 'maNVYT' in leave_df.columns:
        # Convert both to strings for consistent comparison
        leave_df['maNVYT'] = leave_df['maNVYT'].astype(str)
        user_maNVYT = str(user_info['maNVYT'])
        user_leaves = leave_df[leave_df['maNVYT'] == user_maNVYT]
    else:
        st.error("Column 'maNVYT' is missing in the Google Sheet.")
        return

    if not user_leaves.empty:
        # Convert 'ngayDangKy' to datetime format
        user_leaves['ngayDangKy'] = pd.to_datetime(user_leaves['ngayDangKy'], errors='coerce')

        # Filter out rows where 'ngayDangKy' could not be converted
        user_leaves = user_leaves[user_leaves['ngayDangKy'].notna()]

        # Format 'ngayDangKy' as dd/MM/yyyy
        user_leaves['ngayDangKy_display'] = user_leaves['ngayDangKy'].dt.strftime('%d/%m/%Y')

        # Rename columns for display
        user_leaves = user_leaves.rename(columns={
            'tenNhanVien': 'Họ tên',
            'ngayDangKy_display': 'Ngày đăng ký',
            'loaiPhep': 'Loại phép',
            'thoiGianDangKy': 'Thời gian đăng ký',
            'DuyetPhep': 'Duyệt',
            'HuyPhep': 'Hủy phép',
            'nguoiHuy': 'Người hủy'
        })

        # Date filter
        st.write("### Lọc theo thời gian:")
        col1, col2 = st.columns(2)
        current_year = pd.Timestamp.now().year
        with col1:
            start_date = st.date_input(
                "Ngày bắt đầu",
                value=pd.Timestamp(year=current_year, month=1, day=1),
                key="start_date"
            )
        with col2:
            end_date = st.date_input(
                "Ngày kết thúc",
                value=pd.Timestamp(year=current_year, month=12, day=31),
                key="end_date"
            )

        # Filter leaves within the selected date range
        filtered_leaves = user_leaves[
            (user_leaves['ngayDangKy'] >= pd.Timestamp(start_date)) &
            (user_leaves['ngayDangKy'] <= pd.Timestamp(end_date))
        ]

        # Display filtered leaves
        st.write("### Danh sách phép của bạn:")
        if not filtered_leaves.empty:
            st.dataframe(
                filtered_leaves[['Họ tên', 'Ngày đăng ký', 'Loại phép', 'Thời gian đăng ký', 'Duyệt', 'Hủy phép']],
                use_container_width=True, hide_index = True
            )
        else:
            st.write("Không có phép nào được đăng ký trong khoảng thời gian này.")

        # Calculate max cancellations for the first and second 6-month periods
        first_half_start = pd.Timestamp(year=current_year, month=1, day=1)
        first_half_end = pd.Timestamp(year=current_year, month=6, day=30)
        second_half_start = pd.Timestamp(year=current_year, month=7, day=1)
        second_half_end = pd.Timestamp(year=current_year, month=12, day=31)

        # Count cancellations in each period
        first_half_cancellations = filtered_leaves[
            (filtered_leaves['Hủy phép'] == 'Hủy') &
            (filtered_leaves['Người hủy'] == user_maNVYT) &
            (filtered_leaves['ngayDangKy'] >= first_half_start) &
            (filtered_leaves['ngayDangKy'] <= first_half_end)
        ].shape[0]

        second_half_cancellations = filtered_leaves[
            (filtered_leaves['Hủy phép'] == 'Hủy') &
            (filtered_leaves['Người hủy'] == user_maNVYT) &
            (filtered_leaves['ngayDangKy'] >= second_half_start) &
            (filtered_leaves['ngayDangKy'] <= second_half_end)
        ].shape[0]

        max_cancellations_per_period = 2  # Easy to change cancellation limit here

        # Display cancellation limits for both periods
        if filtered_leaves['ngayDangKy'].between(first_half_start, first_half_end).any():
            st.write(
                f"Trong 6 tháng đầu năm, bạn đã hủy {first_half_cancellations} lần. "
                f"Bạn có thể hủy thêm {max(0, max_cancellations_per_period - first_half_cancellations)} lần."
            )

        if filtered_leaves['ngayDangKy'].between(second_half_start, second_half_end).any():
            st.write(
                f"Trong 6 tháng cuối năm, bạn đã hủy {second_half_cancellations} lần. "
                f"Bạn có thể hủy thêm {max(0, max_cancellations_per_period - second_half_cancellations)} lần."
            )

        # Allow user to cancel if within limit
        total_cancellations = first_half_cancellations + second_half_cancellations
        if total_cancellations < max_cancellations_per_period:
            # Filter leaves where 'Hủy phép' is empty
            cancellable_leaves = filtered_leaves[filtered_leaves['Hủy phép'].isnull() | (filtered_leaves['Hủy phép'] == "")]
            
            if not cancellable_leaves.empty:
                cancel_row = st.selectbox(
                    "Chọn dòng để hủy:",
                    cancellable_leaves.index,
                    format_func=lambda x: f"Ngày đăng ký: {cancellable_leaves.loc[x, 'Ngày đăng ký']}"
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
                    
                    # Refresh the data
                    leave_df = fetch_sheet_data(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE)
                    user_leaves = leave_df[leave_df['maNVYT'] == user_maNVYT]
                    
                    # Reapply filtering
                    user_leaves['ngayDangKy'] = pd.to_datetime(user_leaves['ngayDangKy'], errors='coerce')
                    user_leaves = user_leaves[user_leaves['ngayDangKy'].notna()]
                    user_leaves['ngayDangKy_display'] = user_leaves['ngayDangKy'].dt.strftime('%d/%m/%Y')
                    filtered_leaves = user_leaves[
                        (user_leaves['ngayDangKy'] >= pd.Timestamp(start_date)) &
                        (user_leaves['ngayDangKy'] <= pd.Timestamp(end_date))
                    ]
                    
                    # Refresh the displayed table
                    st.success("Đã hủy phép thành công.")
                    st.dataframe(
                        filtered_leaves[['Họ tên', 'Ngày đăng ký', 'Loại phép', 'Thời gian đăng ký', 'Duyệt', 'Hủy phép']],
                        use_container_width=True, hide_index=True
                    )

            else:
                st.warning("Không có phép nào có thể hủy.")
        else:
            st.warning("Bạn đã đạt giới hạn hủy phép trong giai đoạn này.")
    else:
        st.write("Không có phép nào được đăng ký bởi bạn.")



# Registration form for leaves
def display_registration_form():
    user_info = st.session_state['user_info']
    current_date = datetime.now().date()

    # Define allowed date ranges
    if current_date < datetime(current_date.year, 7, 1).date():
        min_date = datetime(current_date.year, 2, 1).date()
        max_date = datetime(current_date.year, 7, 31).date()
    else:
        min_date = datetime(current_date.year, 7, 1).date()
        max_date = datetime(current_date.year + 1, 1, 31).date()

    # Restrict date input to the defined range
    registration_date = st.date_input(
        "Ngày đăng ký",
        value=min_date,
        min_value=min_date,
        max_value=max_date,
        key="registration_date"
    )

    st.write("### Chọn loại phép:")
    leave_type = st.selectbox(
        "Loại phép",
        options=["Phép Ngày", "Phép Sáng", "Phép Chiều", "Bù Ngày", "Bù Sáng", "Bù Chiều"],
        key="leave_type"
    )

    if st.button("Xác nhận đăng ký"):
        # Re-validate the selected date
        if not (min_date <= registration_date <= max_date):
            st.error(
                f"Ngày đăng ký không hợp lệ. Vui lòng chọn trong khoảng từ {min_date.strftime('%d/%m/%Y')} đến {max_date.strftime('%d/%m/%Y')}."
            )
            return

        timestamp = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")

        # Fetch existing registrations to check for duplicates
        leave_df = fetch_sheet_data(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE)
        user_registrations = leave_df[
            (leave_df['maNVYT'] == str(user_info['maNVYT'])) &
            (leave_df['ngayDangKy'] == str(registration_date)) &
            (leave_df['loaiPhep'] == leave_type)
        ]

        if not user_registrations.empty:
            existing_dates = user_registrations['ngayDangKy'].tolist()
            st.warning(f"Bạn đã đăng ký {leave_type} cho ngày: {', '.join(existing_dates)}. Vui lòng kiểm tra lại.")
            return

        # New registration data
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
            st.error(f"Lỗi khi ghi dữ liệu: {e}")



# Admin approval page
def admin_approval_page():
    # Fetch leave data
    leave_df = fetch_sheet_data(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE)

    # Ensure required columns exist
    required_columns = ['maNVYT', 'tenNhanVien', 'ngayDangKy', 'loaiPhep', 'thoiGianDangKy', 'DuyetPhep', 'HuyPhep']
    for col in required_columns:
        if col not in leave_df.columns:
            leave_df[col] = ""  # Add missing columns with default values

    # Convert `ngayDangKy` and `thoiGianDangKy` to datetime for filtering and formatting
    leave_df['ngayDangKy'] = pd.to_datetime(leave_df['ngayDangKy'], errors='coerce')
    leave_df['thoiGianDangKy'] = pd.to_datetime(leave_df['thoiGianDangKy'], errors='coerce')

    # Format `ngayDangKy` as `dd/MM/yyyy` and `thoiGianDangKy` as `dd/MM/yyyy HH:mm:ss`
    leave_df['ngayDangKy_display'] = leave_df['ngayDangKy'].dt.strftime('%d/%m/%Y')
    leave_df['thoiGianDangKy_display'] = leave_df['thoiGianDangKy'].dt.strftime('%d/%m/%Y %H:%M:%S')

    # Side-by-side layout for date filters
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
        # Iterate over rows to display with "Duyệt" and "Không duyệt" buttons
        for index, row in filtered_leaves.iterrows():
            # Display the row information
            st.write(f"""
                **Họ tên:** {row['tenNhanVien']}  
                **Ngày đăng ký:** {row['ngayDangKy_display']}  
                **Loại phép:** {row['loaiPhep']}  
                **Thời gian đăng ký:** {row['thoiGianDangKy_display']}
            """)

            col1, col2 = st.columns(2)
            with col1:
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

            with col2:
                # "Không duyệt" button
                if st.button("Không duyệt", key=f"reject_{index}"):
                    # Update the specific row in the Google Sheet
                    row_index = index + 2  # Account for 1-based indexing in Google Sheets and header row
                    sheets_service.spreadsheets().values().update(
                        spreadsheetId=LEAVE_SHEET_ID,
                        range=f"Sheet1!F{row_index}:F{row_index}",
                        valueInputOption="RAW",
                        body={"values": [["Không duyệt"]]} 
                    ).execute()
                    st.success(f"Không duyệt thành công cho {row['tenNhanVien']}")

                # Re-fetch data to show updated table without refreshing the page
                leave_df = fetch_sheet_data(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE)
                leave_df['ngayDangKy'] = pd.to_datetime(leave_df['ngayDangKy'], errors='coerce')
                leave_df['thoiGianDangKy'] = pd.to_datetime(leave_df['thoiGianDangKy'], errors='coerce')
                leave_df['ngayDangKy_display'] = leave_df['ngayDangKy'].dt.strftime('%d/%m/%Y')
                leave_df['thoiGianDangKy_display'] = leave_df['thoiGianDangKy'].dt.strftime('%d/%m/%Y %H:%M:%S')
                filtered_leaves = leave_df[
                    (leave_df['DuyetPhep'] == "") & 
                    (leave_df['HuyPhep'] == "") & 
                    (leave_df['ngayDangKy'] >= pd.to_datetime(start_date)) & 
                    (leave_df['ngayDangKy'] <= pd.to_datetime(end_date))
                ].sort_values(by='ngayDangKy', ascending=True)  # Re-apply filters
    else:
        st.write("Không có đăng ký phép nào trong khoảng thời gian này.")



def admin_disapproved_leaves():
    # Fetch leave data
    leave_df = fetch_sheet_data(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE)
    nhanvien_df = fetch_sheet_data(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)

    # Ensure required columns exist
    required_columns = ['maNVYT', 'tenNhanVien', 'ngayDangKy', 'loaiPhep', 'thoiGianDangKy', 'DuyetPhep', 'HuyPhep', 'nguoiHuy']
    for col in required_columns:
        if col not in leave_df.columns:
            leave_df[col] = ""  # Add missing columns with default values

    # Convert `ngayDangKy` and `thoiGianDangKy` to datetime for formatting
    leave_df['ngayDangKy'] = pd.to_datetime(leave_df['ngayDangKy'], errors='coerce')
    leave_df['thoiGianDangKy'] = pd.to_datetime(leave_df['thoiGianDangKy'], errors='coerce')

    # Format dates as `dd/MM/yyyy` and `dd/MM/yyyy HH:mm:ss`
    leave_df['ngayDangKy_display'] = leave_df['ngayDangKy'].dt.strftime('%d/%m/%Y')
    leave_df['thoiGianDangKy_display'] = leave_df['thoiGianDangKy'].dt.strftime('%d/%m/%Y %H:%M:%S')

    # Filter rows where `DuyetPhep` is "Duyệt" and `HuyPhep` is empty
    approved_leaves = leave_df[
        (leave_df['DuyetPhep'] == 'Duyệt') & 
        (leave_df['HuyPhep'].isnull() | (leave_df['HuyPhep'] == ""))
    ]

    # Add filter for `tenNhanVien`
    st.write("### Lọc theo nhân viên:")
    employee_options = sorted(nhanvien_df['tenNhanVien'].unique().tolist())  # Fetch and sort all unique names
    employee_filter = st.selectbox("Chọn nhân viên", options=["Tất cả"] + employee_options, key="employee_filter")

    # Apply the employee filter
    if employee_filter != "Tất cả":
        approved_leaves = approved_leaves[approved_leaves['tenNhanVien'] == employee_filter]

    if not approved_leaves.empty:
        # Rename columns for display
        approved_leaves = approved_leaves.rename(columns={
            'tenNhanVien': 'Họ tên',
            'ngayDangKy_display': 'Ngày đăng ký',
            'loaiPhep': 'Loại phép',
            'thoiGianDangKy_display': 'Thời gian đăng ký',
            'DuyetPhep': 'Duyệt',
            'HuyPhep': 'Hủy phép'
        })

        # Iterate over rows to display with a "Hủy" button for each row
        for index, row in approved_leaves.iterrows():
            st.write(f"""
                **Họ tên:** {row['Họ tên']}  
                **Ngày đăng ký:** {row['Ngày đăng ký']}  
                **Loại phép:** {row['Loại phép']}  
                **Thời gian đăng ký:** {row['Thời gian đăng ký']}
            """)

            # "Hủy" button
            if st.button(f"Hủy phép cho {row['Họ tên']}", key=f"cancel_{index}"):
                # Update the specific row in the Google Sheet
                row_index = index + 2  # Account for 1-based indexing in Google Sheets and header row
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=LEAVE_SHEET_ID,
                    range=f"Sheet1!G{row_index}:H{row_index}",
                    valueInputOption="RAW",
                    body={"values": [["Hủy", st.session_state['user_info']['maNVYT']]]}  # Update HuyPhep and nguoiHuy columns
                ).execute()
                st.success(f"Hủy phép thành công cho {row['Họ tên']}.")

                # Re-fetch data to reflect the updated table
                leave_df = fetch_sheet_data(LEAVE_SHEET_ID, LEAVE_SHEET_RANGE)
                leave_df['ngayDangKy'] = pd.to_datetime(leave_df['ngayDangKy'], errors='coerce')
                leave_df['thoiGianDangKy'] = pd.to_datetime(leave_df['thoiGianDangKy'], errors='coerce')
                leave_df['ngayDangKy_display'] = leave_df['ngayDangKy'].dt.strftime('%d/%m/%Y')
                leave_df['thoiGianDangKy_display'] = leave_df['thoiGianDangKy'].dt.strftime('%d/%m/%Y %H:%M:%S')

                # Re-apply filters
                approved_leaves = leave_df[
                    (leave_df['DuyetPhep'] == 'Duyệt') & 
                    (leave_df['HuyPhep'].isnull() | (leave_df['HuyPhep'] == ""))
                ]
                if employee_filter != "Tất cả":
                    approved_leaves = approved_leaves[approved_leaves['tenNhanVien'] == employee_filter]
    else:
        st.write("Không có phép nào đã được duyệt.")


# Function to change password
def change_password():
    user_info = st.session_state['user_info']
    st.subheader("Thay đổi mật khẩu")
    
    # Input fields for old password, new password, and confirmation
    old_password = st.text_input("Mật khẩu cũ", type="password")
    new_password = st.text_input("Mật khẩu mới", type="password")
    confirm_password = st.text_input("Xác nhận mật khẩu mới", type="password")
    
    if st.button("Cập nhật mật khẩu"):
        # Fetch user info from the session state
        nhanvien_df = st.session_state['nhanvien_df']
        
        # Find the row corresponding to the current user's maNVYT
        user_row = nhanvien_df[nhanvien_df['maNVYT'] == user_info['maNVYT']]
        
        if not user_row.empty:
            # Validate old password
            if user_row.iloc[0]['matKhau'] == old_password:
                if new_password == confirm_password:
                    try:
                        # Find the row index in Google Sheets
                        row_index = user_row.index[0] + 2  # Add 2 for 1-based indexing and header row
                        
                        # Update the matKhau column in the Google Sheet
                        sheets_service.spreadsheets().values().update(
                            spreadsheetId=NHANVIEN_SHEET_ID,
                            range=f"Sheet1!D{row_index}",  # 'matKhau' is in column D
                            valueInputOption="RAW",
                            body={"values": [[new_password]]}
                        ).execute()
                        
                        st.success("Mật khẩu đã được thay đổi thành công!")
                        
                        # Refresh the session state to reflect the change
                        st.session_state['nhanvien_df'] = fetch_sheet_data(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)
                    except Exception as e:
                        st.error(f"Lỗi khi thay đổi mật khẩu: {e}")
                else:
                    st.error("Mật khẩu mới và xác nhận mật khẩu không khớp.")
            else:
                st.error("Mật khẩu cũ không đúng.")
        else:
            st.error("Không tìm thấy thông tin tài khoản.")


# Main app logic
if not st.session_state.get('is_logged_in', False):
    st.title("Đăng ký phép/bù - Khoa Xét nghiệm")
    username = st.text_input("Tài khoản", placeholder="e.g., 01234.bvhv")
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
                st.rerun()
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
    pages = ["Danh sách đăng ký phép", "Phép của tôi", "Đăng ký phép mới", "Thay đổi mật khẩu"]
    if role == "admin":
        pages.extend(["Duyệt phép", "Hủy duyệt phép"])  # Extend list for admin pages

    # Sidebar navigation
    page = st.sidebar.radio("Chọn trang", pages)

    # Page navigation logic
    if page == "Danh sách đăng ký phép":
        st.subheader("Danh sách đăng ký phép")  # Smaller than st.title
        display_all_leaves()
    elif page == "Phép của tôi":
        st.subheader("Phép của tôi")  # Smaller than st.title
        display_user_leaves()
    elif page == "Đăng ký phép mới":
        st.subheader("Đăng ký phép mới")  # Smaller than st.title
        display_registration_form()
    elif page == "Duyệt phép" and role == "admin":
        st.subheader("Duyệt phép")  # Smaller than st.title
        admin_approval_page()
    elif page == "Hủy duyệt phép" and role == "admin":
        st.subheader("Hủy duyệt phép")  # Smaller than st.title
        admin_disapproved_leaves()
    elif page == "Thay đổi mật khẩu":
        st.subheader("Thay đổi mật khẩu")  # Smaller than st.title
        change_password()

    # Footer
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='text-align: center; font-size: small;'>Developed by HuanPham</div>",
        unsafe_allow_html=True
    )




