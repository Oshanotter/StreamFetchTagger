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

app_name = "StreamFetchTagger"
app_version = "1.4.0"
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

# Function to get the binary paths of the included resources
def get_binary_path(binary_name):
    """Finds the correct path to a bundled binary"""
    if getattr(sys, 'frozen', False):  # Running inside PyInstaller
        base_path = sys._MEIPASS  # PyInstaller's temp directory
    else:
        base_path = os.path.dirname(__file__)  # Running as a script

    return os.path.join(base_path, "binaries", binary_name)

# Define binary paths
FFMPEG_PATH = get_binary_path("ffmpeg")
MP4BOX_PATH = get_binary_path("MP4Box")
SUBLERCLI_PATH = get_binary_path("SublerCLI")

# Functions to retireve information and download assets about the video

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
        metadata = {}


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
                genre = convert_tmdb_to_apple_genres([g["name"] for g in show_data.get("genres", [])])
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
                rating = "TV Unrated"
                for rating_entry in rating_data.get("results", []):
                    if rating_entry["iso_3166_1"] == "US":
                        rating = rating_entry.get("rating", "TV Unrated")
                        if rating == "NR":
                            rating = "TV NR"
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
                    default_filename = replace_for_default_filename(tv_show, release_date, name, episode, season)
                    filename_entry.insert(0, default_filename)
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
                genre = convert_tmdb_to_apple_genres([g["name"] for g in data.get("genres", [])])
                release_date = data.get("release_date", "1900-01-01")
                description = data.get("overview", "No description available.")
                long_description = data.get("overview", "No long description available.")

                # **Get movie rating (US region)**
                rating = "Movie Unrated"
                for country in rating_data.get("results", []):
                    if country["iso_3166_1"] == "US":
                        for release in country.get("release_dates", []):
                            rating = release.get("certification", "Movie Unrated")
                            if rating:  # Stop at first found rating
                                if rating == "NR":
                                    rating = "Movie NR"
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
                    default_filename = replace_for_default_filename(name, release_date)
                    filename_entry.insert(0, default_filename)
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

            certification_ratings = {
                # US TV Ratings
                "TV-Y":     "us-tv|TV-Y|100",
                "TV-Y7":    "us-tv|TV-Y7|200",
                "TV-G":     "us-tv|TV-G|300",
                "TV-PG":    "us-tv|TV-PG|400",
                "TV-14":    "us-tv|TV-14|500",
                "TV-MA":    "us-tv|TV-MA|600",
                "TV NR":    "us-tv|Unrated|???",
                "TV Unrated": "us-tv|Unrated|???",

                # US Movie Ratings (MPA formerly MPAA)
                "G":        "mpaa|G|100",
                "PG":       "mpaa|PG|200",
                "PG-13":    "mpaa|PG-13|300",
                "R":        "mpaa|R|400",
                "NC-17":    "mpaa|NC-17|500",
                "Movie NR":    "mpaa|NR|000|",
                "Movie Unrated": "mpaa|Unrated|???"
            }

            if tv_var.get():
                metadata = {
                    "Name": name,
                    "Genre": genre,
                    "Release Date": release_date,
                    "TV Network": tv_network,
                    "Rating": certification_ratings[rating],
                    "TV Show": tv_show,
                    "TV Season": season,
                    "TV Episode #": episode,
                    "Description": description,
                    "Long Description": long_description,
                    "Series Description": series_description,
                    "Studio": studios,
                    "Cast": ", ".join(cast),
                    "Director": ", ".join(directors),
                    "Screenwriters": ", ".join(screenwriters),
                    "Media Kind": "10", # Set mediatype to tv show
                    "Sort Name": "S" + season + "E" + episode, # Set the sort name so that thumbnails show up correctly in Apple TV
                }
            else:
                # Metadata for movies
                metadata = {
                    "Name": name,
                    "Genre": genre,
                    "Release Date": release_date,
                    "Rating": certification_ratings[rating],
                    "Description": description,
                    "Long Description": long_description,
                    "Artist": ", ".join(directors),
                    "Studio": studios,
                    "Cast": ", ".join(cast),
                    "Director": ", ".join(directors),
                    "Producers": ", ".join(producers),
                    "Screenwriters": ", ".join(screenwriters),
                    "Media Kind": "9" # Set mediatype to movie
                }

            if unknown_media == None:
                metadata = {}



            retrieve_backdrops(tmdb_id, media_type, still_path)

        except Exception as e:
            tmdb_title_var.set("Error fetching data from TMDB")
            metadata = {}
            print(f"Error: {e}")

    debounce_timer = root.after(500, lambda: threading.Thread(target=retrieve_data, daemon=True).start())


