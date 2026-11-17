# Module Điểm Danh Sinh Viên (check_in_for_student)

Module này được thiết kế chuyên biệt dành riêng cho **Học viên / Sinh viên** tham gia các khóa học và sự kiện của CLB o365, với nguyên tắc bảo vệ quyền riêng tư và **không phát hành cơ sở dữ liệu** (Không xuất file Excel, CSV).

---

## 1. Sự khác biệt giữa `check_in` (Giảng viên) và `check_in_for_student` (Học viên)

| Đặc tính | `check_in` (Dành cho Giảng viên/BTC) | `check_in_for_student` (Dành cho Học viên) |
| :--- | :--- | :--- |
| **Mục đích** | Quản lý, giám sát và xuất dữ liệu điểm danh toàn bộ lớp | Sinh viên tự xác nhận có mặt qua GPS |
| **Xuất Excel (.xlsx)** | ✅ Có hỗ trợ (`/check-in/export-excel/`) | ❌ **Tuyệt đối không có (Không release database)** |
| **Xuất CSV** | ✅ Có hỗ trợ (`/check-in/export-csv/`) | ❌ **Tuyệt đối không có (Không release database)** |
| **Xem danh sách người khác**| ✅ Giảng viên/Admin xem được toàn bộ danh sách | ❌ Sinh viên chỉ xem được kết quả điểm danh của chính mình |
| **Giao diện** | Giao diện quản trị, có nút xuất file dữ liệu | Giao diện gọn gàng, hiển thị thông tin học viên & nút GPS |

---

## 2. Tính năng chính của `check_in_for_student`

1. **Điểm danh GPS chính xác cao:**
   - Sử dụng HTML5 Geolocation API kết hợp công thức Haversine để đo khoảng cách theo đường chân trời.
   - Bù trừ sai số GPS (accuracy buffer) hợp lý khi ở trong phòng kín, nhưng ngăn chặn gian lận khoảng cách xa.

2. **Bảo mật và riêng tư (No Database Release):**
   - Loại bỏ hoàn toàn các router và view xuất file CSV/Excel.
   - Không cung cấp API liệt kê danh sách điểm danh công khai.
   - Bản ghi được lưu thẳng vào cơ sở dữ liệu hệ thống để Giảng viên tổng hợp, học viên không có quyền can thiệp hoặc tải về database.

3. **Tương thích linh hoạt:**
   - Nếu học viên đã đăng nhập tài khoản LMS: Hệ thống tự động nhận diện Họ tên, MSSV, Lớp sinh hoạt và liên kết bản ghi.
   - Nếu học viên chưa đăng nhập (khách vãng lai): Cung cấp ô nhập MSSV và Họ tên trực tiếp trước khi điểm danh.

---

## 3. Các đường dẫn (URLs)

- `GET /check-in-student/`: Giao diện điểm danh dành cho sinh viên.
- `POST /check-in-student/api/`: API tiếp nhận tọa độ GPS và xác thực.
- `GET /check-in-student/my-status/`: API tra cứu trạng thái bản ghi gần nhất của chính sinh viên đang đăng nhập.
