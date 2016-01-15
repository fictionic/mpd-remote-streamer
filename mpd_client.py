# mpd-remote-streamer
# Dylan Forbes
# Computer Networks


import sys, socket, os, multiprocessing, threading, time

class mpd_client():

    def __init__(self, ip, port, debuglevel):
        self.status = self.status()
        self.ip = ip
        self.port = port
        self.idler_receiver = threading.Thread(target=self.keep_idle_and_receive)
        self.from_idler_receiver, self.from_remote = multiprocessing.Pipe()
        self.quitting = threading.Event()
        self.status_changed = threading.Event()
        self.expecting_status_change = False
        self.idle_lock = threading.Lock()
        self.idle = False
        self.waiting = False
        self.debuglevel = debuglevel

    def print_debug(self, msg, level):
        if level <= self.debuglevel:
            print(msg)
    
    class status():
        def __init__(self):
            self.volume = None
            self.repeat = None
            self.single = None
            self.consume = None
            self.playlist = None
            self.playlistlength = None
            self.mixrampdb = None
            self.state = None
            self.song = None
            self.songid = None
            self.time = None
            self.elapsed = None
            self.bitrate = None
            self.audio = None
            self.nextsong = None
            self.nextsongid = None
            # ones I'm adding
            self.song_title = None
            self.song_artist = None
            self.song_album = None

    def recv_all(self):
        data_parsed = [b'']
        done = False
        while not done:
            self.print_debug("remote: receiving from mpd server via pipe...", 3)
            new_bytes = self.from_remote.recv_bytes()
            self.print_debug(new_bytes, 4)
            data_parsed_chunks = new_bytes.split(b'\n')
            data_parsed[-1] += data_parsed_chunks.pop(0)
            data_parsed += data_parsed_chunks
            if len(new_bytes) == 0:
                done = True
                response_type = None
                break
            if data_parsed[-1] == b'':
                response_type = data_parsed[-2][:3].strip()
                if response_type in [b'OK', b'ACK']:
                    done = True
                    break
        if response_type == None:
            self.print_debug("remote: connection to mpd server lost!", 1)
            self.quitting.set()
            self.idler_receiver.join()
            self.quitting.clear()
            self.idler_receiver = threading.Thread(target=self.keep_idle_and_receive)
            self.connect_to_server()
            return None, None
        response_list = b'\n'.join(data_parsed).decode("UTF-8").split('\n') # this is the dumbest stream of method calls I've ever written 
        response_list.pop() # remove newline at end
        return (response_list.pop(), response_list) # returns (response code ("OK ..." | "ACK ..."), response message)

    # child thread, responsible for constantly receiving from the socket and feeding to the pipe
    # which the parent thread reads from. it also has the job of checking if the status has changed while we're idle,
    # and re-sending the idle (but only if the parent thread isn't currently in wait())
    def keep_idle_and_receive(self):
        while not self.quitting.is_set():
            try:
                try:
                    self.print_debug("remote: idler-receiver: receiving data...", 3) 
                    data = self.mpd_sock.recv(4096)
                    self.idle = False
                    self.print_debug("remote: idler-receiver: received data:\n" + data.decode("UTF-8"), 3) 
                except:
                    data = b''
            except KeyboardInterrupt:
                break
            if not data:
                self.print_debug("remote: idler-receiver: error receiving from mpd socket!", 0) 
                self.print_debug("remote: idler-receiver: re-establishing connection...", 0) 
                self.connect_to_server()
                continue
            
            if data.find(b"changed: ") == 0:
                self.print_debug("remote: idler-receiver: status changed after idle!", 4)
                self.status_changed.set()
                if not self.waiting:
                    self.print_debug("remote: idler-receiver: we're not waiting, so go ahead and send idle", 4) 
                    self.send_cmd_raw("idle")
                    self.idle = True
            else:
                self.print_debug("remote: idler-receiver: sending data to parent thread...", 3) 
                self.from_idler_receiver.send_bytes(data)
        self.print_debug("remote: idler-receiver: quitting flag set, exiting thread!", 3) 

    # called before displaying the command prompt
    # checks to see if we need to fetch the status of the mpd server,
    # which is indicated by the fact that we have received something after sending
    # "idle"--this only happens when the server's status changed (e.g. the track changed)
    # if we don't notice a change w/in 50ms then we just give up, we don't want to force
    # the user to wait just because the server is slow. it might be that the last command called
    # didn't actually change the status at all (e.g. calling "stop" when we're already stopped)
    def wait(self, ms=50):
        self.waiting = True
        while self.expecting_status_change:
            if self.status_changed.is_set():
                while self.status_changed.is_set():
                    self.print_debug("remote: wait: status changed after idle, retrieving status...", 3)
                    self.retrieve_status()
                    self.status_changed.clear()
                    self.expecting_status_change = False
            else:
                if ms == 0:
                    break
                else:
                    time.sleep(.001)
                    ms -= 1
        self.waiting = False

    def connect_to_server(self):
        try:
            self.mpd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.print_debug("remote: connecting to mpd server...", 1)
            self.mpd_sock.connect((self.ip, self.port))
        except ConnectionRefusedError:
            self.print_debug("remote: connection refused!", 0)
            self.quit()
            sys.exit(1)
        response = self.mpd_sock.recv(1024)
        self.print_debug(response, 3)
        if response != b'':
            self.print_debug("remote: connected to mpd server at %s:%s" % (self.ip, self.port), 1)
            self.send_cmd_raw("idle")
            self.idle = True
            if not self.idler_receiver.is_alive():
                self.idler_receiver.start()
        else:
            self.print_debug("remote: something went wrong!", 0)
            self.print_debug(response.decode("UTF-8"), 0)
            self.quit()
            sys.exit(1)
    
    def send_cmd_raw(self, cmd):
        if cmd == "idle" or cmd == "noidle":
            debuglevel = 3
        else:
            debuglevel = 1
        self.print_debug("remote: sending message to mpd server: " + cmd, debuglevel)
        self.mpd_sock.sendall((cmd + "\n").encode("UTF-8"))

    # wrapper for send that makes sure we always end up in an idle state, so the server doesn't disconnect us
    def send_cmd(self, cmd):
        if self.idle:
            self.send_cmd_raw("noidle")
            self.idle = False
            self.recv_all() # get the OK from the server
        self.send_cmd_raw(cmd)
        self.print_debug("remote: waiting for response from server...", 1) 
        code, response = self.recv_all()
        if not self.idle:
            self.send_cmd_raw("idle")
            self.idle = True
        return (code, response)

    def retrieve_status(self):
        self.status.__init__() # clear status, so ones that aren't filled out by this process are known to have a null value
        code, resp = self.send_cmd("status")
        if code != "OK":
            self.print_debug("remote: failed to fetch status!", 1)
            self.print_debug(code, 1)
            return
        self.parse_status(resp)
    
    def parse_status(self, resp): 
        status = resp
        # parse response, assign to attributes of self.status
        for i in range(len(status)):
            status[i] = status[i].split(": ")
        for attr in status:
            setattr(self.status, attr[0], attr[1])
        # get info about current playing song
        if self.status.song != None:
            code, resp = self.send_cmd("playlistid " + self.status.songid)
            if code != "OK":
                self.print_debug("remote: failed to fetch info about current song!", 1)
                self.print_debug("mpd: " + code)
            cur_song_info = self.parse_song_info(resp)
            if "Title" in cur_song_info:
                self.status.song_title = cur_song_info["Title"]
            if "Artist" in cur_song_info:
                self.status.song_artist = cur_song_info["Artist"]
            if "Album" in cur_song_info:
                self.status.song_album = cur_song_info["Album"]
            return

    def parse_song_info(self, info_list):
        info = {}
        for item in info_list:
            item_split = item.split(": ")
            info[item_split[0]] = item_split[1]
        return info

    def play(self):
        self.send_cmd("play")
        self.expecting_status_change = True

    def pause(self):
        self.send_cmd("pause 1")
        self.expecting_status_change = True

    def stop(self):
        self.send_cmd("stop")
        self.expecting_status_change = True

    def prev(self):
        self.send_cmd("previous")
        self.expecting_status_change = True

    def next_(self):
        self.send_cmd("next")
        self.expecting_status_change = True

    def clear(self):
        self.send_cmd("clear")
        self.expecting_status_change = True

    def findadd(self, findcmd):
        code, resp = self.send_cmd(findcmd)
        if code != "OK":
            self.print_debug("remote: error executing command!", 1)
            self.print_debug("mpd: " + str(code), 1)
            return
        self.expecting_status_change = True

    def find(self, findcmd):
        code, resp = self.send_cmd(findcmd)
        if code != "OK":
            self.print_debug("remote: error executing command!", 1)
            self.print_debug("mpd: " + str(code), 1)
            return
        # get the results!
        results = []
        item = {}
        for pair in resp:
            temp = pair.split(": ")
            key, value = temp[0], ": ".join(temp[1:])
            if key in ["Title", "Artist", "Album"]:
                item[key] = value
            if item != {} and key == "file":
                item = item["Artist"] + "\t\t" + (item["Album"] if "Album" in item else "[no album]") + "\t\t" + item["Title"]
                results.append(item)
                item = {}
        item = item["Artist"] + "\t\t" + item["Album"] + "\t\t" + item["Title"]
        results.append(item)
        self.print_debug("\n".join(results), 0)

    def playlistinfo(self):
        code, resp = self.send_cmd("playlistinfo")
        if code != "OK":
            self.print_debug("remote: error executing command!", 0)
            self.print_debug("mpd: " + str(code), 1)
        # parse response
        playlist = []
        item = {}
        for pair in resp:
            temp = pair.split(": ")
            key, value = temp[0], ": ".join(temp[1:])
            if key in ["Title", "Artist", "Album", "Track"]:
                item[key] = value
            if key == "Id":
                item = item["Track"] + "\t" + item["Artist"] + "\t\t" + item["Album"] + "\t\t" + item["Title"]
                playlist.append(item)
                item = {}
        if playlist:
            self.print_debug("\n".join(playlist), 0)
        else:
            self.print_debug("[playlist empty]", 0)

    def update(self):
        code, resp = self.send_cmd("update")
        if code != "OK":
            self.print_debug("remote: error executing command!", 0)
            self.print_debug("mpd: " + str(code), 1)
        else:
            self.print_debug("remote: successfully updated mpd database", 1)

    def quit(self):
        self.quitting.set()
        try:
            self.send_cmd_raw("clearerror") # so the idler-receiver thread has something to receive, so it can see we've set the quitting flag
            socket_broken = False
        except:
            socket_broken = True # the socket might be broken (we might have called quit() after failing to reconnect to the server) 
        if self.idler_receiver.is_alive():
            self.idler_receiver.join()
            self.print_debug("remote: idler-receiver thread joined", 3)
        if not socket_broken:
            self.print_debug("remote: closing connection...", 2)
            self.mpd_sock.close()