def convert_tmdb_to_apple_genres(tmdb_genres):
    # Convert TMDB style genres to Apple TV style genres

    # base mapping for single genre conversions
    single_map = {
        "Action": "Action",
        "Adventure": "Adventure",
        "Animation": "Animation",
        "Comedy": "Comedy",
        "Documentary": "Documentary",
        "Drama": "Drama",
        "Family": "Kids & Family",
        "Fantasy": "Fantasy",
        "Science Fiction": "Sci-Fi",
        "History": "History",
        "Horror": "Horror",
        "Thriller": "Thriller",
        "Music": "Musical",
        "Mystery": "Mystery",
        "Romance": "Romance",
        "War": "War & Military",
        "Western": "Western"
    }

    # genres to remove entirely
    drop_genres = ["Crime", "TV Movie"]

    # multiple genre combination
    merged_genres = {
        "Action & Adventure": ["Action", "Adventure"],
        "Sci-Fi & Fantasy": ["Sci-Fi", "Fantasy"]
    }

    # genres that only exist in Apple TV and have no corresponding TMDB genre
    apple_tv_only_genres = ["Anime", "Biography", "Bollywood", "Classics", "Foreign", "Holiday", "Independent", "International", "Music Feature Films", "Nonfiction", "Reality", "Short Films", "Special Interest", "Sports", "Travel"]

    # remove dropped genres and convert simple ones
    new_genres = []
    for genre in tmdb_genres:
        if genre in drop_genres:
            # don't add it to the list
            continue
        if genre in single_map:
            new_genres.append(single_map[genre])


    # replace two similar genres with a single genre
    # example: "Action" and "Adventure" is replaced with "Action & Adventure"
    for genre in merged_genres:
        genre1 = merged_genres[genre][0]
        genre2 = merged_genres[genre][1]
        if genre1 in new_genres and genre2 in new_genres:
            index = new_genres.index(genre1)
            new_genres[index] = genre
            index = new_genres.index(genre2)
            new_genres[index] = genre


    # if list is empty, use a default genre "Independent"
    if not new_genres:
        new_genres.append(apple_tv_only_genres[6])

    # return the first genre in the list
    return new_genres[0]


def replace_for_default_filename(title, release_date, episode_name=None, episode=None, season=None):
    # replaces the default filename with the given parameters
    settings = check_and_create_settings()
    if episode_name and episode and season:
        default_filename = settings.get("default_tv_show_filename")
    else:
        default_filename = settings.get("default_movie_filename")

    year = release_date[:4]

    new_filename = re.sub(r'<title>', title, default_filename)
    new_filename = re.sub(r'<year>', year, new_filename)
    if episode_name and episode and season:
        new_filename = re.sub(r'<episode_name>', episode_name, new_filename)
        new_filename = re.sub(r'<episode_number>', episode, new_filename)
        new_filename = re.sub(r'<season_number>', season, new_filename)

    return new_filename

def download_thumbnail():
    """Downloads the thumbnail for the tmdb id based on the thumbnail_image_path_or_url"""
    global thumbnail_image_path_or_url
    print(thumbnail_image_path_or_url)

    if "http" not in thumbnail_image_path_or_url:
        print("thumbnail_image_path_or_url is not a url")
        if os.path.exists(thumbnail_image_path_or_url):
            print("thumbnail_image_path_or_url is already downloaded")
            return
        else:
            thumbnail_image_path_or_url = image_label.original_file_path_or_url or ""
            if "http" not in thumbnail_image_path_or_url and not os.path.exists(thumbnail_image_path_or_url):
                update_image(placeholder_image_path)
            download_thumbnail()
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

