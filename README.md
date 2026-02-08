# iTunes-navidrome-migration
Python scripts to transfer iTunes history & playlists to a new Navidrome installation

## Introduction
This Python script will transfer song ratings, play counts, play dates, added dates and playlists from an existing iTunes library to a new Navidrome installation. This is a modified script created by Stampede (https://github.com/Stampede/itunes-navidrome-migration), with the playlists being migrated using SQLite scripts instead of Navidrome API.

## Background
iTunes saves its data in a Library.xml file. Navidrome saves its data in up to three different `navidrome.db*` files. The script reads from `Library.xml` and writes the data to the navidrome.db file.

This script was tested on Navidrome v0.59.

## Installation
1. You can create a Python virtual environment, or not.
2. Download `iTunestoND.py` and `requirements.txt` and save to a folder.
3. `$ pip3 install -r requirements.txt`

## How to use

### Preparing your library
Set up your Navidrome server and copy all the folders and music files from your iTunes library to the Navidrome library. Navidrome will build its own database from scratch based on the file metadata. 

The most important thing is that you keep the same directory structure between iTunes and Navidrome libraries. Do not rename, delete or move any files or directories. The script uses the file paths to sync the databases. If you want to reorganize the file structure, do it after you have moved over all your iTunes data.

That said, before running the scripts, I found it very helpful to use Music Brainz Picard to clean up file metadata **without moving any files**. Use Navidrome for a week or so and if you have problems finding albums or songs, use Picard or Beets or something to improve the metadata tags for the files that are acting funny.

**Only work on backups until you know the scripts were successful.**

### Migrating play counts, last played date and song ratings
1. Shut down your Navidrome server.
2. Copy the Navidrome database files to the machine with these scripts. In my case there are 3 database files: `navidrome.db`, `navidrome.db-shm` and `navidrome.db-wal` you need any `navidrome.db*` file that you find.
3. Run the first script: `$python3 iTunestoND.py <navidrome_db_path> <iTunes_db_path>`
4. Wait. For large libraries, it can take a few minutes to crunch all the data in `Library.xml`.
5. When it's done, your Navidrome database files may be collapsed into a single `navidrome.db` file. This is OK.
6. **On the machine with the ND server:** delete the 3 database files, then copy over the `navidrome.db` file from the script. Put it in their place.
7. Start your Navidrome server to make sure everything worked correctly. You should now have song rating, play counts and playlists.

