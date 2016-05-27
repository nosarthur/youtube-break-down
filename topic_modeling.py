
from __future__ import division
from nltk.stem.porter import PorterStemmer 
from nltk.tokenize import RegexpTokenizer
tokenizer = RegexpTokenizer(r'\w+')
porter = PorterStemmer()

from nltk.corpus import stopwords
stop = set(stopwords.words('english'))

from collections import Counter
import json
import re
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import os.path
from apiclient.discovery import build
from functools import partial
import tempfile
import pickle
import datetime
import rfc3339      # for date object -> date string
import iso8601      # for date string -> date object

import sqlite3
SQLKEYS = ['videoId','publishedAt','channelTitle','title']

from gensim import corpora
import gensim


def analyze_videos(channel, wordcloud=False, LDA=False):
    videos = load_channel(channel['title'])
    channel['v_num'] = len(videos)
    channel['topic_num'] = max(channel['v_num']//50 , 4)

    # get last video in this channel 
    last_video = get_last_video(channel['title'])
    channel['latest'] = last_video['publishedAt']

    # make word cloud
    global stop
    if channel.get('stopwords'):
        extra_w = [x.lower() for x in channel['stopwords'].split()]
        stopw = stop.union(extra_w)
    else:
        stopw = stop
    new_tokenizer = partial(tokenize_text, stopw)
    titles = [new_tokenizer(v['title']) for v in videos]
    channel['wordcloud'] = ''.join(('images/',
                                    channel['title'],
                                    '.png'))
    if wordcloud:
        make_wordcloud(channel['wordcloud'], titles)
    
    if LDA:
        print 'LDA channel number: ', channel['topic_num']
        channel['topics'], lda_corpus = do_LDA(titles,
                                    channel['topic_num'])
        title_videoid = [(v['title'],v['videoId']) 
                            for v in videos]
        playlists = [[] for i in xrange(channel['topic_num'])]
        for i, x in enumerate(lda_corpus):
            playlists[x[0]].append(title_videoid[i])
        # save to temp file 
        channel['tempdir'] = tempfile.mkdtemp()
        outfile = open(channel['tempdir'] + '/filename', 'wb')
        pickle.dump(playlists, outfile)
        outfile.close()

def do_LDA(titles,num_topics):    
    dictionary = corpora.Dictionary(titles)
    corpus = [dictionary.doc2bow(title) for title in titles]
    threshold = 1/num_topics
    ldamodel = gensim.models.ldamodel.LdaModel(corpus, 
                num_topics=num_topics, id2word = dictionary, 
                passes=20, minimum_probability=threshold)
    # assign topics
    lda_corpus = [max(x,key=lambda y:y[1]) 
                        for x in ldamodel[corpus] ]
    return ldamodel.show_topics(num_topics=num_topics,
                                num_words=4), lda_corpus

def simplify_lib(fullLib, update=False):
    ''' for some unknown reason, using Youtube api v3
        with search.list does not give all videos,
        thus playlistitem.list is used to download
        videos if the channel is queried the 1st time
    '''
    if update:
        simplify_results = lambda video: {
            'title': video['snippet']['title'],
            'videoId': video['id']['videoId'], 
            'publishedAt': video['snippet']['publishedAt'],
            'channelTitle': video['snippet']['channelTitle']
            }
    else:
        simplify_results = lambda video: {
            'title': video['snippet']['title'],
            'videoId': video['snippet']['resourceId']['videoId'], 
            'publishedAt': video['snippet']['publishedAt'],
            'channelTitle': video['snippet']['channelTitle']
            }

    videoLib = map(simplify_results, fullLib)

    # update the database
    conn = sqlite3.connect('videos.sqlite')
    for v in videoLib:
        conn.execute('''INSERT INTO videos 
                (videoId, publishedAt, title, channelTitle)
                  VALUES (?,?,?,?)''', 
                 (v['videoId'], v['publishedAt'], 
                  v['title'], v['channelTitle']))
    conn.commit()
    conn.close()

def create_database():
    conn = sqlite3.connect('videos.sqlite')
    conn.execute(''' CREATE TABLE videos 
        (videoId TEXT NOT NULL PRIMARY KEY, \
        publishedAt TEXT NOT NULL,  \
        channelTitle TEXT NOT NULL, \
        title TEXT NOT NULL);''')
    conn.close()

def tokenize_text(stopw, text):
    ''' split the text, word stemming, stopword removal '''
    global porter

#    return [porter.stem(w) for w in re.findall(r'\w+',text)
    return [porter.stem(w) for w in tokenizer.tokenize(text)
                if w.lower() not in stopw]

def make_wordcloud(filename, titles):
    print filename, ' make_wordcloud'
    counts = Counter()
    for t in titles:
        counts.update(t)
    wordcloud = WordCloud().generate_from_frequencies(counts.items())
    plt.figure()
    plt.imshow(wordcloud)
    plt.axis("off")
    plt.savefig('static/'+filename, bbox_inches='tight')

def get_channel_names():
    conn = sqlite3.connect('videos.sqlite')
    c = conn.execute('SELECT DISTINCT channelTitle FROM videos')
    names = [x[0] for x in c]
    name_dict = dict(zip([x.lower() for x in names], names))
    conn.close()
    return name_dict

def load_channel(name):
    conn = sqlite3.connect('videos.sqlite')
    c = conn.execute('SELECT * FROM videos WHERE \
                channelTitle = ?',(name,))
    data = c.fetchall()
    global SQLKEYS
    return [dict(zip(SQLKEYS,x)) for x in data]
    
def get_last_video(channelname):
    conn = sqlite3.connect('videos.sqlite')
    c = conn.execute('SELECT * FROM videos \
                    WHERE channelTitle=?\
                    ORDER BY publishedAt DESC LIMIT 1',\
                    (channelname,))
    data = c.fetchall()[0]
    global SQLKEYS
    return dict(zip(SQLKEYS,data)) 

def delay1s(t):
    tt = iso8601.parse_date(t) + datetime.timedelta(seconds=1)
    return rfc3339.rfc3339(tt)

def update_channel(channel):
    old = get_last_video(channel['title'])
    youtube = make_youtube_api()
    results = youtube.channels().list(
                part = "contentDetails",
                forUsername = channel['title']
                ).execute()
    channelId = results['items'][0]['id']
    results = youtube.search().list(
                type = 'video',
                part = 'snippet',
                channelId = channelId, 
                maxResults=50,
                relevanceLanguage='en',
                publishedAfter=delay1s(old['publishedAt'])
                ).execute()
    videos = results['items']

    print 'update ',len(videos), 'videos', channelId
    if len(videos):
        simplify_lib(videos, update=True)
        return True
    return False

def make_youtube_api():
    with open ('my_key', 'r') as fin:
        DEVELOPER_KEY = fin.read().replace('\n', '')
    YOUTUBE_API_SERVICE_NAME = "youtube"
    YOUTUBE_API_VERSION = "v3"

    return build(YOUTUBE_API_SERVICE_NAME,
                    YOUTUBE_API_VERSION,
                    developerKey=DEVELOPER_KEY)

def query_Youtube(channel):
    ''' return False if this channel does not exist '''
    # check if already in database
    name_dict = get_channel_names()
    print name_dict
    print 'channel name: ', channel
    namekey = channel['title'].lower() 
    if namekey in name_dict.keys():
        channel['title'] = name_dict[namekey]
        return True

    # check if the json file exists
    filename = ''.join(('channels/', 
                    channel['title'],'.json'))
    if os.path.isfile(filename):
        with open(filename) as fin:
            videoLib = json.load(fin)
        simplify_lib(videoLib)
        return True
    youtube = make_youtube_api()
    results = youtube.channels().list(
                part = "contentDetails",
                forUsername = channel['title']
                ).execute()
    if (results['pageInfo']['totalResults'] != 1):
        return False

    # retrieve all information of all videos
    # note channelId is the same as playlist:uploads
    all_uploads = results["items"][0]["contentDetails"]\
                    ["relatedPlaylists"]["uploads"]

    results = youtube.playlistItems().list(
        part = "snippet",
        playlistId = all_uploads,
        maxResults = 50
        ).execute()
    videoLib = results['items'] 
    while ('nextPageToken' in results):
        results = youtube.playlistItems().list(
                part = "snippet",
                playlistId = all_uploads,
                pageToken = results['nextPageToken'],
                maxResults = 50
        ).execute()
        videoLib += results['items']

    channel['title'] = videoLib[0]['snippet']['channelTitle']

    # save video information
    '''
    print channel['title'], 'before save'
    with open('channels/'+channel['title']+'.json', 'w') as outfile:
        json.dump(videoLib, outfile)
    '''

    simplify_lib(videoLib)
    return True






