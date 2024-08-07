import os
import tkinter as tk
from tkinter import messagebox, ttk
import subprocess
import threading
import queue
import sys
import time
import webbrowser


# Global variables
process = None
stop_event = threading.Event()
update_queue = queue.Queue()
total_videos = 0
start_time = time.time()
feedback_reminder_interval = 24 * 3600  # 24 hours in seconds
usage_time_limit = 10 * 60  # 10 minutes in seconds


def create_downloads_folder():
    """Create the 'Downloads' folder if it does not exist."""
    if not os.path.exists("Downloads"):
        os.makedirs("Downloads")

def reset_ui():
    """Reset the UI elements to their default state."""
    download_button.config(state=tk.NORMAL)
    status_label.config(text="")
    progress_bar['value'] = 0
    progress_bar.pack_forget()
    progress_message_label.pack_forget()
    video_name_label.pack_forget()
    exit_button.pack_forget()

def update_gui():
    """Update the GUI based on messages from the update_queue."""
    while not update_queue.empty():
        item = update_queue.get_nowait()
        if item[0] == "video_name":
            video_name_label.config(text=f"Downloading: {item[1]}")
        elif item[0] == "status":
            status_label.config(text=item[1])
            progress_bar['value'] = item[2]
            progress_message_label.config(text=item[1])
        elif item[0] == "info":
            messagebox.showinfo("Download Complete", item[1])
            show_frame(home_frame)
        elif item[0] == "error":
            messagebox.showerror("Download Error", item[1])
            show_frame(home_frame)
    app.after(100, update_gui)  # Check the queue every 100ms

def update_quality_menu(*args):
    """Update the quality menu based on the selected format."""
    if format_var.get() == "MP4":
        quality_var.set(quality_options_mp4[0])
        quality_menu['menu'].delete(0, 'end')
        for option in quality_options_mp4:
            quality_menu['menu'].add_command(label=option, command=tk._setit(quality_var, option))
    elif format_var.get() == "MP3":
        quality_var.set(quality_options_mp3[0])
        quality_menu['menu'].delete(0, 'end')
        for option in quality_options_mp3:
            quality_menu['menu'].add_command(label=option, command=tk._setit(quality_var, option))

def process_playlist():
    """Process the playlist to determine the number of videos."""
    global total_videos
    playlist_url = url_entry.get()
    if not playlist_url:
        messagebox.showwarning("Input Error", "Please enter a playlist URL.")
        return

    create_downloads_folder()
    process_button.config(state=tk.DISABLED)
    show_frame(video_count_frame)

    def run_process():
        global total_videos
        playlist_url = url_entry.get()
        command = ["./yt-dlp.exe", "--flat-playlist", "--get-duration", playlist_url]
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            total_videos = len(result.stdout.splitlines())
            app.after(0, lambda: total_videos_label.config(text=f"Total Videos In Playlist = {total_videos}"))
        except subprocess.CalledProcessError:
            messagebox.showerror("Process Error", "An error occurred while processing the playlist.")
        except FileNotFoundError:
            messagebox.showerror("yt-dlp Not Found", "yt-dlp is not installed. Please install it and try again.")
        finally:
            process_button.config(state=tk.NORMAL)

    threading.Thread(target=run_process).start()

def download_playlist():
    """Start downloading the playlist based on the selected options."""
    playlist_url = url_entry.get()
    start_point = start_entry.get()
    end_point = end_entry.get()
    download_format = format_var.get()
    quality = quality_var.get()

    if not playlist_url:
        messagebox.showwarning("Input Error", "Please enter a playlist URL.")
        return
    if not start_point.isdigit() or not end_point.isdigit():
        messagebox.showwarning("Input Error", "Starting and ending points must be numbers.")
        return
    if int(start_point) < 1 or int(end_point) > total_videos or int(start_point) > int(end_point):
        messagebox.showwarning("Input Error", "Starting and ending points must be within the range of the playlist.")
        return

    create_downloads_folder()
    download_button.config(state=tk.DISABLED)
    show_frame(downloading_frame)  # Switch to the downloading frame

    def run_download():
        global process
        stop_event.clear()
        if download_format == "MP4":
            height = quality.split()[0][:-1]
            format_string = f"bestvideo[height<=?{height}]+bestaudio/best[height<=?{height}]"
            command = [
                "./yt-dlp.exe",
                "-f", format_string,
                "--playlist-start", start_point,
                "--playlist-end", end_point,
                "-o", "Downloads/%(playlist_index)s - %(title)s.%(ext)s",
                playlist_url
            ]
        elif download_format == "MP3":
            audio_quality = quality.split()[0]
            command = [
                "./yt-dlp.exe",
                "-f", "bestaudio/best",
                "--playlist-start", start_point,
                "--playlist-end", end_point,
                "-o", "Downloads/%(playlist_index)s - %(title)s.%(ext)s",
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", audio_quality,
                playlist_url
            ]

        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in process.stdout:
                if stop_event.is_set():
                    process.terminate()
                    break
                if "Destination:" in line:
                    video_name = line.split("Destination:")[1].strip()
                    update_queue.put(("video_name", video_name))
                elif "[download]" in line:
                    progress_message = line.strip()
                    progress = extract_progress(progress_message)
                    update_queue.put(("status", progress_message, progress))
            process.wait()
            if not stop_event.is_set():
                if process.returncode == 0:
                    update_queue.put(("info", "The playlist has been downloaded successfully."))
                else:
                    update_queue.put(("error", "An error occurred while downloading the playlist."))
        except subprocess.CalledProcessError:
            update_queue.put(("error", "An error occurred while downloading the playlist."))
        except FileNotFoundError:
            update_queue.put(("error", "yt-dlp is not installed. Please install it and try again."))
        finally:
            app.after(0, reset_ui)  # Reset the UI after completion

    def extract_progress(line):
        if "%" in line:
            percent = line.split("%")[0].split()[-1]
            try:
                return float(percent)
            except ValueError:
                return 0
        return 0

    threading.Thread(target=run_download).start()
    app.after(100, update_gui)  # Start checking the queue

