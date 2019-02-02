# mpd-remote-streamer
An MPD client that also streams the audio from MPD's HTTP streaming server, and plays it back with mpv.

#### USAGE
    python3 mpdrs.py <server_ip> <mpd_port> <http_port>

#### DESCRIPTION
I made this for my final project of my Computer Networks class; it is mostly a proof-of-concept. However, I do believe it has serious promise, at least as an idea.  
MPD's HTTP streaming server is intended to be used quite separately from the MPD server itself--generally those streaming from the HTTP server would not have control over the MPD process. For example, one might release the IP/port of one's MPD HTTP stream for others to tune in to, but they wouldn't want listeners controlling playback and browsing their library (I believe MPD supports authentication of clients). However, if you both control an MPD process and stream its output, you can stream all of your music from your computer over the internet! It's pretty nifty.

#### SETUP
For this to be of any use, you must know the IP address of a running MPD server that is configured to output to an HTTP streaming server, i.e., the following must appear in the `mpd.conf` of the MPD process:

```
audio_output {
	type	"httpd"
	name	"My HTTP Stream"
	encoder	"vorbis" #or use "lame" for mp3, doesn’t matter
	port	"8000"
	bitrate	"128"
	format	"44100:16:1"
	max_clients	"0" #0=nolimit
}
```
Slightly more information about MPD's HTTP streaming output can be found [here](https://wiki.archlinux.org/index.php/Music_Player_Daemon/Tips_and_tricks#HTTP_Streaming) (it's quite sparsely documented, and thus I had to figure out exactly how the protocol works in relation to MPD.)

Further, you'll need `mpv` installed to be able to hear the playback. Get it here: http://mpv.io

Lastly, this was written and tested primarily on Linux; I did some testing on Mac with the MPD process running on Linux, and it worked fine. But I haven't done extensive testing, so take caution.
