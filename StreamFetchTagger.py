import tkinter as tk
from tkinter import filedialog, ttk
import yt_dlp
import sys
import threading
import subprocess
import os
import hashlib
import base64
import glob
import re
import requests
import json
import queue
import time
from PIL import ImageTk, Image
from io import BytesIO
import plistlib

app_name = "StreamFetchTagger"
app_version = "1.0.0"
tmdb_key = "9de437782139633fe25c0d307d5da137"
opensubtitles_token = None
opensubtitles_key = "lhUi4siT3Y6pbCI0qkCNNJG48q1mzXLT"
opensubtitles_user_agent = app_name + " v" + app_version
download_folder = os.getcwd()
home_folder = os.path.expanduser("~")
hidden_folder = os.path.join(home_folder, "." + app_name)

# Create a stop event
stop_event = threading.Event()
download_process = None
progress_queue = queue.Queue()  # Create a queue to communicate between threads
backdrop_list = []
last_load_id = ""
debounce_timer = None
metadata = {}
plist_content = None

def get_binary_path(binary_name):
    """Finds the correct path to a bundled binary"""
    if getattr(sys, 'frozen', False):  # Running inside PyInstaller
        base_path = sys._MEIPASS  # PyInstaller's temp directory
    else:
        base_path = os.path.dirname(__file__)  # Running as a script

    return os.path.join(base_path, "binaries", binary_name)

# Define binary paths
FFMPEG_PATH = get_binary_path("ffmpeg")
FFPROBE_PATH = get_binary_path("ffprobe")
ATOMIC_PARSLEY_PATH = get_binary_path("AtomicParsley")
MP4BOX_PATH = get_binary_path("MP4Box")


def download_thumbnail():
    global thumbnail_image_path_or_url
    print(thumbnail_image_path_or_url)

    if "http" not in thumbnail_image_path_or_url:
        print("thumbnail_image_path_or_url is already downloaded")
        return

    # Determine file extension from URL
    ext = os.path.splitext(thumbnail_image_path_or_url)[-1] or ".jpg"
    url = url_entry.get().strip()
    hash = hash_url(url)
    save_path = os.path.join(hidden_folder, f"{hash}{ext}")

    try:
        response = requests.get(thumbnail_image_path_or_url, stream=True)
        response.raise_for_status()  # Raise error if request fails

        with open(save_path, "wb") as file:
            for chunk in response.iter_content(1024):
                file.write(chunk)

        print(f"Thumbnail downloaded successfully to {save_path}")
        thumbnail_image_path_or_url = save_path

    except requests.RequestException as e:
        print(f"Failed to download thumbnail: {e}")


def retrieve_tmdb_data(event=None):
    """Retrieves the data from TMDB for the specified ID and media type"""
    global debounce_timer
    # Cancel any previously scheduled execution
    if debounce_timer is not None:
        root.after_cancel(debounce_timer)

    tmdb_id = tmdb_id_entry.get().strip()

    # If the media type is TV
    if tv_var.get():
        media_type = "tv"
        season = season_entry.get().strip()
        episode = episode_entry.get().strip()

        if not tmdb_id or not season or not episode:
            tmdb_title_var.set("Unknown Series Title")
            return

        # Retrieve general TV show info
        show_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={tmdb_key}&language=en-US"

        # Retrieve episode-specific info
        episode_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/season/{season}/episode/{episode}?api_key={tmdb_key}&language=en-US"

        # Retrieve the rating
        rating_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/content_ratings?api_key={tmdb_key}"

        # Credits
        credits_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/season/{season}/episode/{episode}/credits?api_key={tmdb_key}"

    else:
        # For movies
        if not tmdb_id:
            tmdb_title_var.set("Unknown Movie Title")
            return
        media_type = "movie"
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={tmdb_key}&language=en-US"
        rating_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/release_dates?api_key={tmdb_key}"
        credits_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/credits?api_key={tmdb_key}"

    # Retrieve data from TMDB
    def retrieve_data():

        global metadata
        global plist_content
        metadata = {}
        plist_content = None

        try:
            # If it's a TV show, make two requests: one for the show info and one for the episode info
            if tv_var.get():
                # Request for TV show general info
                show_response = requests.get(show_url)
                show_data = show_response.json()

                # Request for episode-specific info
                episode_response = requests.get(episode_url)
                episode_data = episode_response.json()

                # Request ratings
                rating_response = requests.get(rating_url)
                rating_data = rating_response.json()

                # Request credits
                credits_response = requests.get(credits_url)
                credits_data = credits_response.json()

                # Handle TV Show general data
                unknown_media = episode_data.get("name", None)
                name = episode_data.get("name", "Unknown Episode Title")
                genre = ", ".join([g["name"] for g in show_data.get("genres", [])])
                release_date = episode_data.get("air_date", "1900-01-01")
                tv_show = show_data.get("name", "Unknown Series Title")
                tv_network = ", ".join([net["name"] for net in show_data.get("networks", [])])
                description = episode_data.get("overview", "No description available.")
                long_description = episode_data.get("overview", "No long description available.")

                # Get the series description from the current season's overview
                season_data = show_data.get("seasons", [])
                series_description = ""
                for season_info in season_data:
                    if str(season_info["season_number"]) == season:
                        series_description = season_info.get("overview", "No season overview available.")
                        break


                # **Get the rating (US region)**
                rating = "Not Rated"
                for rating_entry in rating_data.get("results", []):
                    if rating_entry["iso_3166_1"] == "US":
                        rating = rating_entry.get("rating", "Not Rated")
                        break

                cast = [cast_member["name"] for cast_member in credits_data.get("cast", [])]
                directors = [crew["name"] for crew in credits_data.get("crew", []) if crew["job"] == "Director"]
                producers = []
                screenwriters = [crew["name"] for crew in credits_data.get("crew", []) if crew["job"] == "Writer" or crew["job"] == "Screenplay"]
                studios = ", ".join([studio["name"] for studio in show_data.get("production_companies", [])])
                still_path = episode_data.get("still_path", None)
                tmdb_title_var.set(f"{tv_show} — S{season}E{episode}: {name}")
                if unknown_media != None:
                    # Delete any existing text in the filename_entry box
                    filename_entry.delete(0, tk.END)
                    # Insert new text
                    filename_entry.insert(0, f"{tv_show} - S{season}E{episode}")
                else:
                    filename_entry.delete(0, tk.END)
                    filename_entry.insert(0, "Untitled")

            else:
                # Handle Movie request
                response = requests.get(url)
                data = response.json()

                # Request ratings
                rating_response = requests.get(rating_url)
                rating_data = rating_response.json()

                # Request credits
                credits_response = requests.get(credits_url)
                credits_data = credits_response.json()

                unknown_media = data.get("title", None)
                name = data.get("title", "Unknown Movie Title")
                genre = ", ".join([g["name"] for g in data.get("genres", [])])
                release_date = data.get("release_date", "1900-01-01")
                description = data.get("overview", "No description available.")
                long_description = data.get("overview", "No long description available.")

                # **Get movie rating (US region)**
                rating = "Not Rated"
                for country in rating_data.get("results", []):
                    if country["iso_3166_1"] == "US":
                        for release in country.get("release_dates", []):
                            rating = release.get("certification", "Not Rated")
                            if rating:  # Stop at first found rating
                                break

                cast = [cast_member["name"] for cast_member in credits_data.get("cast", [])]
                directors = [crew["name"] for crew in credits_data.get("crew", []) if crew["job"] == "Director"]
                producers = [crew["name"] for crew in credits_data.get("crew", []) if crew["job"] in ["Producer", "Executive Producer"]]
                screenwriters = [crew["name"] for crew in credits_data.get("crew", []) if crew["job"] in ["Writer", "Screenplay"]]
                studios = ", ".join([studio["name"] for studio in data.get("production_companies", [])])
                still_path = None
                tmdb_title_var.set(name)
                if unknown_media != None:
                    # Delete any existing text in the filename_entry box
                    filename_entry.delete(0, tk.END)
                    # Insert new text
                    filename_entry.insert(0, f"{name}")
                else:
                    filename_entry.delete(0, tk.END)
                    filename_entry.insert(0, "Untitled")

            # Print TV Show data
            if tv_var.get():
                print(f"TV Show: {tv_show}")
                print(f"Season: {season}, Episode: {episode} - {name}")
                print(f"Genre: {genre}")
                print(f"Release Date: {release_date}")
                print(f"Network: {tv_network}")
                print(f"Rating: {rating}")
                print(f"Studio: {studios}")
                print(f"Series Description: {series_description}")
                print(f"Episode Description: {description}")
                print(f"Long Description: {long_description}")
                print(f"Director(s): {directors}")
                print(f"Screenwriter(s): {screenwriters}")
                print(f"Cast: {cast}")

            # Print Movie data
            else:
                print(f"Movie: {name}")
                print(f"Genre: {genre}")
                print(f"Release Date: {release_date}")
                print(f"Rating: {rating}")
                print(f"Studio: {studios}")
                print(f"Description: {description}")
                print(f"Long Description: {long_description}")
                print(f"Director(s): {directors}")
                print(f"Producer(s): {producers}")
                print(f"Screenwriter(s): {screenwriters}")
                print(f"Cast: {cast}")

            if tv_var.get():
                metadata = {
                    "--title": name,
                    "--genre": genre,
                    "--year": release_date,
                    "--TVNetwork": tv_network,
                    "--contentRating": rating,
                    "--TVShowName": tv_show,
                    "--TVSeasonNum": season,
                    "--TVEpisodeNum": episode,
                    "--description": description,
                    "--longdesc": long_description,
                    "--storedesc": series_description,
                    "--artist": ", ".join(directors),
                    "--stik": "TV Show", # Set mediatype to tv show
                }
            else:
                # Metadata for movies
                metadata = {
                    "--title": name,
                    "--genre": genre,
                    "--year": release_date,
                    "--contentRating": rating,
                    "--description": description,
                    "--longdesc": long_description,
                    "--artist": ", ".join(directors),
                    "--stik": "Movie" # Set mediatype to movie
                }

            if unknown_media == None:
                metadata = {}
                plist_content = None

            plist_content = makePlist(cast, directors, producers, screenwriters, studios)

            retrieve_backdrops(tmdb_id, media_type, still_path)

        except Exception as e:
            tmdb_title_var.set("Error fetching data from TMDB")
            metadata = {}
            plist_content = None
            print(f"Error: {e}")

    debounce_timer = root.after(500, lambda: threading.Thread(target=retrieve_data, daemon=True).start())

