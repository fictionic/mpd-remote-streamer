# mpd-remote-streamer
# Dylan Forbes
# Computer Networks


import sys, socket, os, time
import player, http_client, mpd_client

STREAMER_BUFFER_SIZE = 7000
MAIN_DEBUGLEVEL = 1
REMOTE_DEBUGLEVEL = 1
STREAMER_DEBUGLEVEL = 1
PLAYER_DEBUGLEVEL = 1

def print_debug(msg, level):
    if level <= MAIN_DEBUGLEVEL:
        print(msg)

class mpd_remote_streamer():

    def __init__(self, mpv_path, streamer_fifo_path, mpv_cmds_fifo_path, server_ip, mpd_port, http_port):

        self.streamer_fifo_path = streamer_fifo_path
        self.mpv_cmds_fifo_path = mpv_cmds_fifo_path

        # the command that Popen will call in a new process (the media player, 
        # controlled by writing commands to mpv_cmds_fifo_path, a handy feature
        # of mpv) 
        self.playercmd = [mpv_path, "--input-file=" + mpv_cmds_fifo_path, streamer_fifo_path]

        # create mpd client, connect it to the server
        self.remote = mpd_client.mpd_client(server_ip, mpd_port, REMOTE_DEBUGLEVEL)
        self.remote.connect_to_server()
        # get the status of the server 
        self.remote.retrieve_status()

        # create player
        self.player = player.player(self.playercmd, mpv_cmds_fifo_path, PLAYER_DEBUGLEVEL)

        # create http client
        self.streamer = http_client.http_client(server_ip, http_port, streamer_fifo_path, STREAMER_BUFFER_SIZE, STREAMER_DEBUGLEVEL)

        # if the mpd server is playing, initialize the http client's connetion 
        state = self.remote.status.state
        if state == "play":
            self.player.play()
            self.streamer.play()
            # check if the streamer successfully connected
            if not self.streamer.connected:
                self.print_debug("Error: could not connect to HTTP server!", 1) 
                self.quit()

        self.message = None

    def quit(self):
        # the order in which these things are called is important!
        self.remote.quit()
        self.streamer.quit()
        self.player.quit()
        os.remove(self.streamer_fifo_path)
        os.remove(self.mpv_cmds_fifo_path)
        print("bye!")
        sys.exit(0)

    def play(self):
        if self.remote.status.playlistlength == "0":
            self.message = " (nothing to play!)" 
            return
        if self.remote.status.state != "play":
            self.remote.play()
            # if the http server doesn't know the mpd server is playing, the http connection won't stay open
            # but there seems to be a bit of a delay
            # this solution is super hacky but i don't know if there's a better way
            if not self.streamer.connected:
                time.sleep(1) 
            
        self.player.play()
        self.streamer.play()

    def pause(self):
        self.player.pause()
        self.remote.pause()
        self.streamer.pause()

    def stop(self):
        self.streamer.stop()
        self.player.quit()
        self.remote.stop()

    def prev(self):
        if self.remote.status.state != "stop":
            self.remote.prev()
            self.player.play() # mpd plays when the current track is changed 
            self.streamer.play()
        else:
            print(" (playback stopped; can't do that)")

    def next_(self):
        if self.remote.status.state != "stop":
            self.remote.next_()
            self.player.play() # mpd plays when the current track is changed 
            self.streamer.play()
            print("streamer done")
        else:
            self.message = " (playback stopped; can't do that)"

    def clear(self):
        self.streamer.stop()
        self.player.quit()
        self.remote.clear()

    def findadd(self, cmd):
        self.remote.findadd(cmd)

    def find(self, cmd):
        self.remote.find(cmd)

    def playlistinfo(self):
        self.remote.playlistinfo()

    def display_help(self):
        self.message = """Commands:
 quit                  quit mpd-remote-streamer
 help                  display this message
 play                  tell mpd to play; stream the audio; play the audio via mpv
 pause                 tell mpd to pause; pause mpv
 stop                  tell mpd to stop; stop streaming; quit mpv
 prev                  tell mpd to play the previous track in the playlist, resume streaming if stopped 
 next                  tell mpd to play the next track in the playlist, resume streaming if stopped
 clear                 tell mpd to clear the playlist; stop streaming; quit mpv
 findadd <tag> <val>   tell mpd to add all files in its database whose <tag> has value <val> to the playlist (case-sentitive, quotes needed for multi-word arguments)
 find <tag> <val>      list all files in mpd's database whose <tag> has value <val> to the playlist (case-sentitive, quotes needed for multi-word arguments)
 playlistinfo          display the current mpd playlist"""

    def display_info(self):
        print("~~~~~~~~~~~~~~~~~~~~")
        if self.remote.status.playlistlength:
            print(" Playlist length: " + self.remote.status.playlistlength)
        if self.remote.status.song_title != None:
            message = " Current song: "
            if self.remote.status.song_artist:
                message += self.remote.status.song_artist + " - "
            if self.remote.status.song_title:
                message += self.remote.status.song_title
            print(message)
            state = self.remote.status.state
            if state == "play":
                state = "playing"
            elif state == "pause":
                state = "paused"
            elif state == "stop":
                state = "stopped"
            print(" [" + state + "]")
        else:
            print(" [stopped]")
        print("~~~~~~~~~~~~~~~~~~~~")

    def display_message(self):
        if self.message: 
            print(self.message)
            self.message = None
            return True
        else:
            self.message = None
            return False

    def update(self):
        self.remote.update()

    def listen(self):
        while True:
            try:
                self.remote.wait()
                if not self.display_message():
                    self.display_info()
                cmd = input(">> ")
                if cmd == "":
                    continue
                if cmd == "quit":
                    self.quit()
                    continue
                if cmd == "help":
                    self.display_help()
                    continue
                if cmd == "play":
                    self.play()
                    continue
                if cmd == "pause":
                    self.pause()
                    continue
                if cmd == "stop":
                    self.stop()
                    continue
                if cmd == "prev":
                    self.prev()
                    continue
                if cmd == "next":
                    self.next_()
                    continue
                if cmd == "clear":
                    self.clear()
                    continue
                if cmd[:8] == "findadd ":
                    self.findadd(cmd)
                    continue
                if cmd[:5] == "find ":
                    self.find(cmd)
                    continue
                if cmd == "playlistinfo":
                    self.playlistinfo()
                    continue
                if cmd == "update":
                    self.update()
                    continue
                else:
                    print("main: unrecognized command; type 'help' for available commands")

            except KeyboardInterrupt:
                self.quit()

