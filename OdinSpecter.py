
from time import sleep
from PIL import Image, ImageDraw, ImageFont
import sys
import os
import argparse
import pygame  # Import pygame
import subprocess
import time
import socket
import json
import threading
import signal
from driver.Whisplay import WhisPlayBoard
from utils import ColorUtils, ImageUtils, TextUtils

scroll_thread = None
scroll_stop_event = threading.Event()

status_font_size=24
emoji_font_size=40
battery_font_size=13

# Global variables
current_status = "Hello"
current_emoji = "😄"
current_text = "Waiting for message..."
current_battery_level = 100
current_battery_color = ColorUtils.get_rgb255_from_any("#55FF00")
current_scroll_top = 0
current_scroll_speed = 6
current_image_path = ""
current_image = None
camera_mode = False
camera_mode_button_press_time = 0
camera_mode_button_release_time = 0
camera_capture_image_path = ""
camera_thread = None
clients = {}
# Global variables
img1_data = None  # Recording stage (test1.jpg)
img2_data = None  # Playback stage (test2.jpg)
REC_FILE = "data/recorded_voice.wav"
recording_process = None

class RenderThread(threading.Thread):
    def __init__(self, whisplay, font_path, fps=30):
        super().__init__()
        self.whisplay = whisplay
        self.font_path = font_path
        self.fps = fps
        self.render_init_screen()
        # Clear logo after 1 second and start running loop
        time.sleep(1)
        self.running = True
        self.main_text_font = ImageFont.truetype(self.font_path, 20)
        self.main_text_line_height = self.main_text_font.getmetrics()[0] + self.main_text_font.getmetrics()[1]
        self.text_cache_image = None
        self.current_render_text = ""

    def render_init_screen(self):
        # Display logo on startup
        logo_path = os.path.join("img", "logo.png")
        if os.path.exists(logo_path):
            logo_image = Image.open(logo_path).convert("RGBA")
            logo_image = logo_image.resize((whisplay.LCD_WIDTH, whisplay.LCD_HEIGHT), Image.LANCZOS)
            rgb565_data = ImageUtils.image_to_rgb565(logo_image, whisplay.LCD_WIDTH, whisplay.LCD_HEIGHT)
            whisplay.set_backlight(100)
            whisplay.draw_image(0, 0, whisplay.LCD_WIDTH, whisplay.LCD_HEIGHT, rgb565_data)

    def render_frame(self, status, emoji, text, scroll_top, battery_level, battery_color):
        global current_scroll_speed, current_image_path, current_image, camera_mode
        if camera_mode:
            return  # Skip rendering if in camera mode
        if current_image_path not in [None, ""]:
            # Try to load image from path
            if current_image is not None:
                rgb565_data = ImageUtils.image_to_rgb565(current_image, self.whisplay.LCD_WIDTH, self.whisplay.LCD_HEIGHT)
                self.whisplay.draw_image(0, 0, self.whisplay.LCD_WIDTH, self.whisplay.LCD_HEIGHT, rgb565_data)
            elif os.path.exists(current_image_path):
                try:
                    image = Image.open(current_image_path).convert("RGBA") # 1024x1024
                    # crop center and resize to fit screen ratio
                    img_w, img_h = image.size
                    screen_ratio = self.whisplay.LCD_WIDTH / self.whisplay.LCD_HEIGHT
                    img_ratio = img_w / img_h
                    if img_ratio > screen_ratio:
                        # crop width
                        new_w = int(img_h * screen_ratio)
                        left = (img_w - new_w) // 2
                        image = image.crop((left, 0, left + new_w, img_h))
                    else:
                        # crop height
                        new_h = int(img_w / screen_ratio)
                        top = (img_h - new_h) // 2
                        image = image.crop((0, top, img_w, top + new_h))
                    image = image.resize((self.whisplay.LCD_WIDTH, self.whisplay.LCD_HEIGHT), Image.LANCZOS)
                    current_image = image
                    rgb565_data = ImageUtils.image_to_rgb565(image, self.whisplay.LCD_WIDTH, self.whisplay.LCD_HEIGHT)
                    self.whisplay.draw_image(0, 0, self.whisplay.LCD_WIDTH, self.whisplay.LCD_HEIGHT, rgb565_data)
                except Exception as e:
                    print(f"[Render] Failed to load image {current_image_path}: {e}")
        else:
            current_image = None
            header_height = 88 + 10  # header + margin
            # create a black background image for header
            image = Image.new("RGBA", (self.whisplay.LCD_WIDTH, header_height), (0, 0, 0, 255))
            draw = ImageDraw.Draw(image)
            
            clock_font_size = 24
            # clock_font = ImageFont.truetype(self.font_path, clock_font_size)

            # current_time = time.strftime("%H:%M:%S")
            # draw.text((self.whisplay.LCD_WIDTH // 2, self.whisplay.LCD_HEIGHT // 2), current_time, font=clock_font, fill=(255, 255, 255, 255))
            
            # render header
            self.render_header(image, draw, status, emoji, battery_level, battery_color)
            self.whisplay.draw_image(0, 0, self.whisplay.LCD_WIDTH, header_height, ImageUtils.image_to_rgb565(image, self.whisplay.LCD_WIDTH, header_height))

            # render main text area
            text_area_height = self.whisplay.LCD_HEIGHT - header_height
            text_bg_image = Image.new("RGBA", (self.whisplay.LCD_WIDTH, text_area_height), (0, 0, 0, 255))
            text_draw = ImageDraw.Draw(text_bg_image)
            self.render_main_text(text_bg_image, text_area_height, text_draw, text, current_scroll_speed)
            self.whisplay.draw_image(0, header_height, self.whisplay.LCD_WIDTH, text_area_height, ImageUtils.image_to_rgb565(text_bg_image, self.whisplay.LCD_WIDTH, text_area_height))

        

    def render_main_text(self, main_text_image, area_height, draw, text, scroll_speed=2):
        global current_scroll_top
        """Render main text content, wrap lines according to screen width, only display currently visible part"""
        if not text:
            return
        # Use main text font
        font = ImageFont.truetype(self.font_path, 20)
        lines = TextUtils.wrap_text(draw, text, font, self.whisplay.LCD_WIDTH - 20)

        # Line height
        line_height = self.main_text_line_height

        # Calculate currently visible lines
        display_lines = []
        render_y = 0
        fin_show_lines = False
        for i, line in enumerate(lines):
            if (i + 1) * line_height >= current_scroll_top and i * line_height - current_scroll_top <= area_height:
                display_lines.append(line)
                fin_show_lines = True
            elif fin_show_lines is False:
                render_y += line_height
        
        # render_text
        render_text = ""
        for line in display_lines:
            render_text += line
        if self.current_render_text != render_text:
            self.current_render_text = render_text
            show_text_image = Image.new("RGBA", (self.whisplay.LCD_WIDTH, render_y + len(display_lines) * line_height), (0, 0, 0, 255))
            show_text_draw = ImageDraw.Draw(show_text_image)
            for line in display_lines:
                TextUtils.draw_mixed_text(show_text_draw, show_text_image, line, font, (10, render_y))
                render_y += line_height
            # Update cache image
            self.text_cache_image = show_text_image
        # Draw text_cache_image to main_text_image
        main_text_image.paste(self.text_cache_image, (0, -current_scroll_top), self.text_cache_image)

        # Update scroll position
        if scroll_speed > 0 and current_scroll_top < (len(lines) + 1) * line_height - area_height:
            current_scroll_top += scroll_speed
                

    def render_header(self, image, draw, status, emoji, battery_level, battery_color):
        global current_status, current_emoji, current_battery_level, current_battery_color
        global status_font_size, emoji_font_size, battery_font_size
        
        status_font = ImageFont.truetype(self.font_path, status_font_size)
        emoji_font = ImageFont.truetype(self.font_path, emoji_font_size)
        battery_font = ImageFont.truetype(self.font_path, battery_font_size)

        image_width = self.whisplay.LCD_WIDTH

        ascent_status, _ = status_font.getmetrics()
        ascent_emoji, _ = emoji_font.getmetrics()

        top_height = status_font_size + emoji_font_size + 20

        # Draw status centered
        status_bbox = status_font.getbbox(current_status)
        status_w = status_bbox[2] - status_bbox[0]
        TextUtils.draw_mixed_text(draw, image, current_status, status_font, (whisplay.CornerHeight, 0))

        # Draw emoji centered
        emoji_bbox = emoji_font.getbbox(current_emoji)
        emoji_w = emoji_bbox[2] - emoji_bbox[0]
        TextUtils.draw_mixed_text(draw, image, current_emoji, emoji_font, ((image_width - emoji_w) // 2, status_font_size + 8))
        
        # Draw battery icon
        if battery_level is not None:
            self.render_battery(draw, battery_font, battery_level, battery_color, image_width, status_font_size)
        
        return top_height

    def render_battery(self, draw, battery_font, battery_level, battery_color, image_width, status_font_size):
         # Battery icon parameters (smaller)
        battery_width = 26
        battery_height = 15
        battery_margin_right = 20
        battery_x = image_width - battery_width - battery_margin_right
        battery_y = (status_font_size) // 2
        corner_radius = 3
        fill_color = "black"
        if battery_color is not None:
            fill_color = battery_color # Light green
        # Outline with rounded corners
        outline_color = "white"
        line_width = 2

        # Draw rounded corners
        draw.arc((battery_x, battery_y, battery_x + 2 * corner_radius, battery_y + 2 * corner_radius), 180, 270, fill=outline_color, width=line_width)  # Top-left
        draw.arc((battery_x + battery_width - 2 * corner_radius, battery_y, battery_x + battery_width, battery_y + 2 * corner_radius), 270, 0, fill=outline_color, width=line_width)  # Top-right
        draw.arc((battery_x, battery_y + battery_height - 2 * corner_radius, battery_x + 2 * corner_radius, battery_y + battery_height), 90, 180, fill=outline_color, width=line_width)  # Bottom-left
        draw.arc((battery_x + battery_width - 2 * corner_radius, battery_y + battery_height - 2 * corner_radius, battery_x + battery_width, battery_y + battery_height), 0, 90, fill=outline_color, width=line_width)  # Bottom-right

        # Draw top and bottom lines
        draw.line([(battery_x + corner_radius, battery_y), (battery_x + battery_width - corner_radius, battery_y)], fill=outline_color, width=line_width)  # Top
        draw.line([(battery_x + corner_radius, battery_y + battery_height), (battery_x + battery_width - corner_radius, battery_y + battery_height)], fill=outline_color, width=line_width)  # Bottom

        # Draw left and right lines
        draw.line([(battery_x, battery_y + corner_radius), (battery_x, battery_y + battery_height - corner_radius)], fill=outline_color, width=line_width)  # Left
        draw.line([(battery_x + battery_width, battery_y + corner_radius), (battery_x + battery_width, battery_y + battery_height - corner_radius)], fill=outline_color, width=line_width)  # Right

        if fill_color !=(0,0,0):
            draw.rectangle([battery_x + line_width // 2, battery_y + line_width // 2, battery_x + battery_width - line_width // 2, battery_y + battery_height - line_width // 2], fill=fill_color)

        # Battery head
        head_width = 2
        head_height = 5
        head_x = battery_x + battery_width
        head_y = battery_y + (battery_height - head_height) // 2
        draw.rectangle([head_x, head_y, head_x + head_width, head_y + head_height], fill="white")

        # Battery level text (just number)
        battery_text = str(battery_level)
        text_bbox = battery_font.getbbox(battery_text)
        text_h = text_bbox[3] - text_bbox[1]
        text_y = battery_y + (battery_height - (battery_font.getmetrics()[0] + battery_font.getmetrics()[1])) // 2
        text_w = text_bbox[2] - text_bbox[0]
        text_x = battery_x + (battery_width - text_w) // 2
        
        luminance = ColorUtils.calculate_luminance(fill_color)
        brightness_threshold = 128 # You can adjust this threshold as needed
        if luminance > brightness_threshold:
            text_fill_color = "black"
        else:
            text_fill_color = "white"
        draw.text((text_x, text_y), battery_text, font=battery_font, fill=text_fill_color)

    def run(self):
        frame_interval = 1 / self.fps
        while self.running:
            self.render_frame(current_status, current_emoji, current_text, current_scroll_top, current_battery_level, current_battery_color)
            time.sleep(frame_interval)
            
    def stop(self):
        self.running = False

whisplay = WhisPlayBoard()
whisplay.set_backlight(50)

global_image_data = None
image_filepath = None

# Initialize pygame mixer
pygame.mixer.init()
sound = None  # Global sound variable
playing = False  # Global variable to track if sound is playing


def set_wm8960_volume_stable(volume_level: str):
    """Set wm8960 sound card volume"""
    CARD_NAME = 'wm8960soundcard'
    DEVICE_ARG = f'hw:{CARD_NAME}'
    try:
        subprocess.run(['amixer', '-D', DEVICE_ARG, 'sset', 'Speaker',
                       volume_level], check=False, capture_output=True)
        subprocess.run(['amixer', '-D', DEVICE_ARG, 'sset',
                       'Capture', '100'], check=False, capture_output=True)
    except Exception as e:
        print(f"ERROR: Failed to set volume: {e}")

def start_recording():
    """Enter recording stage: display test1.jpg and start arecord"""
    global recording_process, img1_data
    print(">>> Status: Entering recording stage (displaying test1)...")
    print(">>> Press the button to stop recording and playback...")

    if img1_data:
        whisplay.draw_image(0, 0, whisplay.LCD_WIDTH, whisplay.LCD_HEIGHT, img1_data)

    # Start recording asynchronously
    command = ['arecord', '-D', 'hw:wm8960soundcard',
               '-f', 'S24_LE', '-r', '16000', '-c', '2', REC_FILE]
    recording_process = subprocess.Popen(command)

def load_jpg_as_rgb565(filepath, screen_width, screen_height):
    img = Image.open(filepath).convert('RGB')
    original_width, original_height = img.size

    aspect_ratio = original_width / original_height
    screen_aspect_ratio = screen_width / screen_height

    if aspect_ratio > screen_aspect_ratio:
        # Original image is wider, scale based on screen height
        new_height = screen_height
        new_width = int(new_height * aspect_ratio)
        resized_img = img.resize((new_width, new_height))
        # Calculate horizontal offset to center the image
        offset_x = (new_width - screen_width) // 2
        # Crop the image to fit screen width
        cropped_img = resized_img.crop(
            (offset_x, 0, offset_x + screen_width, screen_height))
    else:
        # Original image is taller or has the same aspect ratio, scale based on screen width
        new_width = screen_width
        new_height = int(new_width / aspect_ratio)
        resized_img = img.resize((new_width, new_height))
        # Calculate vertical offset to center the image
        offset_y = (new_height - screen_height) // 2
        # Crop the image to fit screen height
        cropped_img = resized_img.crop(
            (0, offset_y, screen_width, offset_y + screen_height))

    pixel_data = []
    for y in range(screen_height):
        for x in range(screen_width):
            r, g, b = cropped_img.getpixel((x, y))
            rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            pixel_data.extend([(rgb565 >> 8) & 0xFF, rgb565 & 0xFF])

    return pixel_data

def on_button_pressed_record():
    """Button callback: stop recording -> color change -> display test2 -> play recording (blocking) -> return to recording"""
    global recording_process, img1_data, img2_data
    print(">>> Button pressed!")

    # 1. Stop recording
    if recording_process and recording_process.poll() is None:
        recording_process.terminate()
        recording_process.wait()

    # 2. Visual feedback: LED color sequence
    color_sequence = [(255, 0, 0, 0xF800),
                      (0, 255, 0, 0x07E0), (0, 0, 255, 0x001F)]
    for r, g, b, hex_code in color_sequence:
        whisplay.fill_screen(hex_code)
        whisplay.set_rgb(r, g, b)
        sleep(0.4)
    whisplay.set_rgb(0, 0, 0)

    # 3. Playback feedback: display test2.jpg and play recorded audio
    if img2_data:
        whisplay.draw_image(0, 0, whisplay.LCD_WIDTH, whisplay.LCD_HEIGHT, img2_data)

    print(">>> Playing back recording (displaying test2)...")
    subprocess.run(['aplay', '-D', 'plughw:wm8960soundcard', REC_FILE])

    # 4. Automatically return to recording stage
    start_recording()

# Button callback function

def on_button_pressed_play():
    print("Button pressed!")

    global sound, playing  # Use the global sound and playing variables

    # --- MODIFICATION START: Play sound BEFORE screen changes ---
    if sound:
        if playing:
            sound.stop()  # Stop the current sound if it's playing
            print("Stopping current sound...")
        sound.play()  # Play the sound from the beginning
        print("Playing sound concurrently with display changes...")
        playing = True  # Set the playing flag
    else:
        print("Sound not loaded.")
    # --- MODIFICATION END ---

    # Display red filled screen
    whisplay.fill_screen(0xF800)  # Red RGB565
    whisplay.set_rgb(255, 0, 0)
    sleep(0.5)

    # Display green filled screen
    whisplay.fill_screen(0x07E0)  # Green RGB565
    whisplay.set_rgb(0, 255, 0)
    sleep(0.5)

    # Display blue filled screen
    whisplay.fill_screen(0x001F)  # Blue RGB565
    whisplay.set_rgb(0, 0, 255)
    sleep(0.5)

    # Display the image using the globally stored data
    global global_image_data, image_filepath
    if global_image_data is not None:
        whisplay.draw_image(0, 0, whisplay.LCD_WIDTH,
                         whisplay.LCD_HEIGHT, global_image_data)
        print(
            f"Image {os.path.basename(image_filepath)} displayed successfully from memory.")
    else:
        print("Image data not loaded yet. This should not happen after initial load.")

def on_button_pressed():
    """Button callback: play sound -> color change -> display image"""
    on_button_pressed_record()

# Register button event
whisplay.on_button_press(on_button_pressed)

# --- Argument Parsing ---
# parser = argparse.ArgumentParser(
#     description="Display an image and play sound on button press.")
# parser.add_argument("--image", default="data/OdinSpecter_1.png",
#                     help="Path to the image file (default: data/test.png)")
# parser.add_argument("--sound", default="data/test.mp3",
#                     # Add sound argument
#                     help="Path to the sound file (default: data/test.mp3)")
# args = parser.parse_args()

image_filepath = 'data/OdinSpecter_1.png'
sound_filepath = 'data/test.mp3'

# --- Initial Image Loading ---
# Load the image once at the beginning of the script
try:
    global_image_data = load_jpg_as_rgb565(
        image_filepath, whisplay.LCD_WIDTH, whisplay.LCD_HEIGHT)
    whisplay.draw_image(0, 0, whisplay.LCD_WIDTH,
                     whisplay.LCD_HEIGHT, global_image_data)
    print(
        f"Image {os.path.basename(image_filepath)} loaded and displayed initially.")
except Exception as e:
    print(f"Failed to load initial image from {image_filepath}: {e}")

# Load the sound
try:
    sound = pygame.mixer.Sound(sound_filepath)
    print(f"Sound {os.path.basename(sound_filepath)} loaded successfully.")
    set_wm8960_volume_stable("121")  # Set volume to 121（74）
except Exception as e:
    print(f"Failed to load sound from {sound_filepath}: {e}")
    sound = None

try:
    print("Waiting for button press (Press Ctrl+C to exit)...")
    # 4. After audio finishes, enter recording loop
    start_recording()
    while True:
        # Check if the sound has finished playing and update the 'playing' flag
        if playing and not pygame.mixer.get_busy():
            playing = False
            # print("Sound finished playing.") # Optional print
        sleep(0.1)

except KeyboardInterrupt:
    print("Exiting program...")

finally:
    whisplay.cleanup()
    pygame.mixer.quit()  # Quit the mixer
