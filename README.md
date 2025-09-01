# StreamFetchTagger

<img align="left" height="65vw" src="resources/StreamFetchTagger_icon_cropped.png">

A MacOS app built with Python that allows you to automatically download and tag media. StreamFetchTagger is built with Python and utilizes yt-dlp, ffmpeg, SublerCLI, MP4Box, as well as several Python modules and packages.

</br>

> [!NOTE]  
> This currently has only been tested using a M1 MacBook Air, but it should work on other arm based MacOS machines as well. Small modifications may be made for this Python code to run on other machines as well.

> [!IMPORTANT]  
> Your computer may say that the app cannot be run because it is not from a trusted developer. In order to bypass this, you will need to go into `System Settings > Privacy & Security > StreamFetchTagger`, and click `Open Anyway`.
## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Images](#images)
- [Limitations](#limitations)
- [License](#license)
- [Disclaimer](#disclaimer)

## Features

- Downloads media from anywhere that yt-dlp can download from
- Automatically tags the downloaded media with metadata from TMDB
- Automatically downloads subtitles from opensubtitles.com for TMDB tagged media
- Accepts command line arguments and parameters via the `StreamFetchTagger://` url scheme

## Installation

There are three different ways that you can install this project:  
1. [Method 1:](#method-1) Download the .app file (simple. runs slower than other methods)
2. [Method 2:](#method-2) Download the .app file and supporting directories (simple. runs normal speed)
3. [Method 3:](#method-3) Download all files in this repository and run with Python (more difficult. runs normal speed)  

Deciding which method for you is important. I would recommend option 2 for most people as it is still simple and it starts up at a regular speed. Option 1 is the second best choice as it is the simplest, but it starts up slower than the other options. Option 3 is not recommended for most users because it is more for advanced users who know how to code.

### Method 1

This method is simple to setup, but it runs a little slower than the other methods.  
First head over to the [Releases Page](../../releases/latest) and download the `SFT_application.zip` file.  
Then you can simply extract it and place the app wherever you want on your machine to run it.

### Method 2

This method is simple to setup, and it runs at normal speed, so it is the recommended option.  
First head over to the [Releases Page](../../releases/latest) and download the `SFT_directory.zip` file.  
Then you can simply extract it and place the StreamFetchTagger folder anywhere you want to run it on your machine.  
To run the app, just open the folder and double click on the app like any other application.  

### Method 3

This method is for advanced users and requires Python to be installed, as well as all of the imported packages and modules at the beginning of the `StreamFetchTagger.py` file. After Python and all other modules/packages have been installed, download this repository and run the `StreamFetchTagger.py` file with `python3 StreamFetchTagger.py`.  
To compile this code into an app yourself, you will need PyInstaller installed on your computer, then run this command:  
```sh
pyinstaller --onefile --windowed --name "StreamFetchTagger" \
  --add-binary "binaries/ffmpeg:./binaries" \
  --add-binary "binaries/SublerCLI:./binaries" \
  --add-binary "binaries/MP4Box:./binaries" \
  --add-data "resources/placeholder.png:./resources" \
  --icon="resources/icon.icns" \
  StreamFetchTagger.py
```
or run this command to compile it in one directory:  
```sh
pyinstaller --onedir --windowed --name "StreamFetchTagger" \
  --add-binary "binaries/ffmpeg:./binaries" \
  --add-binary "binaries/SublerCLI:./binaries" \
  --add-binary "binaries/MP4Box:./binaries" \
  --add-data "resources/placeholder.png:./resources" \
  --icon="resources/icon.icns" \
  StreamFetchTagger.py
```

## Usage

When opening the app for the first time, your computer may say that the app cannot be run because it is not from a trusted developer. In order to bypass this, you will need to go into `System Settings > Privacy & Security > StreamFetchTagger`, and click `Open Anyway`.  

The app opens a simple GUI which allows the user to input the url that they want downloaded, as well as options to input the TMDB id and season and episode numbers to automatically tag the downloaded video.  
There are also options to change the download location, file type, file name, and the thumbnail artwork.  
The user can then click on the download button and wait for the download to finish.  

After the application has been opened once, it will then accept parameters via the custom url scheme. These parameters should be specified in the order: tmdb_id, season_num, episode_num, download_url.  
For example:  
Movie: `StreamFetchTagger://params?tmdb=1726&url=https://www.youtube.com/watch?v=dQw4w9WgXcQ`  
TV Show: `StreamFetchTagger://params?tmdb=1877&s=1&e=3&url=https://www.youtube.com/watch?v=dQw4w9WgXcQ`  
URL Only: `StreamFetchTagger://params?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ`  
Only Launch App: `StreamFetchTagger://`  

## Images

<p align="left">
  <img src="https://i.imgur.com/qDID9GJ.png" width="400vw" />
  <strong>Downloading a movie</strong>
  <br>
  <br>
  <img src="https://i.imgur.com/6tDaVt3.png" width="400vw" />
  <strong>Downloading a tv show while choosing the thumbnail</strong>
</p>

## Limitations

The only limitation I am aware of so far is the fact that only one window can be opened at a time.  
I will try to implement multiple windows for downloading more than one video at a time soon.  

## License

This project is licensed under the MIT License - meaning that you are free to use, distribute, and edit this project however you see fit!  
See the [LICENSE](./LICENSE) file for more details.

## Disclaimer

I do not condone or encourage the unauthorized downloading of copyrighted materials. Any such activity is the sole responsibility of the user.  

I do not claim ownership of or authorship for yt-dlp, ffmpeg, SublerCLI, MP4Box, or any other Python modules and packages used in this project. I extend my gratitude to the developers of these projects for providing the tools that made this project possible.  
