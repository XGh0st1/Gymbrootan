import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
import json
import os

class WelcomeEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Welcome Image Editor")
        
        self.bg_image_path = None
        self.bg_image = None
        self.bg_photo = None
        
        self.avatar_x = 100
        self.avatar_y = 100
        self.avatar_size = 128
        
        self.username_x = 200
        self.username_y = 200
        self.username_size = 40
        self.username_angle = 0
        
        self.dragging_item = None
        
        # UI Setup
        control_frame = tk.Frame(root)
        control_frame.pack(side=tk.TOP, fill=tk.X, pady=5)
        
        load_btn = tk.Button(control_frame, text="Load Background Image", command=self.load_bg)
        load_btn.pack(side=tk.LEFT, padx=5)
        
        save_btn = tk.Button(control_frame, text="Save Configuration", command=self.save_config)
        save_btn.pack(side=tk.LEFT, padx=5)
        
        help_label = tk.Label(control_frame, text="Drag to move. Scroll near item to resize. Shift+Scroll near text to rotate.")
        help_label.pack(side=tk.RIGHT, padx=5)
        
        self.canvas = tk.Canvas(root, width=800, height=600, bg='gray')
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<MouseWheel>", self.on_scroll)
        
        # Load existing config if exists
        self.load_existing_config()

    def load_existing_config(self):
        if os.path.exists("welcome_config.json"):
            try:
                with open("welcome_config.json", "r") as f:
                    config = json.load(f)
                    self.bg_image_path = config.get("background_image")
                    self.avatar_x = config.get("avatar_x", 100)
                    self.avatar_y = config.get("avatar_y", 100)
                    self.avatar_size = config.get("avatar_size", 128)
                    self.username_x = config.get("username_x", 200)
                    self.username_y = config.get("username_y", 200)
                    self.username_size = config.get("username_size", 40)
                    self.username_angle = config.get("username_angle", 0)
                    
                    if self.bg_image_path and os.path.exists(self.bg_image_path):
                        self.load_image()
            except Exception as e:
                print(f"Error loading config: {e}")

    def load_bg(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg")])
        if file_path:
            # Save relative path if it's in the same directory, otherwise absolute
            if os.path.commonprefix([os.path.abspath(file_path), os.path.abspath(".")]) == os.path.abspath("."):
                self.bg_image_path = os.path.relpath(file_path) 
            else:
                self.bg_image_path = file_path
            self.load_image()

    def load_image(self):
        try:
            self.bg_image = Image.open(self.bg_image_path)
            self.bg_photo = ImageTk.PhotoImage(self.bg_image)
            
            self.canvas.config(width=self.bg_image.width, height=self.bg_image.height)
            self.draw_canvas()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image: {e}")

    def draw_canvas(self):
        self.canvas.delete("all")
        if self.bg_photo:
            self.canvas.create_image(0, 0, image=self.bg_photo, anchor=tk.NW)
            
            # Draw dummy avatar circle
            x0 = self.avatar_x - self.avatar_size // 2
            y0 = self.avatar_y - self.avatar_size // 2
            x1 = self.avatar_x + self.avatar_size // 2
            y1 = self.avatar_y + self.avatar_size // 2
            
            self.canvas.create_oval(x0, y0, x1, y1, outline="red", width=3, dash=(4, 4), tags="avatar")
            self.canvas.create_text(self.avatar_x, self.avatar_y, text="Avatar", fill="red", font=("Arial", 16, "bold"), tags="avatar")
            
            # Draw dummy username text using PIL for accurate font and rotation
            try:
                font = ImageFont.truetype("Poppins-Bold.ttf", self.username_size)
            except:
                try:
                    font = ImageFont.truetype("arialbd.ttf", self.username_size)
                except:
                    font = ImageFont.load_default()
                    
            text = "Username123"
            if hasattr(font, 'getbbox'):
                bbox = font.getbbox(text)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                offset_x, offset_y = bbox[0], bbox[1]
            else:
                text_w, text_h = font.getsize(text)
                offset_x, offset_y = 0, 0
                
            txt_img = Image.new('RGBA', (text_w + 40, text_h + 40), (255, 255, 255, 0))
            txt_draw = ImageDraw.Draw(txt_img)
            txt_draw.text((20 - offset_x, 20 - offset_y), text, font=font, fill=(255, 255, 255, 255))
            
            if self.username_angle != 0:
                # CCW rotation to match PIL
                txt_img = txt_img.rotate(-self.username_angle, expand=True, resample=Image.BICUBIC)
                
            self.text_photo = ImageTk.PhotoImage(txt_img)
            self.canvas.create_image(self.username_x, self.username_y, image=self.text_photo, tags="username")

    def on_press(self, event):
        if not self.bg_image: return
        self.dragging_item = None
        
        # Check distance to see what was clicked
        dist_avatar = (event.x - self.avatar_x)**2 + (event.y - self.avatar_y)**2
        dist_username = (event.x - self.username_x)**2 + (event.y - self.username_y)**2
        
        if dist_avatar < dist_username:
            if dist_avatar < (self.avatar_size)**2:
                self.dragging_item = "avatar"
        else:
            if dist_username < (self.username_size*3)**2:
                self.dragging_item = "username"

    def on_drag(self, event):
        if self.dragging_item == "avatar":
            self.avatar_x = event.x
            self.avatar_y = event.y
            self.draw_canvas()
        elif self.dragging_item == "username":
            self.username_x = event.x
            self.username_y = event.y
            self.draw_canvas()

    def on_release(self, event):
        self.dragging_item = None

    def on_scroll(self, event):
        if not self.bg_image: return
        
        dist_avatar = (event.x - self.avatar_x)**2 + (event.y - self.avatar_y)**2
        dist_username = (event.x - self.username_x)**2 + (event.y - self.username_y)**2
        target = "avatar" if dist_avatar < dist_username else "username"
        
        delta = 10 if event.delta > 0 else -10
        shift_pressed = (event.state & 0x0001) != 0
        
        if shift_pressed and target == "username":
            self.username_angle = (self.username_angle + (5 if event.delta > 0 else -5)) % 360
        else:
            if target == "avatar":
                self.avatar_size = max(20, self.avatar_size + delta)
            elif target == "username":
                size_delta = 10 if event.delta > 0 else -10
                self.username_size = max(10, self.username_size + size_delta)
                
        self.draw_canvas()

    def save_config(self):
        if not self.bg_image_path:
            messagebox.showwarning("Warning", "No background image loaded.")
            return
            
        config = {
            "background_image": self.bg_image_path,
            "avatar_x": self.avatar_x,
            "avatar_y": self.avatar_y,
            "avatar_size": self.avatar_size,
            "username_x": self.username_x,
            "username_y": self.username_y,
            "username_size": self.username_size,
            "username_angle": self.username_angle
        }
        try:
            with open("welcome_config.json", "w") as f:
                json.dump(config, f, indent=4)
            messagebox.showinfo("Success", "Configuration saved to welcome_config.json")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = WelcomeEditor(root)
    root.mainloop()