def exit_application():
    """Stop the download and exit the application."""
    global process
    stop_event.set()  # Signal the thread to stop
    if process and process.poll() is None:
        process.terminate()  # Terminate the process
        process.wait()  # Wait for the process to terminate
    app.quit()
    sys.exit()  # Ensure the application exits

def show_download_range():
    """Show the download range frame."""
    show_frame(download_range_frame)

def show_options():
    """Show the options frame."""
    playlist_url = url_entry.get()
    if not playlist_url:
        messagebox.showwarning("Input Error", "Please enter a playlist URL.")
        return

    show_frame(options_frame)

def show_frame(frame):
    """Raise the specified frame to the top."""
    frame.tkraise()

def show_frame(frame):
    """Raise the specified frame to the top."""
    frame.tkraise()


def show_feedback():
    """Show the feedback frame."""
    show_frame(feedback_frame)

def submit_feedback():
    webbrowser.open("https://forms.gle/F79m6a73c3RwFNa19")

def remind_feedback():
    """Remind the user to give feedback after 10 minutes of continuous use and then every 24 hours."""
    global start_time  # Ensure the global variable is declared at the beginning
    elapsed_time = time.time() - start_time
    if elapsed_time >= usage_time_limit:
        messagebox.showinfo("Feedback Reminder", "Please give your feedback!")
        start_time = time.time()  # Reset the timer
    app.after(1000, remind_feedback)  # Check every second

# Create the main application window
app = tk.Tk()
app.title("YouTube Playlist Downloader")
app.geometry("650x440")
app.minsize(650, 440)
app.maxsize(650, 440)
app.config(bg="#2C3E50")

# Configure the grid layout
app.grid_rowconfigure(0, weight=1)
app.grid_columnconfigure(0, weight=1)

# Create frames
home_frame = tk.Frame(app, bg="#2C3E50")
video_count_frame = tk.Frame(app, bg="#2C3E50")
download_range_frame = tk.Frame(app, bg="#2C3E50")
options_frame = tk.Frame(app, bg="#2C3E50")
downloading_frame = tk.Frame(app, bg="#2C3E50")
feedback_frame = tk.Frame(app, bg="#2C3E50")
footer_frame = tk.Frame(app, bg="#2C3E50")

for frame in (home_frame, video_count_frame, download_range_frame, options_frame, downloading_frame, feedback_frame,footer_frame):
    frame.grid(row=0, column=0, sticky='nsew')

# Home Frame
feedback_button = tk.Button(home_frame, text=" Give Feedback", command=submit_feedback, font=("Consolas", 9, "bold"), bg="#2C3E50", fg="white", relief="raised", borderwidth=3)
feedback_button.place(x=520, y=20)

tk.Label(home_frame, text="YouTube Playlist Downloader", bg="#2C3E50", fg="white", font=("Cooper Black", 16)).pack(pady=70)
tk.Label(home_frame, text="Enter Playlist URL:", bg="#2C3E50", fg="white", font=("Consolas", 14)).pack(pady=5)

url_entry = tk.Entry(home_frame, width=50, font=("Consolas", 12), relief="raised", borderwidth=5)
url_entry.pack(padx=50, pady=10)

process_button = tk.Button(home_frame, text="Process", command=process_playlist, bg="grey", fg="white", font=("Cooper Black", 12), relief="raised", borderwidth=3)
process_button.pack(pady=10)

# Video Count Frame
feedback_button = tk.Button(video_count_frame, text=" Give Feedback", command=submit_feedback, font=("Consolas", 9, "bold"), bg="#2C3E50", fg="white", relief="raised", borderwidth=3)
feedback_button.place(x=520, y=20)

tk.Label(video_count_frame, text="Processing Playlist...", bg="#2C3E50", fg="white", font=("Cooper Black", 12)).pack(pady=70)

total_videos_label = tk.Label(video_count_frame, text="", bg="#2C3E50", fg="white", font=("Consolas", 12))
total_videos_label.pack(pady=10)