def retrieve_backdrops(tmdb_id, media_type, still_path):
    """
    Fetches English backdrops with a 16:9 ratio for a given movie or TV show,
    sorts by popularity, and downloads the first 10 to the hidden folder.
    Calls update_image(file_path) after downloading the first image.

    Args:
        tmdb_id (str): The TMDB ID of the media.
        media_type (str): "movie" or "tv".
        api_key (str): Your TMDB API key.
    """
    # TMDB URL to get images
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/images?language=en&api_key={tmdb_key}"

    response = requests.get(url)
    if response.status_code != 200:
        update_image(placeholder_image_path)
        return

    data = response.json()
    backdrops = data.get("backdrops", [])

    # Filter English backdrops that have a 16:9 aspect ratio
    english_backdrops = [
        b for b in backdrops
        if b.get("iso_639_1") in (None, "en") and b["width"] / b["height"] == 16 / 9
    ]

    # Sort by popularity (vote_average if available)
    english_backdrops.sort(key=lambda x: x.get("vote_average", 0), reverse=True)

    if still_path:
        english_backdrops.insert(0, {"file_path": still_path})

    global backdrop_list
    backdrop_list = english_backdrops

    if len(backdrop_list) == 0:
        # Load default image
        #default_image_path = hidden_folder + "/default.jpg"
        print("no image")
        print(placeholder_image_path)
        update_image(placeholder_image_path)
        return

    # Show the first image
    image_url = "https://image.tmdb.org/t/p/original" + english_backdrops[0]["file_path"]

    update_image(image_url)


def update_image(file_path_or_url):
    """Load and display the image using Pillow, accepts both file paths and URLs."""
    global thumbnail_image  # Prevent garbage collection
    global thumbnail_image_path_or_url
    thumbnail_image_path_or_url = file_path_or_url
    scrollable_frame.grid_forget()  # Hide the frame
    try:
        # If it's a URL, fetch the image from the URL
        if file_path_or_url.startswith("http"):
            response = requests.get(file_path_or_url)
            if response.status_code == 200:
                img = Image.open(BytesIO(response.content))  # Open the image from the URL
            else:
                raise Exception("Failed to fetch image from URL")
        else:
            img = Image.open(file_path_or_url)  # Open the image from the file path

        img = img.resize((192, 108), Image.Resampling.LANCZOS)  # Resize to fit UI
        thumbnail_image = ImageTk.PhotoImage(img)  # Convert for tkinter
        image_label.config(image=thumbnail_image, text="")  # Remove text after loading image
    except Exception as e:
        tmdb_title_var.set(f"Error: Could not load image: {e}")

def select_image():
    """Open file dialog to select an image and update the display."""
    file_path = filedialog.askopenfilename(title="Select An Image", filetypes=[
        ("All Image Files", "*.png *.jpg *.jpeg *.gif *.bmp"),
        ("PNG Files", "*.png"),
        ("JPEG Files", "*.jpg *.jpeg"),
        ("GIF Files", "*.gif"),
        ("BMP Files", "*.bmp"),
        ("All Files", "*.*")
    ])
    if file_path:
        update_image(file_path)