def retrieve_backdrops(tmdb_id, media_type, still_path):
    """
    Fetches English backdrops with a 16:9 ratio for a given movie or TV show,
    sorts by popularity, and downloads the first 10 to the hidden folder.
    Calls update_image(file_path) after downloading the first image.

    Args:
        tmdb_id (str): The TMDB ID of the media.
        media_type (str): "movie" or "tv".
        still_path (str): The url path of the still image.
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
    image_label.original_file_path_or_url = file_path_or_url
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

def get_subtitles():
    """Finds and downloads subtitles for a tmdb id. Downloads both non-foreign and foreign subtitles."""

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

    def clean_subtitles(input_file, output_file, foreign_only=False, remove=True):
        with open(input_file, "r", encoding="utf-8") as infile, open(output_file, "w", encoding="utf-8") as outfile:
            buffer = []
            an8_present = False

            for line in infile:
                if r"{\an8}" in line:
                    an8_present = True
                    line = line.replace(r"{\an8}", "")  # remove the tag

                if line.strip():
                    buffer.append(line)
                else:
                    if buffer:
                        if any("<font" in l for l in buffer):
                            buffer.clear()
                            an8_present = False
                            continue

                        # modify the timestamp line (second line)
                        if len(buffer) >= 2 and "-->" in buffer[1]:
                            ts_line = buffer[1].strip()

                            if an8_present:
                                ts_line += " X1:0"
                            if foreign_only:
                                ts_line += " !!!"

                            buffer[1] = ts_line + "\n"

                        outfile.writelines(buffer)
                        outfile.write("\n")

                        buffer.clear()
                        an8_present = False  # reset for next block

        if remove:
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

    def combine_srt(regular_path, forced_path, output_path):
        # regex to match srt timestamp lines
        timestamp_pattern = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})")

        def parse_srt(path, forced=False):
            """parse srt into list of (start_time, entry_text)"""
            with open(path, "r", encoding="utf-8-sig") as f:
                content = f.read().strip()
            blocks = content.split("\n\n")

            entries = []
            for block in blocks:
                lines = block.splitlines()
                if len(lines) < 2:
                    continue
                timestamp_line = lines[1]
                if not timestamp_pattern.match(timestamp_line):
                    continue

                # add !!! for forced subtitles
                if forced:
                    timestamp_line += " !!!"

                # store for sorting
                entries.append((timestamp_line.split(" --> ")[0], "\n".join(lines[1:])))
            return entries

        # parse both files
        regular_entries = parse_srt(regular_path, forced=False)
        forced_entries = parse_srt(forced_path, forced=True)

        # merge & sort by start time
        all_entries = regular_entries + forced_entries
        all_entries.sort(key=lambda e: e[0])  # sort by start time

        # rebuild new srt with renumbered indices
        output_lines = []
        for i, (_, entry_text) in enumerate(all_entries, start=1):
            output_lines.append(str(i))
            output_lines.append(entry_text)
            output_lines.append("")  # blank line separator

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines).strip())

        print(f"Combined SRT written to {output_path}")


    best_subtitles = get_best_subtitles(response.json())

    download_url = url_entry.get().strip()
    hash = hash_url(download_url)
    temp_sub_path = hidden_folder + "/" + hash + "_temp_sub.srt"
    temp_foreign_sub_path = hidden_folder + "/" + hash + "_temp_sub_foreign.srt"
    sub_path = hidden_folder + "/" + hash + "_sub.srt"
    sub_foreign_path = hidden_folder + "/" + hash + "_sub_foreign.srt"
    combined_subs_path = hidden_folder + "/" + hash + "_sub_combined.srt"

    try:

        global regular_subtitle_path
        global foreign_subtitle_path

        if regular_subtitle_path != "Download" and foreign_subtitle_path != "Download":
            print("not downloading subtitles")
            clean_subtitles(regular_subtitle_path, sub_path, remove=False)
            clean_subtitles(foreign_subtitle_path, sub_foreign_path, foreign_only=True, remove=False)
            return_dict = {"subtitles": sub_path, "foreign_subtitles": sub_foreign_path}

        elif not best_subtitles:
            if regular_subtitle_path != "Download":
                print("using regular subs from file")
                clean_subtitles(regular_subtitle_path, sub_path, remove=False)
                reg_subs = sub_path
            else:
                print("no regular subs")
                reg_subs = None
            if foreign_subtitle_path != "Download":
                print("using foreign subs from file")
                clean_subtitles(foreign_subtitle_path, sub_foreign_path, foreign_only=True, remove=False)
                fore_subs = sub_foreign_path
            else:
                print("no foreign subs")
                fore_subs = None

            #print("No subtitles available")
            return_dict = {"subtitles": reg_subs, "foreign_subtitles": fore_subs}

        elif len(best_subtitles) > 1:
            if regular_subtitle_path != "Download":
                print("using regular subs from file")
                clean_subtitles(regular_subtitle_path, sub_path, remove=False)
            else:
                print("downloading regular subtitles")
                sub = download_subtitles(best_subtitles[0]['attributes']['files'][0]['file_id'], temp_sub_path)
                clean_subtitles(sub, sub_path)

            if foreign_subtitle_path != "Download":
                print("using foreign subs from file")
                clean_subtitles(foreign_subtitle_path, sub_foreign_path, foreign_only=True, remove=False)
            else:
                print("downloading foreign subtitles")
                sub_foreign = download_subtitles(best_subtitles[1]['attributes']['files'][0]['file_id'], temp_foreign_sub_path)
                clean_subtitles(sub_foreign, sub_foreign_path, foreign_only=True)

            return_dict = {"subtitles": sub_path, "foreign_subtitles": sub_foreign_path}
        else:
            if regular_subtitle_path != "Download":
                print("using regular subs from file")
                clean_subtitles(regular_subtitle_path, sub_path, remove=False)
            else:
                print("downloading regular subs")
                sub = download_subtitles(best_subtitles[0]['attributes']['files'][0]['file_id'], temp_sub_path)
                clean_subtitles(sub, sub_path)

            if foreign_subtitle_path != "Download":
                print("using foreign subs from file")
                clean_subtitles(foreign_subtitle_path, sub_foreign_path, foreign_only=True, remove=False)
                fore_subs = sub_path
            else:
                print("no foreign subs")
                fore_subs = None

            return_dict = {"subtitles": sub_path, "foreign_subtitles": fore_subs}

        if combine_subs_var.get():
            regular_subs = return_dict['subtitles']
            foreign_subs = return_dict['foreign_subtitles']
            if regular_subs == None or foreign_subs == None:
                return return_dict
            else:
                combine_srt(regular_subs, foreign_subs, combined_subs_path)
                return {"subtitles": combined_subs_path, "foreign_subtitles": return_dict['foreign_subtitles']}
        else:
            return return_dict

    except:
        return {"subtitles": None, "foreign_subtitles": None}


# Functions to change or update settings

def check_and_create_settings():
    """Checks for the settings.json file. If it doesn't exist, it creates one with default settings."""
    settings_file = os.path.join(hidden_folder, "settings.json")

    # Default values for settings
    default_settings = {
        "download_folder": home_folder,
        "file_extension": ".mp4",
        "default_movie_filename": "<title> (<year>)",
        "default_tv_show_filename": "S<season_number>E<episode_number> - <title>",
        "request_headers": "{}"
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

        # Merge old settings an new settings
        updated = False
        for key, value in default_settings.items():
            if key not in settings:
                settings[key] = value
                updated = True

        # If new keys were added, save updated file
        if updated:
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=4)
            print("settings.json updated with new default keys.")

    download_folder = settings.get("download_folder")
    file_extension = settings.get("file_extension")

    print(f"Loaded settings: Download folder: {download_folder}, File extension: {file_extension}")

    # Apply the settings
    select_folder(download_folder)  # Update the folder
    selected_extension.set(file_extension)  # Update the file extension

    return settings