next_button = tk.Button(video_count_frame, text="Next", command=show_download_range, bg="grey", fg="white", font=("Cooper Black", 12), relief="raised", borderwidth=3)
next_button.pack(pady=10)

back_button = tk.Button(video_count_frame, text="Back", command=lambda: show_frame(home_frame), bg="red", fg="white", font=("Cooper Black", 12), relief="raised", borderwidth=3)
back_button.pack(pady=10)

# Download Range Frame
feedback_button = tk.Button(download_range_frame, text=" Give Feedback", command=submit_feedback, font=("Consolas", 9, "bold"), bg="#2C3E50", fg="white", relief="raised", borderwidth=3)
feedback_button.place(x=520, y=20)

tk.Label(download_range_frame, text="Enter Download Range (Start and End):", bg="#2C3E50", fg="white", font=("Cooper Black", 12)).pack(pady=70)

range_frame = tk.Frame(download_range_frame, bg="#2C3E50")
range_frame.pack(pady=10)

tk.Label(range_frame, text="Start:", bg="#2C3E50", fg="white", font=("Consolas", 12)).grid(row=0, column=0, padx=10)

tk.Label(range_frame, text="End:", bg="#2C3E50", fg="white", font=("Consolas", 12)).grid(row=0, column=1, padx=10)

start_entry = tk.Entry(range_frame, width=10, font=("Cooper Black", 12), relief="raised", borderwidth=5)
start_entry.grid(row=1, column=0, padx=10)

end_entry = tk.Entry(range_frame, width=10, font=("Cooper Black", 12), relief="raised", borderwidth=5)
end_entry.grid(row=1, column=1, padx=10)

next_button = tk.Button(download_range_frame, text="Next", command=show_options, bg="grey", fg="white", font=("Cooper Black", 12), relief="raised", borderwidth=3)
next_button.pack(pady=10)

back_button = tk.Button(download_range_frame, text="Back", command=process_playlist, bg="red", fg="white", font=("Cooper Black", 12), relief="raised", borderwidth=3)
back_button.pack(pady=10)

# Options Frame
feedback_button = tk.Button(options_frame, text=" Give Feedback", command=submit_feedback, font=("Consolas", 9, "bold"), bg="#2C3E50", fg="white", relief="raised", borderwidth=3)
feedback_button.place(x=520, y=20)

tk.Label(options_frame, text="Select Download Format and Quality:", bg="#2C3E50", fg="white", font=("Cooper Black", 12)).pack(pady=50)

format_var = tk.StringVar(value="MP4")
quality_var = tk.StringVar()
format_menu = tk.OptionMenu(options_frame, format_var, "MP4", "MP3", command=update_quality_menu)
format_menu.pack(pady=10)

quality_options_mp4 = ["1440P HD", "1080P", "720P", "480P"]
quality_options_mp3 = ["128kbps", "230kbps"]
quality_menu = tk.OptionMenu(options_frame, quality_var, *quality_options_mp4)
quality_menu.pack(pady=10)

download_button = tk.Button(options_frame, text="Download", command=download_playlist, bg="grey", fg="white", font=("Cooper Black", 12), relief="raised", borderwidth=3)
download_button.pack(pady=10)

back_button = tk.Button(options_frame, text="Back", command=show_download_range, bg="red", fg="white", font=("Cooper Black", 12), relief="raised", borderwidth=3)
back_button.pack(pady=10)

# Downloading Frame
status_label = tk.Label(downloading_frame, text="Status: ", bg="#2C3E50", fg="white", font=("Cooper Black", 12))
status_label.pack(pady=70)

video_name_label = tk.Label(downloading_frame, text="Downloading:", bg="#2C3E50", fg="white", font=("Consolas", 12), wraplength=400)
video_name_label.pack(pady=10)

progress_bar = ttk.Progressbar(downloading_frame, length=400, mode='determinate')
progress_bar.pack(pady=10)

progress_message_label = tk.Label(downloading_frame, text="", bg="#2C3E50", fg="white", font=("Consolas", 12))
progress_message_label.pack(pady=10)

exit_button = tk.Button(downloading_frame, text="Exit", command=exit_application, bg="red", fg="white", font=("Cooper Black", 12), relief="raised", borderwidth=3)
exit_button.pack(pady=10)

# Feedback frame
feedback_button = tk.Button(feedback_frame, text=" Give Feedback", command=submit_feedback, font=("Consolas", 9, "bold"), bg="#2C3E50", fg="white", relief="raised", borderwidth=3)
feedback_button.place(x=520, y=20)

# Footer Frame
footer_label = tk.Label(footer_frame, text="© 2024 YouTube-Playlist-Downloader Developed By Ali Khan Jalbani", bg="#2C3E50", fg="white", font=("Times New Roman", 10))
footer_label.pack(pady=5)

# Pack the footer at the bottom
footer_frame.grid(row=1, column=0, sticky='ew')


# Show the initial frame
show_frame(home_frame)
app.after(1000, remind_feedback)
app.after(100, update_gui)  # Start checking the queue
app.protocol("WM_DELETE_WINDOW", exit_application)
app.mainloop()