def check_and_create_settings():
    settings_file = os.path.join(hidden_folder, "settings.json")

    # Default values for settings
    default_settings = {
        "download_folder": home_folder,
        "file_extension": ".mp4"
    }

    # Check if settings.json exists
    if not os.path.exists(settings_file):
        # Create the settings file with default values
        os.makedirs(hidden_folder, exist_ok=True)  # Ensure the hidden folder exists
        with open(settings_file, 'w') as f:
            json.dump(default_settings, f, indent=4)
        print(f"settings.json created with default values.")
        settings = default_settings
    else:
        # Load existing settings from the file
        with open(settings_file, 'r') as f:
            settings = json.load(f)

    download_folder = settings.get("download_folder")
    file_extension = settings.get("file_extension")

    print(f"Loaded settings: Download folder: {download_folder}, File extension: {file_extension}")

    # Apply the settings (this will depend on your specific select_folder and select_extension functions)
    select_folder(download_folder)  # Update the folder in your app
    selected_extension.set(file_extension)  # Update the file extension in your app

# Function to update the settings and save the download folder and/or extension
def update_settings(download_folder=None, file_extension=None):
    settings_file = os.path.join(hidden_folder, "settings.json")

    # Load existing settings
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as f:
            settings = json.load(f)
    else:
        settings = {}

    # Update settings if new values are provided
    if download_folder:
        settings["download_folder"] = download_folder

    if file_extension:
        settings["file_extension"] = file_extension

    # Save updated settings back to the file
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=4)

    print(f"Settings updated: Download folder: {settings.get('download_folder')}, File extension: {settings.get('file_extension')}")



def hash_url(url):
    """Generate a short deterministic identifier from a URL."""
    sha1_hash = hashlib.sha1(url.encode()).digest()  # Compute SHA-1 hash
    encoded = base64.b32encode(sha1_hash).decode()[:10]  # Base32 encode & truncate
    return encoded

def sanitize_filename(filename):
    """Sanitize filename by replacing invalid characters and ensuring it doesn't start with a dot."""
    filename = filename.strip()  # Remove leading/trailing spaces
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)  # Replace invalid characters
    if filename.startswith('.'):
        filename = '_' + filename[1:]  # Replace leading dot with underscore
    return filename

def select_folder(folder=None):
    """Let the user select a download folder."""
    global download_folder
    if not folder:
        folder = filedialog.askdirectory()
    if folder:
        download_folder = folder
        folder_var.set(f"Save To: {folder}")
        update_settings(download_folder=download_folder)

def disable_inputs(disable=True):
    """Disables all inputs so the user can't change anything"""
    if disable:
        str = "disabled"
        toggle_image_selection(show=False)
        image_label.bind("<Button-1>", lambda event: toggle_image_selection(show=False))
    else:
        str = "normal"
        image_label.bind("<Button-1>", lambda event: toggle_image_selection())
    url_entry.config(state=str)
    tmdb_id_entry.config(state=str)
    movie_radio.config(state=str)
    tv_radio.config(state=str)
    season_entry.config(state=str)
    episode_entry.config(state=str)
    folder_button.config(state=str)
    filename_entry.config(state=str)
    extension_dropdown.config(state=str)


def discard_download():
    """Deletes all files associated with the current download"""
    url = url_entry.get().strip()
    hashed_id = hash_url(url)
    # Find all files containing the hashed_id in their filenames
    files_to_delete = glob.glob(os.path.join(hidden_folder, f"*{hashed_id}*"))

    for file in files_to_delete:
        try:
            os.remove(file)
            print(f"Deleted: {file}")
        except Exception as e:
            print(f"Error deleting {file}: {e}")

    output_var.set("Discarded current download.")
    update_ui(" ", " ", " ", " ")
    submit_button.config(text="Start Download", command=start_download)
    discard_button.pack_forget()

def update_ui_from_queue():
    """Check the queue for progress updates and update the UI."""
    try:
        while True:
            percentage, file_size, eta, fragments = progress_queue.get_nowait()
            update_ui(percentage, file_size, eta, fragments)
    except queue.Empty:
        root.after(100, update_ui_from_queue)  # Check the queue again after 100ms