def update_settings(download_folder=None, file_extension=None, default_movie_filename=None, default_tv_show_filename=None, request_headers=None):
    """Updates the settings in the settings.json file, given the download folder path and the file extension of the video."""
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

    if default_movie_filename:
        settings["default_movie_filename"] = default_movie_filename

    if default_tv_show_filename:
        settings["default_tv_show_filename"] = default_tv_show_filename

    if request_headers != None:
        settings["request_headers"] = request_headers

    # Save updated settings back to the file
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=4)

    print(f"Settings updated: Download folder: {settings.get('download_folder')}, File extension: {settings.get('file_extension')}")


# Helpful miscellaneous functions

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
    subtitle_button.config(state=str)
    foreign_subtitle_button.config(state=str)
    clear_button.config(state=str)
    combine_subs_checkbox.config(state=str)
    default_filename_button.config(state=str)
    # Also close the default filename settings
    display_filename_settings(False)

def cleanup_old_files():
    """Deletes files older than 1 day in the hidden_folder to save space"""
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

def get_request_headers():
    # Gets the default request headers from the settings and converts them to a dict
    settings = check_and_create_settings()
    request_headers_string = settings.get("request_headers")
    try:
        headers_dict = eval(request_headers_string)
        print(headers_dict)
        return headers_dict
    except Exception as e:
        raise Exception("Error evaluating custom request headers.") from e



# Functions related to the actual download of the video