def usage():
    print("Usage: python mpdrs.py <mpd/http server ip> <mpd server port> <http server port>")
    sys.exit()

def main():
    if len(sys.argv) != 4:
        usage() 

    # check that the user has mpv installed
    from subprocess import check_output, CalledProcessError, DEVNULL
    try:
        mpv_path = check_output(["which", "mpv"], stderr=DEVNULL).decode("ascii")[:-1]
    except CalledProcessError:
        print("Error: mpv not found! Make sure the binary for mpv is in your PATH environment variable") 
        return

    # check that the given ip:port point to a running http server
    print_debug("mpdrs: testing connection to http server...", 3)
    http_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        http_sock.connect((sys.argv[1], int(sys.argv[3])))
        print_debug("mpdrs: connected to http server", 3) 
    except ConnectionRefusedError:
        print_debug("Error: Connection refused!\nMake sure the HTTP server is running, and that you've entered the correct IP/port numbers.\nAborting.", 1)
        return

    # make the fifo files
    mpv_cmds_fifo_path = "/tmp/mpdrs-mpv-cmds.fifo"
    if not os.path.exists(mpv_cmds_fifo_path):
        try:
            os.mkfifo(mpv_cmds_fifo_path)
        except Exception:
            self.print_debug("Error: Failed to create fifo " + mpv_cmds_fifo_path, 1)
            return
    streamer_fifo_path = "/tmp/mpdrs-streamer.fifo"
    if not os.path.exists(streamer_fifo_path):
        try:
            os.mkfifo(streamer_fifo_path)
        except Exception:
            self.print_debug("Error: Failed to create fifo " + streamer_fifo_path, 1)
            return

    # ok we're good!
    remote_streamer = mpd_remote_streamer(mpv_path, streamer_fifo_path, mpv_cmds_fifo_path, sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    remote_streamer.listen()

main()

