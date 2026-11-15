import os
import subprocess
import platform
from datetime import datetime
import tkinter as tk
from tkinter import messagebox
import cv2
from PIL import Image, ImageTk, ImageDraw, ImageFont


class ModernEventCameraApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MINH CHỨNG SỰ KIỆN - CAMERA PRO")
        self.root.geometry("820x760")
        self.root.configure(bg="#0f172a")  # Slate 900
        self.root.resizable(False, False)

        # Flag quản lý vòng đời ứng dụng
        self.is_running = True
        self._after_id = None

        # Cấu hình thư mục lưu ảnh minh chứng (đặt cùng thư mục file script)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.save_dir = os.path.join(base_dir, "MinhChung_SuKien")
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)

        # Khởi tạo Camera DirectShow cho Windows
        try:
            if platform.system() == "Windows":
                self.video_capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            else:
                self.video_capture = cv2.VideoCapture(0)
        except Exception:
            self.video_capture = None

        self.current_frame = None
        self.setup_ui()
        self.check_camera_permission()
        self.update_camera_stream()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        # 1. Header Bar
        header = tk.Frame(self.root, bg="#1e293b", height=70)  # Slate 800
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title_lbl = tk.Label(
            header,
            text="HỆ THỐNG GHI NHẬN MINH CHỨNG SỰ KIỆN",
            font=("Segoe UI", 15, "bold"),
            fg="#38bdf8",  # Sky 400
            bg="#1e293b",
        )
        title_lbl.pack(side="left", padx=25, pady=10)

        # Trạng thái Camera LED
        self.status_container = tk.Frame(header, bg="#1e293b")
        self.status_container.pack(side="right", padx=25)

        self.status_dot = tk.Canvas(
            self.status_container, width=12, height=12, bg="#1e293b", highlightthickness=0
        )
        self.status_dot.pack(side="left", padx=(0, 6))
        self.dot_item = self.status_dot.create_oval(2, 2, 10, 10, fill="#22c55e", outline="")

        self.status_lbl = tk.Label(
            self.status_container,
            text="LIVE",
            font=("Segoe UI", 9, "bold"),
            fg="#22c55e",
            bg="#1e293b",
        )
        self.status_lbl.pack(side="left")

        # 2. Main Content Card
        main_card = tk.Frame(self.root, bg="#0f172a")
        main_card.pack(fill="both", expand=True, padx=25, pady=15)

        # Input Box
        input_container = tk.Frame(main_card, bg="#1e293b", padx=15, pady=12)
        input_container.pack(fill="x", pady=(0, 15))

        lbl_input = tk.Label(
            input_container,
            text="TÊN SỰ KIỆN / HOẠT ĐỘNG",
            font=("Segoe UI", 9, "bold"),
            fg="#94a3b8",
            bg="#1e293b",
        )
        lbl_input.pack(anchor="w", pady=(0, 5))

        self.entry_event = tk.Entry(
            input_container,
            font=("Segoe UI", 11),
            bg="#0f172a",
            fg="#f8fafc",
            insertbackground="#38bdf8",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#334155",
            highlightcolor="#38bdf8",
        )
        self.entry_event.insert(0, "Họp Chi Đoàn / Hội Nghị Sinh Viên")
        self.entry_event.pack(fill="x", ipady=8)

        # Khung hiển thị Camera Preview
        preview_border = tk.Frame(main_card, bg="#1e293b", padx=4, pady=4)
        preview_border.pack(fill="both", expand=True)

        self.preview_lbl = tk.Label(
            preview_border,
            bg="#020617",
            fg="#94a3b8",
            font=("Segoe UI", 12),
            text="Đang kết nối camera...",
        )
        self.preview_lbl.pack(fill="both", expand=True)

        # 3. Footer Action Controls
        footer = tk.Frame(self.root, bg="#0f172a", pady=15)
        footer.pack(fill="x", side="bottom", padx=25)

        self.btn_capture = tk.Button(
            footer,
            text="📸  CHỤP & LƯU MINH CHỨNG",
            font=("Segoe UI", 11, "bold"),
            bg="#0284c7",  # Sky 600
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            command=self.capture_photo,
            pady=10,
        )
        self.btn_capture.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_open = tk.Button(
            footer,
            text="📁  MỞ THƯ MỤC",
            font=("Segoe UI", 11, "bold"),
            bg="#334155",  # Slate 700
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            command=self.open_storage_folder,
            pady=10,
            width=18,
        )
        self.btn_open.pack(side="right")

    def check_camera_permission(self):
        if not self.video_capture or not self.video_capture.isOpened():
            self.status_dot.itemconfig(self.dot_item, fill="#ef4444")
            self.status_lbl.configure(text="OFFLINE", fg="#ef4444")
            self.preview_lbl.configure(
                text="⚠️ CAMERA OFFLINE\n\nKhông thể kết nối với webcam.\nVui lòng kiểm tra quyền truy cập camera hoặc thiết bị."
            )
            messagebox.showerror(
                "Lỗi Camera",
                "Không thể truy cập camera!\n\n"
                "1. Kiểm tra camera có bị phần mềm khác (Teams, Meet, Zoom) chiếm dụng không.\n"
                "2. Mở Windows Settings > Privacy & security > Camera để cấp quyền cho Desktop Apps.",
            )

    def update_camera_stream(self):
        if not self.is_running:
            return

        if self.video_capture and self.video_capture.isOpened():
            ret, frame = self.video_capture.read()
            if ret and frame is not None:
                frame = cv2.flip(frame, 1)
                self.current_frame = frame.copy()

                cv2_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(cv2_rgb)
                
                # Resize keeping high quality
                resample_filter = getattr(Image, "Resampling", Image).LANCZOS
                pil_img = pil_img.resize((762, 450), resample_filter)

                imgtk = ImageTk.PhotoImage(image=pil_img)
                self.preview_lbl.imgtk = imgtk
                self.preview_lbl.configure(image=imgtk, text="")

        if self.is_running:
            self._after_id = self.root.after(16, self.update_camera_stream)

    def _get_unicode_font(self, size: int):
        """Tìm font hỗ trợ Unicode tiếng Việt tốt nhất trên hệ thống."""
        candidate_fonts = [
            "arial.ttf",
            "segoeui.ttf",
            "tahoma.ttf",
            "times.ttf",
            "DejaVuSans.ttf",
        ]
        for font_name in candidate_fonts:
            try:
                return ImageFont.truetype(font_name, size)
            except (OSError, IOError):
                continue
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    def capture_photo(self):
        if self.current_frame is None:
            messagebox.showwarning(
                "Cảnh báo",
                "Chưa nhận diện được khung hình camera!\nVui lòng đảm bảo camera đang hoạt động trước khi chụp.",
            )
            return

        event_name = self.entry_event.get().strip()
        if not event_name:
            messagebox.showwarning("Nhắc nhở", "Vui lòng nhập tên sự kiện trước khi chụp!")
            return

        # 1. Chuyển frame sang RGBA để vẽ overlay mượt mà
        rgb_frame = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
        base_image = Image.fromarray(rgb_frame).convert("RGBA")
        width, height = base_image.size

        # 2. Tạo layer overlay trong suốt
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font = self._get_unicode_font(22)
        font_sub = self._get_unicode_font(18)

        # 3. Thông tin watermark
        timestamp_str = datetime.now().strftime("%d/%m/%Y - %H:%M:%S")
        text_line1 = f"SỰ KIỆN: {event_name.upper()}"
        text_line2 = f"THỜI GIAN: {timestamp_str}"

        banner_height = 80
        # Vẽ dải nền tối mờ (Dark overlay banner) ở góc dưới để text luôn rõ nét
        draw.rectangle(
            [(0, height - banner_height), (width, height)],
            fill=(15, 23, 42, 215),  # Slate 900 với độ trong suốt alpha
        )

        # Vẽ dải màu nhấn (Sky blue stripe bên trái)
        draw.rectangle([(0, height - banner_height), (6, height)], fill=(56, 189, 248, 255))

        # Vẽ text tiếng Việt đầy đủ dấu
        draw.text((25, height - banner_height + 12), text_line1, fill=(255, 255, 255, 255), font=font)
        draw.text((25, height - banner_height + 45), text_line2, fill=(148, 163, 184, 255), font=font_sub)

        # 4. Trộn hai layer bằng alpha_composite
        final_image = Image.alpha_composite(base_image, overlay).convert("RGB")

        # 5. Lưu ảnh JPEG chất lượng cao
        save_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"minh_chung_{save_time}.jpg"
        file_path = os.path.join(self.save_dir, file_name)

        final_image.save(file_path, "JPEG", quality=95)

        ans = messagebox.askyesno(
            "Đã Lưu Ảnh",
            f"Ảnh minh chứng đã lưu thành công:\n{file_name}\n\nBạn có muốn mở thư mục ảnh ngay không?",
        )
        if ans:
            self.open_storage_folder()

    def open_storage_folder(self):
        path = os.path.abspath(self.save_dir)
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Lỗi mở thư mục", f"Không thể mở thư mục:\n{str(e)}")

    def on_close(self):
        self.is_running = False
        if self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

        if self.video_capture and self.video_capture.isOpened():
            self.video_capture.release()

        self.root.destroy()


if __name__ == "__main__":
    app_root = tk.Tk()
    app = ModernEventCameraApp(app_root)
    app_root.mainloop()