def start_download(startingText = "Starting Download..."):
    """Starts the download of the url using yt-dlp.
    Args: startingText (str), the text that is displayed while the download starts.
    """
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
    print("hashed_id")
    print(hashed_id)

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
            #original_file = d.get('filename')
            original_file = d['info_dict']['filename']
            root.after(0, update_ui, percent, file_size, eta, fragments)
            output_var.set("Download Finished!")

    def download_video():
        global download_process
        global original_file
        url = url_entry.get().strip()
        try:
            if url.startswith(("http://", "https://")):
                # Prepare yt-dlp options
                ydl_opts = {
                    'format': 'best/bestvideo+bestaudio',  # Download the best quality
                    'outtmpl': download_path,  # Path where the file will be saved
                    'progress_hooks': [lambda d: progress_hook(d)],  # Progress hook with stop_event
                    'quiet': False,  # Show output to the console
                    'skip_unavailable_fragments': False,  # Give an error if a fragment is unavailable
                    'ffmpeg_location': FFMPEG_PATH,  # Ensure ffmpeg is found
                    'http_headers': get_request_headers(),
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Start the download
                    download_process = ydl.download([url])

            else:
                # The url might be a filepath
                # remove surrounding quotes if they exist
                if (url.startswith(("'", '"')) and url.endswith(("'", '"'))):
                    url = url[1:-1]

                if os.path.exists(url):
                    # Copy the file from the url path to the hidden_folder with the name of the url hash
                    print("filepath exists")
                    print(url)

                    ext = os.path.splitext(url)[1]
                    new_filename = f"{hashed_id}{ext}"
                    destination = os.path.join(hidden_folder, new_filename)

                    # Copy file manually
                    # Copy using FFmpeg to get rid of unwanted streams
                    copy_command = [FFMPEG_PATH, "-i", url, "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", destination, "-y"]
                    copy_process = subprocess.Popen(
                        copy_command,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                    )

                    for line in copy_process.stderr:
                        if stop_event.is_set():
                            conpy_process.terminate()
                            break
                        root.after(0, process_output, line.strip())
                        #output_var.set(line.strip())

                    copy_process.wait()

                    if copy_process.returncode == 0:
                        # Success
                        print(f"File copied to {destination}")
                        original_file = destination
                    else:
                        #Error
                        raise Exception("Error scanning file")


                else:
                    raise Exception("Invalid URL or File Path")

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
                    #global original_file
                    ext = os.path.splitext(original_file)[1]
                    temp_file = f'{hidden_folder}/{hashed_id}_temp{file_extension}'
                    new_file = f'{hidden_folder}/{user_filename}{file_extension}'
                    final_destination = f'{download_folder}/{user_filename}{file_extension}'

                    # output_var.set("Downloading Subtitles...")
                    # foreign_subs_exist = False
                    # subtitle_paths = get_subtitles()
                    # subtitle_paths = {"subtitles": None, "foreign_subtitles": None}
                    # print(subtitle_paths)

                    global thumbnail_image_path_or_url
                    download_thumbnail()
                    if thumbnail_image_path_or_url != placeholder_image_path:
                        print("artwork is not default")
                        ffmpeg_command = [FFMPEG_PATH, '-i', original_file, '-i', thumbnail_image_path_or_url, '-map', '0', '-map', '1', '-c:v', 'copy', '-c:a', 'copy', '-disposition:v:1', 'attached_pic', '-metadata:s:a:0', 'language=eng', '-metadata:s:v:0', 'language=eng', '-movflags', 'faststart', temp_file, '-y']
                    else:
                        print("artowrk is default")
                        ffmpeg_command = [FFMPEG_PATH, '-i', original_file, '-c:v', 'copy', '-c:a', 'copy', '-metadata:s:a:0', 'language=eng', '-metadata:s:v:0', 'language=eng', '-movflags', 'faststart', temp_file, '-y']

                    output_var.set("Converting file to " + file_extension)
                    progress_bar["value"] = 20

                    # Conversion using FFmpeg (if needed)
                    conversion_process = subprocess.Popen(
                        ffmpeg_command,
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
                        progress_bar["value"] = 40

                        # Build the metadata string
                        global metadata
                        metadata_string = ""
                        for key, value in metadata.items():
                            metadata_string += '{' + key + ':' + value + '}'
                        # Add extra metadata
                        metadata_string += '{Encoding Tool:}'

                        # Check to see what resolution height of the video is
                        try:
                            streams = subprocess.run([SUBLERCLI_PATH, "-source", original_file, "-listtracks"], capture_output=True, text=True)
                            streams_list = streams.stdout.split("\n")
                            height = 0
                            for stream in streams_list:
                                parts = stream.split(", ")
                                if parts[1] != "Video Track":
                                    continue
                                else:
                                    res_parts = parts[-1].split()
                                    height = int(res_parts[-1])
                                    width = iny(res_parts[0])
                                    print(height)
                                    break

                            resolution_dict = {
                                0: {"width": 640, "height": 360},
                                1: {"width": 1280, "height": 720},
                                2: {"width": 1920, "height": 1080},
                                3: {"width": 3840, "height": 2160}
                            }

                            resolution_type = 0
                            for key in resolution_dict:
                                res = resolution_dict[key]
                                if width >= res["width"]:
                                    resolution_type = key

                            metadata_string += '{HD Video:' + str(resolution_type) + '}'

                        except Exception as e:
                            metadata_string += '{HD Video:0}'

                        # Start downloading the subtitles
                        output_var.set("Downloading Subtitles...")
                        progress_bar["value"] = 60
                        subtitle_paths = get_subtitles()
                        subs = subtitle_paths["subtitles"]
                        subs_foreign = subtitle_paths["foreign_subtitles"]

                        output_var.set("Adding Subtitles...")
                        progress_bar["value"] = 80
                        mp4box_command_start = [MP4BOX_PATH, temp_file]
                        foreign_subs_command = ["-add", f"{subs_foreign}:hdlr=sbtl:lang=eng:group=2:txtflags=0xC0000000"]
                        regular_subs_command = ["-add", f"{subs}:hdlr=sbtl:lang=eng:group=2:disabled"]
                        mp4box_command_end = ["-out", new_file]
                        if subs and subs_foreign:
                            # If both subs exist, add them both with mp4box (sublercli doesn't allow forced subtitles with 2 files)
                            mp4box_command = mp4box_command_start + foreign_subs_command + regular_subs_command + mp4box_command_end
                        elif subs:
                            mp4box_command = mp4box_command_start + regular_subs_command + mp4box_command_end
                        elif subs_foreign:
                            mp4box_command = mp4box_command_start + foreign_subs_command + mp4box_command_end
                        else:
                            mp4box_command = None

                        if mp4box_command:
                            mp4box_out = subprocess.run(mp4box_command, capture_output=True, text=True)
                            if mp4box_out.returncode != 0:
                                output_var.set("Error adding subtitles!")
                                output_label.config(fg="red")
                                raise Exception("Error adding subtitles!")
                                return
                        else:
                            # Rename the temp_file to new_file
                            os.rename(temp_file, new_file)


                        # Use sublercli to add the metadata that ffmpeg and mp4box cannot, and optimize and organizegroups
                        output_var.set("Adding metadata...")
                        progress_bar["value"] = 90
                        subler_command = [SUBLERCLI_PATH, "-dest", new_file, "-optimize", "-organizegroups", "-metadata", metadata_string]
                        subler_process = subprocess.Popen(
                            subler_command,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                        )

                        for line in subler_process.stdout:
                            if stop_event.is_set():
                                subler_process.terminate()
                                break
                            root.after(0, process_output, line.strip())

                        subler_process.wait()

                        if subler_process.returncode != 0:
                            output_var.set("Error adding metadata!")
                            output_label.config(fg="red")
                            raise Exception("Error adding metadata!")
                            return

                        # Download, conversion, and metadata processes complete
                        output_var.set("Metadata addition complete!")
                        progress_bar["value"] = 100
                        print("Metadata addition complete!")

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
                        print("Video saved successfully!")

                    else:
                        output_var.set("Error during conversion!")
                        output_label.config(fg="red")
                        raise Exception("Error during conversion!")

        except yt_dlp.utils.DownloadCancelled:
            submit_button.config(text="Resume Download", command=lambda: start_download("Resuming Download..."))
            discard_button.pack(side="left")
            output_var.set("")
            print("Download was canceled by the user")

        except Exception as e:
            submit_button.config(text="Try Again", command=lambda: start_download("Retrying..."))
            # Enable the inputs again
            disable_inputs(False)
            output_var.set("Error: " + str(e))
            output_label.config(fg="red")
            print(e)

    # Run download in a separate thread to avoid blocking the GUI
    download_thread = threading.Thread(target=download_video, daemon=True)
    download_thread.start()
    submit_button.config(text="Pause Download", fg="blue", command=stop_download)

def stop_download():
    """Stop the download process."""
    stop_event.set()

    if download_process:
        download_process.terminate()

    output_var.set("Pausing Download...")

    # Enable the url input again
    url_entry.config(state="normal")

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
    """Actually update the ui based on the input"""
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
    elif "Optimizing..." in line:
        # This is output from sublercli
        output_var.set("Optimizing...")

    output_label.config(fg="systemTextColor")



"""Start building the ui of the app"""

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

# Ensure widgets are hidden but still taking up space in layout
def toggle_season_episode():
    """Displays or hides the season and episode entry boxes"""
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

def select_subtitle():
    global regular_subtitle_path
    file_path = filedialog.askopenfilename(
        title="Select subtitle file",
        filetypes=[("Subtitle files", "*.srt")]  # only show .srt
    )
    if file_path:
        regular_subtitle_path = file_path
        subtitle_regular_var.set(regular_subtitle_path)

def select_foreign_subtitle():
    global foreign_subtitle_path
    file_path = filedialog.askopenfilename(
        title="Select subtitle file",
        filetypes=[("Subtitle files", "*.srt")]  # only show .srt
    )
    if file_path:
        foreign_subtitle_path = file_path
        subtitle_foreign_var.set(foreign_subtitle_path)

def clear_subtitle_paths():
    global regular_subtitle_path
    global foreign_subtitle_path
    regular_subtitle_path = "Download"
    foreign_subtitle_path = "Download"
    subtitle_regular_var.set(regular_subtitle_path)
    subtitle_foreign_var.set(foreign_subtitle_path)

# Subtitle selection frame
subtitle_selection_frame = tk.Frame(root)
subtitle_selection_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
subtitle_label = tk.Label(subtitle_selection_frame, text="Subtitles: ")
subtitle_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)
clear_button = tk.Button(subtitle_selection_frame, text="Clear", command=clear_subtitle_paths)
clear_button.grid(row=0, column=1, sticky="w", padx=5, pady=1)
combine_subs_var = tk.IntVar()  # variable to hold checkbox state (0 or 1)
combine_subs_checkbox = tk.Checkbutton(subtitle_selection_frame, text="Combine Subtitles", variable=combine_subs_var)
combine_subs_checkbox.grid(row=0, column=2, columnspan=2, sticky="w", padx=5, pady=1)
regular_subtitle_path = "Download"
foreign_subtitle_path = "Download"
subtitle_regular_var = tk.StringVar(value=f"{regular_subtitle_path}")
subtitle_foreign_var = tk.StringVar(value=f"{foreign_subtitle_path}")
subtitle_button = tk.Button(subtitle_selection_frame, text="Regular Subtitle Source", command=select_subtitle)
subtitle_button.grid(row=1, column=1, columnspan=2, sticky="w", padx=5, pady=1)
subtitle_label = tk.Label(subtitle_selection_frame, textvariable=subtitle_regular_var)
subtitle_label.grid(row=1, column=3, sticky="w", padx=5, pady=1)
foreign_subtitle_button = tk.Button(subtitle_selection_frame, text="Foreign Subtitle Source", command=select_foreign_subtitle)
foreign_subtitle_button.grid(row=2, column=1, columnspan=2, sticky="w", padx=5, pady=1)
foreign_subtitle_label = tk.Label(subtitle_selection_frame, textvariable=subtitle_foreign_var)
foreign_subtitle_label.grid(row=2, column=3, sticky="w", padx=5, pady=1)

# make a horizontal break
# break_label = tk.Label(root, bg="#999999", text="", height=0)
# break_label.grid(row=4, column=0, sticky="nsew", columnspan=2, padx=5, pady=5)
line = tk.Frame(root, height=2, bg="#999999", bd=0)
line.grid(row=4, column=0, columnspan=2, sticky="we", padx=10, pady=5)



# Folder Selection Frame
folder_frame = tk.Frame(root)
folder_frame.grid(row=5, column=0, columnspan=2, sticky="w", padx=5, pady=5)

folder_var = tk.StringVar(value=f"Save To: {download_folder}")
folder_button = tk.Button(folder_frame, text="Select Destination Folder", command=select_folder)
folder_button.pack(side="left", padx=5)
folder_label = tk.Label(folder_frame, textvariable=folder_var)
folder_label.pack(side="left")

# File name entry (on the same line)
filename_frame = tk.Frame(root)
filename_frame.grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=5)

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
    """Changes the default settings to convert the video file as the specified format"""
    selected = selected_extension.get()
    print(selected)
    update_settings(file_extension=selected)

