# mpd-remote-streamer
# Dylan Forbes
# Computer Networks


import sys, socket, os, multiprocessing, threading

class http_client():
    def __init__(self, ip, port, streamer_fifo_path, buffer_size, debuglevel):
        self.debuglevel = debuglevel
        self.ip = ip
        self.port = port
        self.requestpath = "/mpd.ogg"
        self.http_sock = None
        self.streamer_fifo_path = streamer_fifo_path
        self.buffer_size = buffer_size
        self.amount_buffered = 0
        self.fifo_opened = False
        self.connected = False # if we have a connection to the server
        self.streaming = False # if the server is currently sending us data
        self.buffering = False # if we're saving up data before writing to the fifo
        self.writing = False # if we're writing to the fifo 
        self.quitting = threading.Event()

        # first create pipe to communicate with the thread
        self.to_child, self.from_parent = multiprocessing.Pipe()
        # then create separate thread for it to run in, so it can write to audio pipe while we do other stuff here
        self.streamer_thread = threading.Thread(target=self.stream)
        # then run it
        self.streamer_thread.start()
        self.print_debug("streamer: started child thread", 3)

    def print_debug(self, msg, level):
        if level <= self.debuglevel:
            print(msg)
    
    def wait_for_child(self):
        # wait until the child thread tells us it's ready 
        self.print_debug("streamer: waiting for ok from child...", 3)
        if self.to_child.recv() == "OK":
            self.print_debug("streamer: child says ok", 3)
            return

    def quit(self):
        if self.http_sock: 
            self.print_debug("streamer: closing connection", 1)
            self.http_sock.close()
        self.to_child.send("quit")
        if self.streamer_thread.is_alive():
            self.streamer_thread.join()
            self.print_debug("streamer: streamer_thread joined", 3)

    def play(self):
        self.to_child.send("play")
        self.wait_for_child()

    def pause(self):
        self.to_child.send("pause")
        self.wait_for_child()

    def stop(self):
        self.to_child.send("stop")
        self.wait_for_child()

    def open_fifo(self):
        if not self.fifo_opened:
            self.print_debug("streamer: opening fifo", 3)
            self.fifo = open(self.streamer_fifo_path, "wb")
            self.fifo_opened = True

    def close_fifo(self):
        if self.fifo_opened:
            self.print_debug("streamer: closing fifo", 3)
            try:
                self.fifo.close()
            except:
                # for some reason you can't close a fifo that's already closed on the other end?
                pass
            self.fifo_opened = False

    def connect_to_server(self): 
        # connect to to server
        self.print_debug("streamer: connecting to http server...", 1)
        self.http_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.http_sock.connect((self.ip, self.port))
        self.print_debug("streamer: connected to http server at %s:%s" % (self.ip, self.port), 1) 
        self.connected = True

    def receive(self):
        self.print_debug("streamer: receiving from http server...", 4)
        return self.http_sock.recv(2048)

    def request_audio(self):
        self.print_debug("streamer: requesting audio", 3)
        # request audio data from server
        self.amount_buffered = 0
        msg = "GET " + self.requestpath + " HTTP/1.1\r\nAccept: */*\r\n\r\n"
        self.print_debug("streamer: sending http request", 2) 
        self.http_sock.sendall(msg.encode("UTF-8"))

        # filter out the HTTP header of the response
        firstblock = ''
        self.print_debug("streamer: waiting for response from HTTP server...", 2)
        firstblock = self.receive()
        self.print_debug("streamer: received response from HTTP server", 2)
        offset = firstblock.find(b'\r\n\r\n') + 4 # len(b'\r\n\r\n') == 4
        # (sometimes it sends the data in the same packet as the response header, sometimes it doesn't)
        initialdata = b''
        if offset < len(firstblock):
            # remember this block of data for later!
            initialdata = firstblock[offset:]
        # receive first block of actual data
        self.print_debug("streamer: done requesting audio", 3)
        return initialdata

    def check_for_messages(self):
        try:
            # if we're playing, just poll; otherwise block on recv (to reduce cpu usage)
            if (self.connected and self.from_parent.poll()) or not self.connected:
                message = self.from_parent.recv()
                self.print_debug("streamer: received message from parent: " + message, 2)

                # perform necessary actions
                if message == "play":
                    if not self.connected:
                        self.connect_to_server()
                    if self.connected: # if we actually succeeded in connecting
                        if not self.streaming: # self.streaming is only true after we've requested the audio and we haven't told mpd to stop
                            self.data = self.request_audio()
                            self.streaming = True
                            self.buffering = True # start buffering
                            self.print_debug("streamer: started buffering...", 2)
                        else: # if we were already streaming, there's nothing to do here
                            self.from_parent.send("OK")
                    else:
                        self.print_debug("streamer: Error! Failed to connect to server!", 0)
                        # tell parent we're ready (as ready as we're gonna get)
                        self.from_parent.send("OK")

                elif message == "pause":
                    self.print_debug("streamer: stopped writing to fifo", 2)
                    self.writing = False
                    self.buffering = False
                    # tell parent we're ready
                    self.from_parent.send("OK") 
                    
                elif message == "stop":
                    self.print_debug("streamer: stopped writing to fifo", 2)
                    self.writing = False
                    self.buffering = False
                    self.connected = False
                    self.streaming = False
                    self.close_fifo()
                    # tell parent we're ready
                    self.from_parent.send("OK") 

                elif message == "quit":
                    self.writing = False
                    self.buffering = False
                    self.streaming = False
                    self.close_fifo()
                    self.quitting.set()
                    # tell parent we're ready
                    self.from_parent.send("OK") 

        except KeyboardInterrupt:
            self.quit()

    def stream(self):
        while True:
            #print("buffering: " + str(self.buffering))
            ##print("writing: " + str(self.writing))
            # check for messages from main
            self.check_for_messages()
            if self.quitting.is_set():
                break
            if self.streaming:
                # buffer up to the buffer amount
                if self.buffering:
                    # receive data
                    self.data += self.receive()
                    if len(self.data) > self.buffer_size:
                        self.print_debug("streamer: buffer size reached, started writing to fifo", 2)
                        self.buffering = False
                        self.writing = True
                        self.open_fifo()
                        # tell parent we're ready
                        self.from_parent.send("OK") 
                else:
                    # write to fifo
                    if self.writing and self.data:
                        # write the OGG data to the pipe
                        try:
                            self.fifo.write(self.data)
                        except KeyboardInterrupt:
                            self.quit() 
                    # receive more data
                    self.data = self.receive()
            else:
                if self.connected:
                    self.receive() # eat up the silence that the server sends us when paused 
