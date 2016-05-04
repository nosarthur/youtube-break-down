
from flask import Flask, render_template, request, \
                    redirect, session, url_for 
from wtforms import Form, TextAreaField, validators
import json
import shutil
import pickle

from topic_modeling import analyze_videos, query_Youtube, \
                        do_LDA, update_channel

app = Flask(__name__)

class ChannelForm(Form):
    channel_title = TextAreaField('',[validators.DataRequired()])

class StopwordsForm(Form):
    stopwords = TextAreaField('',[validators.DataRequired()])

@app.route('/', methods=['POST','GET'])
def index():
    form = ChannelForm(request.form)
    if request.method == 'POST' and form.validate():
        channel = {}
        channel['title'] = request.form['channel_title']
        if query_Youtube(channel):
            session['channel'] = channel
            analyze_videos(channel, wordcloud=True)
            return redirect(url_for('results'))
        else:
            form.channel_title.errors = ['no such channel']

    return render_template('youtube_app.html', form=form)

@app.route('/clear')
def clear():
    print 'clear'
    if session.has_key('tempdir'):
        shutil.rmtree(session['tempdir'])
    session.clear()
    return redirect(url_for('index'))

@app.route('/results', methods=['POST','GET'])
def results():
    if request.method == 'POST' and \
                request.form['submit_btn'] == 'update':
        print 'update'
        if update_channel(session['channel']):
            analyze_videos(session['channel'], wordcloud=True)
    if request.method == 'POST' and \
                request.form['submit_btn'] == 'add stopwords':
        form = StopwordsForm(request.form)
        if form.validate():
            session['channel']['stopwords'] = request.form['stopwords']
            print 'stop words: ', request.form['stopwords']
            analyze_videos(session['channel'],LDA=True)
        return render_template('results.html',
                                channel=session['channel'],
                                form=form)
    if 'channel' in session:
        form = StopwordsForm(request.form)
        return render_template('results.html',
                                channel=session['channel'],
                                form=form)
    return redirect(url_for('index'))

@app.route('/playlist')
def playlist():
    index = int(request.args.get('playlist'))

    infile = open(session['channel']['tempdir'] + '/filename', 'rb')
    playlists = pickle.load(infile)
    infile.close()
    print len(playlists[index])
    return render_template('playlist.html',
                            playlist=playlists[index],
                 topic=session['channel']['topics'][index][1])

if __name__ == '__main__':
    app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'
    app.run(debug=True)