def update_ui(percentage, file_size, eta, fragments):
    if percentage == " ":
        progress_bar["value"] = 0
        progress_var.set(percentage)
    else:
        percent = float(percentage[:-1])
        progress_bar["value"] = percent
        progress_var.set(percentage)
    if fragments:
        fragment_var.set(fragments)
    if type(eta) == str:
        eta = eta
    else:
        hours = int(eta // 3600)
        minutes = int((eta % 3600) // 60)
        seconds = int(eta % 60)
        eta = ""
        if hours > 0:
            eta += f"{hours}h "
        if minutes > 0 or hours > 0:  # Only include minutes if hours are present or minutes are non-zero
            eta += f"{minutes}m "
        eta += f"{seconds}s"
    eta_var.set(eta)
    if file_size:
        size_var.set(file_size)

def stop_download():
    """Stop the download process."""
    stop_event.set()

    if download_process:
        download_process.terminate()

    output_var.set("Pausing Download...")

    # Enable the url input again
    url_entry.config(state="normal")


def start_download(startingText = "Starting Download..."):

    # Disable the url entry
    url_entry.config(state="disabled")

    url = url_entry.get().strip()
    if not url:
        output_var.set("Error: enter a url to download")
        output_label.config(fg="red")
        url_entry.config(state="normal")
        return
    else:
        output_var.set(startingText)
        output_label.config(fg="systemTextColor")

    stop_event.clear()
    discard_button.pack_forget()
    hashed_id = hash_url(url)

    user_filename = filename_entry.get().strip()
    if not user_filename:
        print("no file name")
        # Delete any existing text in the filename_entry box
        filename_entry.delete(0, tk.END)
        # Insert new text
        filename_entry.insert(0, "Untitled")
        user_filename = "Untitled"


    download_path = os.path.join(hidden_folder, f"{hashed_id}.%(ext)s")

    ydl_opts = {'format': 'best', 'outtmpl': download_path}

    def progress_hook(d):
        """Callback function to process download progress and check for cancellation."""
        if stop_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Download canceled by user.")

        print('#########################')
        print(d)
        print('#########################')

        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0%')
            if "m" in percent_str:
                percent = percent_str.split('m')[1].split('%')[0] + '%'
            else:
                percent = percent_str.strip()
            file_size = d.get('_total_bytes_estimate_str', 'N/A').strip()
            eta = d.get('eta', -1)
            fragments = str(d.get('fragment_index')) + "/" + str(d.get('fragment_count'))

            #progress_text = f"Downloading: {percent} | Speed: {speed} | ETA: {eta}"
            root.after(0, update_ui, percent, file_size, eta, fragments)  # Update UI safely
            output_var.set("Downloading...")

        elif d['status'] == 'finished':
            percent = '100%'
            file_size = d.get('_total_bytes_str', 'N/A').strip()
            eta = "Done"
            fragments = None
            global original_file
            original_file = d.get('filename')
            root.after(0, update_ui, percent, file_size, eta, fragments)
            output_var.set("Download Finished!")

    def download_video():
        global download_process
        try:
            # Prepare yt-dlp options
            ydl_opts = {
                'format': 'best',  # Download the best quality
                'outtmpl': download_path,  # Path where the file will be saved
                'progress_hooks': [lambda d: progress_hook(d)],  # Progress hook with stop_event
                'quiet': False  # Show output to the console
                #'ffmpeg_location': FFMPEG_PATH,  # Ensure ffmpeg is found
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Start the download
                download_process = ydl.download([url])

            # Once download finishes, handle file renaming and conversion
            if not stop_event.is_set():
                print("Download finished, cleaning up")
                output_var.set("Preparing for file cleaning...")
                file_extension = selected_extension.get()

                user_filename = filename_entry.get().strip()
                if not user_filename:
                    print("no file name")
                    filename_entry.delete(0, tk.END)
                    filename_entry.insert(0, "Untitled")
                    user_filename = "Untitled"

                user_filename = sanitize_filename(user_filename)
                disable_inputs()

                downloaded_files = glob.glob(os.path.join(hidden_folder, f"{hashed_id}.*"))
                if downloaded_files:
                    global original_file
                    ext = os.path.splitext(original_file)[1]
                    temp_file = f'{hidden_folder}/{hashed_id}_temp{file_extension}'
                    new_file = f'{hidden_folder}/{user_filename}{file_extension}'
                    final_destination = f'{download_folder}/{user_filename}{file_extension}'

                    # output_var.set("Downloading Subtitles...")
                    # foreign_subs_exist = False
                    # subtitle_paths = get_subtitles()
                    # subtitle_paths = {"subtitles": None, "foreign_subtitles": None}
                    # print(subtitle_paths)

                    output_var.set("Converting file to " + file_extension)

                    # Conversion using FFmpeg (if needed)
                    conversion_process = subprocess.Popen(
                        [FFMPEG_PATH, '-i', original_file, '-c:v', 'copy', '-c:a', 'copy', '-metadata:s:a:0', 'language=eng', '-metadata:s:v:0', 'language=eng', '-movflags', 'faststart', temp_file, '-y'],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                    )

                    for line in conversion_process.stderr:
                        if stop_event.is_set():
                            conversion_process.terminate()
                            break
                        root.after(0, process_output, line.strip())
                        #output_var.set(line.strip())

                    conversion_process.wait()

                    if conversion_process.returncode == 0:
                        print(f"Conversion to {file_extension} successful.")
                        output_var.set("Conversion Complete!")

                        output_var.set("Downloading Subtitles...")
                        subtitle_paths = get_subtitles()
                        subs = subtitle_paths["subtitles"]
                        subs_foreign = subtitle_paths["foreign_subtitles"]
                        foreign_subs_exist = False
                        if subs and subs_foreign:
                            foreign_subs_exist = True
                            subtitles_command = [MP4BOX_PATH, temp_file, '-add', f'{subs}:hdlr=sbtl:lang=eng:group=2:layer=-1:disabled', '-add', f'{subs_foreign}:hdlr=sbtl:lang=eng:group=2:layer=-1:txtflags=0xC0000000', '-udta', '4:type=tagc:str=public.main-program-content', '-udta', '3:type=tagc:str=public.auxiliary-content', '-out', new_file, '-flat']
                            subs_out = subprocess.run(subtitles_command)
                        elif subs:
                            subtitles_command = [MP4BOX_PATH, temp_file, '-add', f'{subs}:hdlr=sbtl:lang=eng:group=2:layer=-1', '-udta', '3:type=tagc:str=public.main-program-content', '-out', new_file, '-flat']
                            subs_out = subprocess.run(subtitles_command)

                        # Process metadata
                        global metadata
                        try:
                            resolution_command = [FFPROBE_PATH, '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'json', new_file]
                            resolution_result = subprocess.run(resolution_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            resolution_data = json.loads(resolution_result.stdout)
                            resolution = resolution_data['streams'][0]['height']
                            if not resolution or resolution < 720:
                                metadata['--hdvideo'] = "0"
                            elif resolution == 720:
                                metadata['--hdvideo'] = "1"
                            else:
                                metadata['--hdvideo'] = "2"
                        except Exception as e:
                            metadata['--hdvideo'] = "0"

                        metadata_command = [ATOMIC_PARSLEY_PATH, new_file, "--overWrite"]

                        # Add the plist content, it it is available
                        if plist_content:
                            metadata_command.append("--rDNSatom")
                            metadata_command.append(plist_content)
                            metadata_command.append("name=iTunMOVI")
                            metadata_command.append("domain=com.apple.iTunes")

                        for key, value in metadata.items():
                            metadata_command.append(key)
                            metadata_command.append(value)

                        # Remove the encoding tool metadata
                        metadata_command.append("--encodingTool")
                        metadata_command.append("")

                        output_var.set("Adding metadata...")
                        global thumbnail_image_path_or_url
                        if thumbnail_image_path_or_url != placeholder_image_path:
                            download_thumbnail()
                            metadata_command.append("--artwork")
                            metadata_command.append(thumbnail_image_path_or_url)
                        else:
                            print("artowrk is default")

                        print(metadata_command)
                        metadata_process = subprocess.Popen(
                            metadata_command,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                        )

                        for line in metadata_process.stdout:
                            if stop_event.is_set():
                                metadata_process.terminate()
                                break
                            root.after(0, process_output, line.strip())

                        metadata_process.wait()

                        if metadata_process.returncode == 0:
                            print("Metadata added successfully")
                            output_var.set("Metadata Added Successfully!")
                        else:
                            output_var.set("Error during metadata addition!")
                            output_label.config(fg="red")
                            return

                        submit_button.config(text="Start New Download", command=start_download)
                        disable_inputs(False)
                        # Ensure the destination directory exists
                        destination_dir = os.path.dirname(final_destination)
                        os.makedirs(destination_dir, exist_ok=True)
                        # Save the downloaded media file to the final destination folder
                        os.rename(new_file, final_destination)
                        os.remove(original_file)
                        extra_files = glob.glob(os.path.join(hidden_folder, f"{hashed_id}*"))
                        if extra_files:
                            for i in range(len(extra_files)):
                                os.remove(extra_files[i])
                        output_var.set("Video saved successfully!")
                        if foreign_subs_exist:
                            output_var.set("Video saved successfully! Foreign subtitles may need adjustment.")

                    else:
                        output_var.set("Error during conversion!")
                        output_label.config(fg="red")

        except yt_dlp.utils.DownloadCancelled:
            submit_button.config(text="Resume Download", command=lambda: start_download("Resuming Download..."))
            discard_button.pack(side="left")
            output_var.set("")
            print("Download was canceled by the user")

        except Exception as e:
            submit_button.config(text="Try Again", command=lambda: start_download("Retrying..."))
            # Enable the url input again
            url_entry.config(state="normal")
            output_var.set("Error: " + str(e))
            output_label.config(fg="red")
            print(e)

    # Run download in a separate thread to avoid blocking the GUI
    download_thread = threading.Thread(target=download_video, daemon=True)
    download_thread.start()
    submit_button.config(text="Pause Download", fg="blue", command=stop_download)

def process_output(line):
    """Process the output from yt-dlp."""
    print('-------------------')
    print(line)
    print('-------------------')
    if "[download]" in line:
        if "Destination:" in line:
            output_var.set("")
            return
        if "Got error:" in line:
            parts = line.split("Retrying")
            message = parts[-1]
            output_var.set("Got error: Retrying" + message)
            output_label.config(fg="red")
            return
        parts = line.split()
        percentage = parts[1]
        file_size = parts[4]
        eta = parts[8]
        fragments = parts[10][:-1]
        progress_queue.put((percentage, file_size, eta, fragments))  # Put progress info in queue
    elif "[generic]" in line:
        if "Extracting URL" in line:
            line = "Extracting URL"
        parts = line.split(":")
        message = parts[-1]
        output_var.set(message)
    elif "[hlsnative]" in line:
        parts = line.split()
        message = " ".join(parts[1:])
        output_var.set(message)

    output_label.config(fg="systemTextColor")


def makePlist(cast, directors, producers, screenwriters, studios):

	plist_header = """<?xml version="1.0" encoding="UTF-8"?>
	<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
	<plist version="1.0">
	<dict>
	"""

	plist_cast = """	<key>cast</key>
		<array>
	"""
	for i in range(len(cast)):
		actor = cast[i]
		plist_cast += f"""		<dict>
				<key>name</key>
				<string>{actor}</string>
			</dict>
	"""
	plist_cast += """	</array>
	"""

	plist_directors = """	<key>directors</key>
		<array>
	"""
	for i in range(len(directors)):
		director = directors[i]
		plist_directors += f"""		<dict>
				<key>name</key>
				<string>{director}</string>
			</dict>
	"""
	plist_directors += """	</array>
	"""

	plist_producers = """	<key>producers</key>
		<array>
	"""
	for i in range(len(producers)):
		producer = producers[i]
		plist_producers += f"""		<dict>
				<key>name</key>
				<string>{producer}</string>
			</dict>
	"""
	plist_producers += """	</array>
	"""

	plist_screenwriters = """	<key>screenwriters</key>
		<array>
	"""
	for i in range(len(screenwriters)):
		screenwriter = screenwriters[i]
		plist_screenwriters += f"""		<dict>
				<key>name</key>
				<string>{screenwriter}</string>
			</dict>
	"""
	plist_screenwriters += """	</array>
	"""

	plist_studio = f"""	<key>studio</key>
		<string>{studios}</string>
	"""

	plist_footer = """</dict>
	</plist>"""

	final_plist = plist_header + plist_cast + plist_directors + plist_producers + plist_screenwriters + plist_studio + plist_footer
	#print(final_plist)
	return final_plist


def cleanup_old_files():
    def clean_old_files():
        now = time.time()
        age_limit = 24 * 60 * 60  # 1 day

        if not os.path.isdir(hidden_folder):
            return

        for filename in os.listdir(hidden_folder):
            file_path = os.path.join(hidden_folder, filename)
            if filename in {"settings.json"}:
                continue
            if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > age_limit:
                try:
                    os.remove(file_path)
                    print(f"Deleted: {file_path}")
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")

    # Run cleanup in a separate thread
    cleanup_thread = threading.Thread(target=clean_old_files, daemon=True)
    cleanup_thread.start()
    print("cleaning...")


def get_subtitles():

    url = "https://api.opensubtitles.com/api/v1/subtitles"

    current_tmdb_id = tmdb_id_entry.get().strip()

    if tv_var.get():
        # The media is a tv show
        season = season_entry.get().strip()
        episode = episode_entry.get().strip()
        querystring = {"tmdb_id":current_tmdb_id,"languages":"en","season_number":season,"episode_number":episode}


    else:
        # The media is a movie
        querystring = {"tmdb_id":current_tmdb_id,"languages":"en"}


    headers = {
        "User-Agent": opensubtitles_user_agent,
        "Api-Key": opensubtitles_key
    }

    response = requests.get(url, headers=headers, params=querystring)

    print(response.json())

    def get_best_subtitles(subtitle_data):
        try:
            if not subtitle_data.get("data"):
                return None

            subtitles = subtitle_data["data"]

            # Sorting function based on multiple criteria
            def subtitle_score(sub):
                attributes = sub.get("attributes")
                return (
                    attributes.get("hearing_impaired") == False,  # Prefer non-hearing-impaired
                    attributes.get("from_trusted", False),        # Prefer from trusted sources
                    attributes.get("ratings", 0.0),               # Prefer higher ratings
                    attributes.get("download_count", 0),          # Prefer higher download counts
                )

            # Sort subtitles with the best one first
            sorted_subtitles = sorted(subtitles, key=subtitle_score, reverse=True)

            # Find the best foreign parts only subtitle
            foreign_parts_subs = [
                sub for sub in subtitles if sub.get("attributes").get("foreign_parts_only", False)
            ]
            best_foreign_parts_sub = (
                sorted(foreign_parts_subs, key=subtitle_score, reverse=True)[0]
                if foreign_parts_subs else None
            )

            # Get the best non foreign subtitle
            non_foreign_parts_subs = [
                sub for sub in subtitles if not sub.get("attributes").get("foreign_parts_only", False)
            ]
            best_non_foreign_parts_sub = (
                sorted(non_foreign_parts_subs, key=subtitle_score, reverse=True)[0]
                if non_foreign_parts_subs else None
            )

            # Return both subtitles if we found a foreign parts subtitle, otherwise just the best one
            return [best_non_foreign_parts_sub, best_foreign_parts_sub] if best_foreign_parts_sub else [best_non_foreign_parts_sub]

        except:
            return None

    def clean_subtitles(input_file, output_file):
        with open(input_file, "r", encoding="utf-8") as infile, open(output_file, "w", encoding="utf-8") as outfile:
            buffer = []
            for line in infile:
                # Remove SSA/ASS positioning tags like {\an8}, but keep text
                line = re.sub(r"\{\\an\d+\}", "", line)

                # Store non-empty lines in a buffer
                if line.strip():
                    buffer.append(line)
                else:
                    # If buffer contains a font tag, discard the entire block
                    if any("<font" in l for l in buffer):
                        buffer.clear()
                    else:
                        outfile.writelines(buffer)
                        outfile.write("\n")
                        buffer.clear()
        # Remove the original file
        os.remove(input_file)

    def download_subtitles(file_id, file_path):
        global opensubtitles_token
        if opensubtitles_token is None:
            url = "https://api.opensubtitles.com/api/v1/login"

            payload = {
                "username": "unsightlyPinnipedCalm",
                "password": "P@ssw0rd"
            }
            headers = {
                "Content-Type": "application/json",
                "User-Agent": opensubtitles_user_agent,
                "Accept": "application/json",
                "Api-Key": opensubtitles_key
            }

            response = requests.post(url, json=payload, headers=headers)
            response_dict = response.json()
            print(response_dict)

            status = response_dict['status']
            print(status)
            opensubtitles_token = response_dict['token']
            print(opensubtitles_token)

        url = "https://api.opensubtitles.com/api/v1/download"

        payload = { "file_id": file_id }
        headers = {
            "User-Agent": opensubtitles_user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {opensubtitles_token}",
            "Api-Key": opensubtitles_key
        }

        response = requests.post(url, json=payload, headers=headers)

        print(response.json())

        srt_link = response.json()['link']

        # Download it now
        dl_response = requests.get(srt_link, stream=True)
        with open(file_path, "wb") as file:
            for chunk in dl_response.iter_content(chunk_size=8192):
                file.write(chunk)

        return file_path


    best_subtitles = get_best_subtitles(response.json())

    download_url = url_entry.get().strip()
    hash = hash_url(download_url)
    temp_sub_path = hidden_folder + "/sub.srt"
    temp_foreign_sub_path = hidden_folder + "/sub_foreign.srt"
    sub_path = hidden_folder + "/" + hash + "_sub.srt"
    sub_foreign_path = hidden_folder + "/" + hash + "_sub_foreign.srt"

    try:

        if not best_subtitles:
            print("No subtitles available")
            return {"subtitles": None, "foreign_subtitles": None}

        elif len(best_subtitles) > 1:
            sub = download_subtitles(best_subtitles[0]['attributes']['files'][0]['file_id'], temp_sub_path)
            clean_subtitles(sub, sub_path)

            sub_foreign = download_subtitles(best_subtitles[1]['attributes']['files'][0]['file_id'], temp_foreign_sub_path)
            clean_subtitles(sub_foreign, sub_foreign_path)

            return {"subtitles": sub_path, "foreign_subtitles": sub_foreign_path}
        else:
            sub = download_subtitles(best_subtitles[0]['attributes']['files'][0]['file_id'], temp_sub_path)
            clean_subtitles(sub, sub_path)

            return {"subtitles": sub_path, "foreign_subtitles": None}

    except:
        return {"subtitles": None, "foreign_subtitles": None}






# Create the main window
root = tk.Tk()
root.title(app_name)

# File name entry (on the same line)
url_input_frame = tk.Frame(root)
url_input_frame.grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=5)

# Create and pack the widgets
url_label = tk.Label(url_input_frame, text="Video URL:")
url_label.pack(side="left", padx=5)

url_entry = tk.Entry(url_input_frame, width=55)
url_entry.pack(side="left", padx=5)

# Movie/TV toggle (side by side)
tv_var = tk.BooleanVar()

# File name entry (on the same line)
tmdb_input_frame = tk.Frame(root)
tmdb_input_frame.grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=5)

tmdb_id_label = tk.Label(tmdb_input_frame, text="TMDB ID:")
tmdb_id_label.pack(side="left", padx=5)

tmdb_id_entry = tk.Entry(tmdb_input_frame, width=7)
tmdb_id_entry.pack(side="left", padx=5)

movie_radio = tk.Radiobutton(tmdb_input_frame, text="Movie", variable=tv_var, value=False)
movie_radio.pack(side="left", padx=10, pady=5)

tv_radio = tk.Radiobutton(tmdb_input_frame, text="TV", variable=tv_var, value=True)
tv_radio.pack(side="left", padx=10, pady=5)

season_label = tk.Label(tmdb_input_frame, text="Season:")
season_label.pack(side="left", padx=5)

season_entry = tk.Entry(tmdb_input_frame, width=5)
season_entry.pack(side="left", padx=5)

episode_label = tk.Label(tmdb_input_frame, text="Episode:")
episode_label.pack(side="left", padx=5)

episode_entry = tk.Entry(tmdb_input_frame, width=5)
episode_entry.pack(side="left", padx=5)

# Bind the event to each entry
tmdb_id_entry.bind("<KeyRelease>", retrieve_tmdb_data)
season_entry.bind("<KeyRelease>", retrieve_tmdb_data)
episode_entry.bind("<KeyRelease>", retrieve_tmdb_data)

# TMDB movie / series title
tmdb_title_var = tk.StringVar()
tmdb_title_label = tk.Label(root, bg="#999999", textvariable=tmdb_title_var)
tmdb_title_label.grid(row=2, column=0, sticky="nsew", columnspan=2, padx=5, pady=5)

# movie_series_title = tk.Label(tmdb_info_frame, text="Unknown Movie Name", bg="#999999")
# movie_series_title.pack(anchor="center", padx=5)
#
# episode_title = tk.Label(tmdb_info_frame, text="Unknown Episode Title", bg="#999999")
# episode_title.pack(side="left", padx=5)


# Ensure widgets are hidden but still taking up space in layout
def toggle_season_episode():
    if tv_var.get():
        season_label.pack(side="left", padx=5)
        season_entry.pack(side="left", padx=5)
        episode_label.pack(side="left", padx=5)
        episode_entry.pack(side="left", padx=5)
        season_entry.config(state="normal")
        episode_entry.config(state="normal")

    else:
        season_label.pack_forget()
        season_entry.pack_forget()
        episode_label.pack_forget()
        episode_entry.pack_forget()
        season_entry.config(state="disabled")
        episode_entry.config(state="disabled")
        # Clear focus from the season and episode entry boxes
        season_entry.selection_clear()
        episode_entry.selection_clear()

    tmdb_input_frame.update_idletasks()
    retrieve_tmdb_data()

# Bind the radio button change event to the toggle function
tv_var.trace("w", lambda *args: toggle_season_episode())

# Folder Selection Frame
folder_frame = tk.Frame(root)
folder_frame.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)

folder_var = tk.StringVar(value=f"Save To: {download_folder}")
folder_button = tk.Button(folder_frame, text="Select Destination Folder", command=select_folder)
folder_button.pack(side="left", padx=5)
folder_label = tk.Label(folder_frame, textvariable=folder_var)
folder_label.pack(side="left")

# File name entry (on the same line)
filename_frame = tk.Frame(root)
filename_frame.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=5)

filename_label = tk.Label(filename_frame, text="File Name:")
filename_label.pack(side="left", padx=(0, 5))

filename_entry = tk.Entry(filename_frame, width=20)
filename_entry.pack(side="left")

# List of available file extensions
extensions = [".mp4", ".m4v", ".mkv", ".avi", ".mov"]

# Variable to store selected extension
selected_extension = tk.StringVar()
selected_extension.set(extensions[0])  # Default to .mp4

# Dropdown menu for file extensions
extension_dropdown = tk.OptionMenu(filename_frame, selected_extension, *extensions)
extension_dropdown.pack(side="left")

# Function to handle extension selection and update settings
def on_extension_select(*args):
    selected = selected_extension.get()
    print(selected)
    update_settings(file_extension=selected)

# Bind the selection event to the dropdown
selected_extension.trace("w", on_extension_select)

# Submit and Discard buttons (side by side)
button_frame = tk.Frame(root)
button_frame.grid(row=5, column=0, columnspan=2, pady=10, padx=10, sticky="w")

submit_button = tk.Button(button_frame, text="Start Download", default="active", command=start_download)
submit_button.pack(side="left", padx=(0, 5))

discard_button = tk.Button(button_frame, text="Discard Download", fg="red", command=discard_download)
discard_button.pack(side="left")
discard_button.pack_forget()

output_var = tk.StringVar()
output_label = tk.Label(button_frame, textvariable=output_var)
output_label.pack(side="left")

# Progress bar widget
progress_bar = ttk.Progressbar(root, orient="horizontal", length=300, mode="determinate")
progress_bar.grid(row=6, column=0, pady=0, padx=10, sticky="w")

progress_frame = tk.Frame(root)
progress_frame.grid(row=7, column=0, sticky="w", padx=5, pady=2)

# Progress information labels
progress_label = tk.Label(progress_frame, text="Downloading:")
progress_label.grid(row=7, column=0, sticky="w", padx=10, pady=2)

fragment_label = tk.Label(progress_frame, text="Fragments:")
fragment_label.grid(row=8, column=0, sticky="w", padx=10, pady=2)

eta_label = tk.Label(progress_frame, text="ETA:")
eta_label.grid(row=9, column=0, sticky="w", padx=10, pady=2)

size_label = tk.Label(progress_frame, text="Estimated File Size:")
size_label.grid(row=10, column=0, sticky="w", padx=10, pady=2)

# Progress information values (separate column for alignment)
progress_var = tk.StringVar()
progress_value = tk.Label(progress_frame, textvariable=progress_var)
progress_value.grid(row=7, column=1, sticky="w", padx=5, pady=2)

fragment_var = tk.StringVar()
fragment_value = tk.Label(progress_frame, textvariable=fragment_var)
fragment_value.grid(row=8, column=1, sticky="w", padx=5, pady=2)

eta_var = tk.StringVar()
eta_value = tk.Label(progress_frame, textvariable=eta_var)
eta_value.grid(row=9, column=1, sticky="w", padx=5, pady=2)

size_var = tk.StringVar()
size_value = tk.Label(progress_frame, textvariable=size_var)
size_value.grid(row=10, column=1, sticky="w", padx=5, pady=2)

tmdb_image_frame = tk.Frame(root, bg="#999999")
tmdb_image_frame.grid(row=7, column=1, sticky="e", padx=5, pady=2)

# tmdb_title_var = tk.StringVar()
# tmdb_title_var.set("Title Here")
# tmdb_title = tk.Label(tmdb_info_display, textvariable=tmdb_title_var)
# tmdb_title.grid(row=0, column=0, sticky="w", padx=5, pady=2)
#
# tmdb_episode_title_var = tk.StringVar()
# tmdb_episode_title_var.set("Episode Title Here")
# tmdb_episode_title = tk.Label(tmdb_info_display, textvariable=tmdb_episode_title_var)
# tmdb_episode_title.grid(row=1, column=0, sticky="w", padx=5, pady=2)

image_label = tk.Label(tmdb_image_frame, text="No Thumbnail", width=192, height=108)
image_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)
# Bind left-click to change image
image_label.bind("<Button-1>", lambda event: toggle_image_selection())