# Bind the selection event to the dropdown
selected_extension.trace("w", on_extension_select)

filename_settings_frame = None
# Function to display the filename settings tab
def display_filename_settings(bool=True):
    global filename_settings_frame
    print("filename settings button pushed")
    if filename_settings_frame == None and bool == True:
        filename_settings_frame = tk.Frame(root, bg="#999999")
        filename_settings_frame.grid(row=7, column=0, columnspan=2, sticky="ew", padx=10, pady=5)

        settings = check_and_create_settings()

        default_movie_name_label = tk.Label(filename_settings_frame, text="Default TV Show Filename:", bg="#999999")
        default_movie_name_label.grid(row=0, column=0, padx=(5, 5), pady=10)
        default_movie_name_entry = tk.Entry(filename_settings_frame, width=40)
        default_movie_name_entry.grid(row=0, column=1, padx=(3, 0), pady=10)
        default_movie_name_entry.insert(0, settings.get("default_movie_filename"))

        default_tv_show_name_label = tk.Label(filename_settings_frame, text="Default Movie Filename:", bg="#999999")
        default_tv_show_name_label.grid(row=1, column=0, padx=(0, 10), pady=10)
        default_tv_show_name_entry = tk.Entry(filename_settings_frame, width=40)
        default_tv_show_name_entry.grid(row=1, column=1, padx=(3, 0), pady=10)
        default_tv_show_name_entry.insert(0, settings.get("default_tv_show_filename"))

        available_tags_label = tk.Label(filename_settings_frame, text="Available Tags:    <title> <year> <episode_name> <episode_number> <season_number>", bg="#999999")
        available_tags_label.grid(row=2, column=0, padx=(5, 0), pady=10, columnspan=2)

        default_request_headers_label = tk.Label(filename_settings_frame, text="Default Request Headers:", bg="#999999")
        default_request_headers_label.grid(row=3, column=0, padx=(5, 5), pady=10)
        default_request_headers_entry = tk.Entry(filename_settings_frame, width=40)
        default_request_headers_entry.grid(row=3, column=1, padx=(3, 0), pady=10)
        default_request_headers_entry.insert(0, settings.get("request_headers"))

        default_filename_button.config(text="Save Settings")

    else:
        # The frame might exist, so delete it and save the settings
        if filename_settings_frame == None:
            return

        # Get the entries from the frame
        entries = [child for child in filename_settings_frame.winfo_children() if isinstance(child, tk.Entry)]
        default_movie_name_entry = entries[0]
        default_tv_show_name_entry = entries[1]
        default_request_headers_entry = entries[2]
        default_movie_filename = default_movie_name_entry.get()
        default_tv_show_filename = default_tv_show_name_entry.get()
        default_request_headers = default_request_headers_entry.get()

        filename_settings_frame.grid_forget()
        filename_settings_frame = None

        update_settings(default_movie_filename=default_movie_filename, default_tv_show_filename=default_tv_show_filename, request_headers=default_request_headers)

        default_filename_button.config(text="Filename Settings")

        retrieve_tmdb_data()

