#!/usr/bin/env python

import sys, sqlite3, datetime, re, string, random
from pathlib import Path
from urllib.parse import unquote
from bs4 import BeautifulSoup
import unicodedata
import demoji

def determine_userID(nd_p):
    conn = sqlite3.connect(nd_p)
    cur = conn.cursor()
    cur.execute('SELECT id, user_name FROM user')
    users = cur.fetchall()
    if len(users) == 1:
        print(f'Changes will be applied to the {users[0][1]} Navidrome account.')
    else:
        raise Exception('There needs to be exactly one user account set up with Navidrome. You either have 0, or more than 1 user account.')
    conn.close()
    return users[0][0]

def update_playstats(d1, id, playcount, playdate, rating=0, starred=0):
    d1.setdefault(id, {})
    d1[id].setdefault('play count', 0)
    d1[id].setdefault('play date', datetime.datetime.fromordinal(1))
    d1[id]['play count'] += playcount
    d1[id]['rating'] = rating
    d1[id]['starred'] = starred

    if playdate > d1[id]['play date']: d1[id].update({'play date': playdate})

def write_to_annotation(userID, dictionary_with_stats, item_type):
    annotation_entries = []
    for item_id in dictionary_with_stats:
        this_entry = dictionary_with_stats[item_id]
        
        play_count = this_entry['play count']
        play_date = this_entry['play date'].strftime('%Y-%m-%d %H:%M:%S') # YYYY-MM-DD 24:mm:ss
        rating = this_entry['rating']
        starred = this_entry['starred']

        annotation_entries.append((userID, item_id, item_type, play_count, play_date, rating, starred, None, None))

    conn = sqlite3.connect(nddb_path)
    cur = conn.cursor()
    cur.executemany('INSERT INTO annotation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', annotation_entries)
    conn.commit()
    conn.close()

def update_dates(d1, id, date_added, date_modified):
    d1.setdefault(id, {})
    d1[id].setdefault('created at', datetime.datetime.fromordinal(1))
    d1[id].setdefault('updated at', datetime.datetime.fromordinal(1))

    if date_added > d1[id]['created at']: 
        d1[id].update({'created at': date_added})
    if date_modified > d1[id]['updated at']: 
        d1[id].update({'updated at': date_modified})

def write_dates(dictionary_with_dates, entry_type):
    conn = sqlite3.connect(nddb_path)
    cur = conn.cursor()

    for item_id in dictionary_with_dates:
        this_entry = dictionary_with_dates[item_id]
        
        created_at = this_entry['created at'].strftime('%Y-%m-%d %H:%M:%S') # YYYY-MM-DD 24:mm:ss
        updated_at = this_entry['updated at'].strftime('%Y-%m-%d %H:%M:%S') # YYYY-MM-DD 24:mm:ss
        if entry_type == 'album':
            cur.execute('''UPDATE album SET created_at = ?, updated_at = ? WHERE id = ?''', (created_at, updated_at, item_id))
        if entry_type == 'media_file':
            cur.execute('''UPDATE media_file SET created_at = ?, updated_at = ? WHERE id = ?''', (created_at, updated_at, item_id))
    conn.commit()
    conn.close()