# image_button = tk.Button(tmdb_info_display, text="Select Image", command=select_image)
# image_button.grid(row=1, column=0, sticky="w", padx=5, pady=2)


# Frame for scrollable images at the bottom
scrollable_frame = tk.Frame(root)
scrollable_frame.grid(row=11, column=0, sticky="ew", padx=5, pady=5, columnspan=2)

# Canvas for scrolling functionality
canvas = tk.Canvas(scrollable_frame, height=60, width=600, bg='#999999', bd=0, highlightthickness=0)  # Set height of the canvas
canvas.grid(row=0, column=0, sticky="ew", columnspan=2)

# Frame to contain the images inside the canvas
image_frame = tk.Frame(canvas)
canvas.create_window((0, 0), window=image_frame, anchor="nw")

choose_custom_button = tk.Button(scrollable_frame, text="Choose Custom Image", command=select_image)
choose_custom_button.grid(row=1, column=0)

# Ensure the grid cell expands in all directions (vertically and horizontally)
scrollable_frame.grid_rowconfigure(0, weight=1)  # This will make the row expand vertically
scrollable_frame.grid_columnconfigure(0, weight=1)  # This will make the column expand horizontally

scrollable_frame.grid_forget()  # Hide the frame




def toggle_image_selection(show=None):
    """
    Creates a horizontally scrollable frame at the bottom of the window and populates it with images from the provided URLs.

    Args:
        root (tk.Tk): The main Tkinter window.
        image_urls (list): A list of image URLs to be displayed.
    """
    global backdrop_list
    global last_load_id
    print(backdrop_list)

    current_tmdb_id = tmdb_id_entry.get().strip() + str(tv_var.get())

    if show is True:
        # Always show the frame
        scrollable_frame.grid(row=11, column=0, sticky="ew", padx=5, pady=5, columnspan=2)
    elif show is False:
        # Always hide the frame
        scrollable_frame.grid_forget()
    else:
        # Toggle visibility if show is None
        if scrollable_frame.winfo_ismapped():
            scrollable_frame.grid_forget()  # Hide the frame
        else:
            scrollable_frame.grid(row=11, column=0, sticky="ew", padx=5, pady=5, columnspan=2)  # Show the frame


    if last_load_id == current_tmdb_id:
        print("Same: " + current_tmdb_id)
        return
    print("Different: " + current_tmdb_id)
    last_load_id = current_tmdb_id

    for widget in image_frame.winfo_children():
        widget.destroy()

    def load_images():
        """Load images from URLs and place them inside the scrollable frame."""
        for i in range(len(backdrop_list)):
            url = "https://image.tmdb.org/t/p/original" + backdrop_list[i]["file_path"]
            try:
                # Fetch the image from the URL
                response = requests.get(url)
                if response.status_code == 200:
                    img = Image.open(BytesIO(response.content))
                    img.thumbnail((96, 54))  # Resize to fit within the frame
                    img = ImageTk.PhotoImage(img)

                    # Create a label for each image
                    img_label = tk.Label(image_frame, image=img)
                    img_label.image = img  # Keep a reference to avoid garbage collection
                    img_label.grid(row=0, column=i, padx=5, pady=5)
                    # Use a lambda to pass the specific URL to the function
                    img_label.bind("<Button-1>", lambda event, url=url: update_image(url))
                else:
                    print(f"Failed to fetch image from {url}")
            except Exception as e:
                print(f"Error loading image from {url}: {e}")


        # Update the scrollable region after adding images
        image_frame.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

        # Enable horizontal dragging to scroll the canvas
        def on_mouse_drag(event):
            canvas.scan_dragto(event.x, 0, gain=1)

        # Bind mouse drag events to scroll horizontally
        canvas.bind("<Button-1>", lambda event: canvas.scan_mark(event.x, 0))
        canvas.bind("<B1-Motion>", on_mouse_drag)

        # Optionally: Allow mouse wheel scrolling
        def on_mouse_wheel(event):
            canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")

        canvas.bind_all("<MouseWheel>", on_mouse_wheel)

    # Load the images from URLs
    threading.Thread(target=load_images, daemon=True).start()

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and PyInstaller .app """
    if hasattr(sys, '_MEIPASS'):
        # Running inside PyInstaller bundle
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(relative_path)

placeholder_image_path = resource_path("resources/placeholder.png")


def parse_arguments(url_handler=None):
    """
    Parses command-line arguments and returns structured data.

    Returns:
        dict: A dictionary containing parsed values.
    """

    if url_handler is None:
        args = sys.argv[1:]  # Exclude script name
    else:
        args = [None] * 4
        parts = url_handler.split("://params?")
        url_handler = "://params?".join(parts[1:])
        parts = url_handler.split("&")
        for i in range(len(parts)):
            part = parts[i]
            # Check for tmdb ID
            if part.startswith('tmdb='):
                args[1] = part[len('tmdb='):]
            # Check for season
            elif part.startswith('s='):
                args[2] = part[len('s='):]
            # Check for episode
            elif part.startswith('e='):
                args[3] = part[len('e='):]
            # Check for URL
            elif part.startswith('url='):
                url_handler = "&".join(parts[i:])
                args[0] = url_handler[len('url='):]

        if args[1] == None:
            args[2] = None
            args[3] = None
        args = [x for x in args if x is not None]

    if len(args) < 1:
        print("No parameters passed")
        return

    if len(args) >= 1:
        print("URL parameter passed")
        url = args[0]
        url_entry.insert(0, url)

    if len(args) >= 2:
        tmdb_id = args[1]
        tmdb_id_entry.insert(0, tmdb_id)

        if len(args) >= 4:
            print("Parameters passed for TV Show")
            tv_var.set(True)
            season = args[2]
            season_entry.insert(0, season)
            episode = args[3]
            episode_entry.insert(0, episode)
        else:
            print("Parameters passed for Movie")

    # Ensure retrieve_tmdb_data() and start_download() runs after the UI is displayed
    root.after(100, retrieve_tmdb_data)
    root.after(100, start_download)

parse_arguments()

# Load default image at startup
#default_image_path = hidden_folder + "/default.jpg"  # Ensure this file exists in the project directory
update_image(placeholder_image_path)

# Call the toggle function after initializing
toggle_season_episode()

# Load the settings
check_and_create_settings()

# Clean up old files
cleanup_old_files()

def get_app_bundle_path():
    """Finds the full path to the .app bundle."""
    exec_path = os.path.abspath(sys.argv[0])  # Get the full path of the running executable
    while not exec_path.endswith(".app") and exec_path != "/":
        exec_path = os.path.dirname(exec_path)  # Move up the directory tree

    if exec_path.endswith(".app"):
        return exec_path
    return None  # Not running as an app

def update_info_plist():
    """Updates the app's Info.plist to include the custom URL scheme."""
    app_bundle_path = get_app_bundle_path()
    if not app_bundle_path:
        #url_entry.insert(0, "Not running as an app bundle.")
        print("Not running as an app bundle.")
        return

    plist_path = os.path.join(app_bundle_path, "Contents", "Info.plist")

    if not os.path.exists(plist_path):
        print("Info.plist not found!")
        #url_entry.insert(0, "Info.plist not found! " + plist_path)
        return

    try:
        with open(plist_path, "rb") as f:
            plist_data = plistlib.load(f)

        # Ensure CFBundleURLTypes is present
        if "CFBundleURLTypes" not in plist_data:
            plist_data["CFBundleURLTypes"] = []

        # Define the custom URL scheme
        custom_scheme = {
            "CFBundleURLName": "com.yourcompany.StreamFetchTagger",
            "CFBundleURLSchemes": ["StreamFetchTagger"]
        }

        # Avoid duplicate entries
        if custom_scheme not in plist_data["CFBundleURLTypes"]:
            plist_data["CFBundleURLTypes"].append(custom_scheme)

            with open(plist_path, "wb") as f:
                plistlib.dump(plist_data, f)

            print(f"Updated Info.plist at {plist_path}")
            #url_entry.insert(0, f"Updated Info.plist at {plist_path}")

    except Exception as e:
        print(f"Failed to update Info.plist: {e}")
        #url_entry.insert(0, f"Failed to update Info.plist: {e}")

def register_url_scheme():
    """Registers the custom URL scheme with macOS."""
    app_bundle_path = get_app_bundle_path()
    if not app_bundle_path:
        print("Not running as an app bundle. Skipping registration.")
        return

    try:
        subprocess.run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister",
                        "-f", app_bundle_path], check=True)
        print("Successfully registered URL scheme.")
    except Exception as e:
        print(f"Error registering URL scheme: {e}")

# Automatically register the custom url scheme
if get_app_bundle_path():
        update_info_plist()
        register_url_scheme()


root.createcommand("::tk::mac::LaunchURL", parse_arguments)

# if len(sys.argv) > 1:
#     incoming_url = sys.argv[1]
#     if incoming_url.startswith("StreamFetchTagger://"):
#         url_entry.insert(0, incoming_url)
#     else:
#         print("No valid URL scheme detected.")
#         url_entry.insert(0, "No valid URL scheme detected.")
# else:
#     print("No arguments provided.")
#     url_entry.insert(0, "No arguments provided. " + sys.argv[0])

# After initialization, start the queue checking
root.after(100, update_ui_from_queue)

# Parse the arguments passed to the script
root.after(100, parse_arguments)

# Start the GUI
root.mainloop()