# Create the filename settings button
default_filename_button = tk.Button(filename_frame, text="Filename Settings", command=display_filename_settings)
default_filename_button.pack(side="left", padx=(100, 0))


# Submit and Discard buttons (side by side)
button_frame = tk.Frame(root)
button_frame.grid(row=8, column=0, columnspan=2, pady=10, padx=10, sticky="w")

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
progress_bar.grid(row=9, column=0, pady=0, padx=10, sticky="w")

progress_frame = tk.Frame(root)
progress_frame.grid(row=10, column=0, sticky="w", padx=5, pady=2)

# Progress information labels
progress_label = tk.Label(progress_frame, text="Downloading:")
progress_label.grid(row=10, column=0, sticky="w", padx=10, pady=2)

fragment_label = tk.Label(progress_frame, text="Fragments:")
fragment_label.grid(row=11, column=0, sticky="w", padx=10, pady=2)

eta_label = tk.Label(progress_frame, text="ETA:")
eta_label.grid(row=12, column=0, sticky="w", padx=10, pady=2)

size_label = tk.Label(progress_frame, text="Estimated File Size:")
size_label.grid(row=13, column=0, sticky="w", padx=10, pady=2)

# Progress information values (separate column for alignment)
progress_var = tk.StringVar()
progress_value = tk.Label(progress_frame, textvariable=progress_var)
progress_value.grid(row=10, column=1, sticky="w", padx=5, pady=2)