def insert_playlist(playlist_name, user_id):
    conn = sqlite3.connect(nddb_path)
    cur = conn.cursor()
    cur.execute('''SELECT id FROM playlist WHERE name = ?''', (playlist_name,))
    try:
        playlist_id, = cur.fetchone()
    except TypeError:
        playlist_id = None

    if playlist_id is None:
        # navidrome playlist id is 22 character long and doesn't contain '-'
        playlist_id = ''.join(random.choices(string.ascii_letters + string.digits, k=22))
        cur.execute('''INSERT INTO playlist (id,name,owner_id,created_at,updated_at) VALUES (?, ?, ?, ?, ?)''', (playlist_id, playlist_name, user_id, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()

    conn.close()
    return playlist_id 

def insert_playlist_track(id, playlist_id, track_id):
    conn = sqlite3.connect(nddb_path)
    cur = conn.cursor()
    cur.execute('''INSERT OR IGNORE INTO playlist_tracks (id, playlist_id, media_file_id) VALUES (?, ?, ?)''', (id, playlist_id, track_id))
    conn.commit()
    conn.close()

def main():
    if len(sys.argv) != 3:
        print("Usage: python itunes-nd.py <navidrome_db_path> <iTunes_db_path>")
        sys.exit(1)
    
    global nddb_path, itdb_path
    nddb_path = Path(sys.argv[1])
    itdb_path = Path(sys.argv[2])
    
    if not nddb_path.is_file():
        print(f"Error: Navidrome database file '{nddb_path}' not found.")
        sys.exit(1)
    
    if not itdb_path.is_file():
        print(f"Error: iTunes database file '{itdb_path}' not found.")
        sys.exit(1)

    with open(itdb_path, 'r', encoding="utf-8") as f: 
        soup = BeautifulSoup(f, 'lxml-xml')

    it_root_music_path = unquote(soup.find('key', text='Music Folder').next_sibling.text, encoding='utf-8')
    # example output of previous line: 'file://localhost/C:/Users/REDACTED/Music/iTunes/iTunes Music/'

    songs = soup.dict.dict.find_all('dict') # yields result set of media files to loop through
    playlists = soup.array.find_all('dict', recursive=False)

    song_count = len(songs)
    print(f'Found {song_count:,} files in iTunes database to process.')
    del(soup)

    userID = determine_userID(nddb_path)
    songID_correlation = {} # we'll save this for later use to transfer iTunes playlists to ND (another script)
    artists = {}            # artists and albums will keep count of plays and play dates for each
    albums = {}
    files = {}

    status_interval = song_count // 8
    counter = 0

    conn = sqlite3.connect(nddb_path)
    cur = conn.cursor()
    cur.execute('DELETE FROM annotation')
    conn.commit()

    for it_song_entry in songs:
        counter += 1    # progress tracking feedback
        if counter % status_interval == 0:
            print(f'{counter:,} files parsed so far of {song_count:,} total songs.')

        # chop off first part of IT path so we can correlate it to the entry in the ND database
        
        if it_song_entry.find('key', string='Location') == None: 
            continue

        song_path = unquote(it_song_entry.find('key', string='Location').next_sibling.text, encoding='utf-8')
        if not song_path.startswith(it_root_music_path):  # excludes non-local content
            continue   

        song_path = re.sub(it_root_music_path, '', song_path)

        try:
            cur.execute('SELECT id, artist_id, album_id FROM media_file WHERE path LIKE "%' + song_path + '"')
            song_id, artist_id, album_id = cur.fetchone()
        except TypeError:
            # the file path might use different unicode normalization than the database
            # there seems to not be a single one that works for all files, so we'll try
            # all of them until we find one that works
            found = False
            for x in ['NFC', 'NFD', 'NFKC', 'NFKD']:
                try:
                    song_path = unicodedata.normalize(x, song_path)
                except UnicodeDecodeError:
                    continue
                try:
                    cur.execute('SELECT id, artist_id, album_id FROM media_file WHERE path LIKE "%' + song_path + '"')
                    song_id, artist_id, album_id = cur.fetchone()
                    found = True
                    break
                except TypeError:
                    continue

            if not found:
                # try removing emojis from the path
                song_path_no_emoji = demoji.replace(song_path, '????') # according to some sources, emojis are replaced with 4 question marks in Navidrome DB
                try:
                    cur.execute('SELECT id, artist_id, album_id FROM media_file WHERE path LIKE "%' + song_path_no_emoji + '"')
                    song_id, artist_id, album_id = cur.fetchone()
                    found = True
                except TypeError:
                    continue

            if not found:
                print(f"Error while parsing {song_path}. Cannot find the matching entry in Navidrome database. SQL query: ")
                print('SELECT id, artist_id, album_id FROM media_file WHERE path LIKE "%' + song_path + '"')
                continue

        # correlate iTunes ID with Navidrome ID (for use in a future script)
        it_song_ID = int(it_song_entry.find('key', string='Track ID').next_sibling.text)
        songID_correlation.update({it_song_ID: song_id})
        
        try:    # get rating, play count & date from iTunes
            song_rating = int(it_song_entry.find('key', string='Rating').next_sibling.text)
            song_rating = int(song_rating / 20)
        except AttributeError: 
            song_rating = 0 # rating = 0 (unrated) if it's not rated in iTunes
            
        try:
            play_count = int(it_song_entry.find('key', string='Play Count').next_sibling.text)
            last_played = it_song_entry.find('key', string='Play Date UTC').next_sibling.text[:-1] # slice off the trailing 'Z'
            last_played = datetime.datetime.strptime(last_played, '%Y-%m-%dT%H:%M:%S') # convert from string to datetime object. Example string: '2020-01-19T02:24:14Z'
            date_added = it_song_entry.find('key', string='Date Added').next_sibling.text[:-1]
            date_added = datetime.datetime.strptime(date_added, '%Y-%m-%dT%H:%M:%S')
            date_modified = it_song_entry.find('key', string='Date Modified').next_sibling.text[:-1]
            date_modified = datetime.datetime.strptime(date_modified, '%Y-%m-%dT%H:%M:%S')
        except AttributeError: 
            continue

        update_playstats(artists, artist_id, play_count, last_played)
        update_playstats(albums, album_id, play_count, last_played)
        update_playstats(files, song_id, play_count, last_played, rating=song_rating)
        update_dates(albums, album_id, date_added, date_modified)
        update_dates(files, song_id, date_added, date_modified)  

    playlists_to_skip = ('Library', 'Downloaded', 'Music', 'Movies', 'TV Shows', 'Podcasts', 'Audiobooks', 'Tagged', 'Genius')
    for plist in playlists:
        if plist.find('key', text='Distinguished Kind'): 
            continue # these are special playlists unique to iTunes
        if plist.find('key', text='Visible'):
            if plist.find('key', text='Visible').find_next('True') == None: 
                continue # skip invisible playlists - like Library
        
        playlist_name = plist.find('key', text='Name').find_next('string').text
        if playlist_name in playlists_to_skip: 
            continue
        if plist.find('key', text='Smart Info'): 
            continue
        
        try:
            playlist_tracks = plist.array.find_all('dict')
        except AttributeError:
            continue

        playlist_id = insert_playlist(playlist_name, userID)

        playlist_track_no = 0;
        for track in playlist_tracks:
            playlist_track_no += 1
            try:
                nd_track_id = songID_correlation[int(track.integer.text)]
                insert_playlist_track(playlist_track_no, playlist_id, nd_track_id)
            except KeyError:
                print(f"Error while parsing playlist {playlist_name}. Cannot find the matching entry in Navidrome database for iTunes track ID {track.integer.text}. Playlist track number in iTunes playlist: {playlist_track_no}. ")
                continue
    
    conn.close()

    write_to_annotation(userID, artists, 'artist')
    write_to_annotation(userID, files, 'media_file')
    write_to_annotation(userID, albums, 'album')
    write_dates(files, 'media_file')
    write_dates(albums, 'album')

if __name__ == "__main__":
    main()