fragment_var = tk.StringVar()
fragment_value = tk.Label(progress_frame, textvariable=fragment_var)
fragment_value.grid(row=11, column=1, sticky="w", padx=5, pady=2)

eta_var = tk.StringVar()
eta_value = tk.Label(progress_frame, textvariable=eta_var)
eta_value.grid(row=12, column=1, sticky="w", padx=5, pady=2)

size_var = tk.StringVar()
size_value = tk.Label(progress_frame, textvariable=size_var)
size_value.grid(row=13, column=1, sticky="w", padx=5, pady=2)

tmdb_image_frame = tk.Frame(root, bg="#999999")
tmdb_image_frame.grid(row=10, column=1, sticky="e", padx=5, pady=2)

# Thumbnail image in the bottom corner
image_label = tk.Label(tmdb_image_frame, text="No Thumbnail", width=192, height=108)
image_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)
# Bind left-click to change image
image_label.bind("<Button-1>", lambda event: toggle_image_selection())


# Frame for scrollable images at the bottom
scrollable_frame = tk.Frame(root)
scrollable_frame.grid(row=14, column=0, sticky="ew", padx=5, pady=5, columnspan=2)

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
    """
    global backdrop_list
    global last_load_id
    print(backdrop_list)

    current_tmdb_id = tmdb_id_entry.get().strip() + str(tv_var.get())

    if show is True:
        # Always show the frame
        scrollable_frame.grid(row=14, column=0, sticky="ew", padx=5, pady=5, columnspan=2)
    elif show is False:
        # Always hide the frame
        scrollable_frame.grid_forget()
    else:
        # Toggle visibility if show is None
        if scrollable_frame.winfo_ismapped():
            scrollable_frame.grid_forget()  # Hide the frame
        else:
            scrollable_frame.grid(row=14, column=0, sticky="ew", padx=5, pady=5, columnspan=2)  # Show the frame


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
update_image(placeholder_image_path)

# Call the toggle function after initializing
toggle_season_episode()

# Load the settings
check_and_create_settings()

# Clean up old files
cleanup_old_files()


root.createcommand("::tk::mac::LaunchURL", parse_arguments)


# After initialization, start the queue checking
root.after(100, update_ui_from_queue)

# Parse the arguments passed to the script
root.after(100, parse_arguments)

# Start the GUI
root.mainloop()
