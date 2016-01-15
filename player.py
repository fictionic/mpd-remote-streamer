# mpd-remote-streamer
# Dylan Forbes
# Computer Networks


import sys, os, subprocess

class player():
    def __init__(self, player_command, mpv_cmds_fifo_path, debuglevel):
        self.player_command = player_command
        self.mpv_cmds_fifo_path = mpv_cmds_fifo_path 
        self.debuglevel = debuglevel
        self.mpv_running = False
        self.playing = False

    def print_debug(self, msg, level):
        if level <= self.debuglevel:
            print(msg)

    def launch(self):
        subprocess.Popen(self.player_command, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.print_debug("player: launched mpv", 2) 
        self.mpv_running = True

    def send_cmd(self, cmd):
        if self.mpv_running:
            # mpv only reads commands when a writer closes the file, it doesn't stream the contents continuously
            fifo = open(self.mpv_cmds_fifo_path, "w")
            fifo.write(cmd + "\n")
            fifo.close()

    def pause(self):
        if self.playing:
            self.send_cmd("cycle pause")
            self.print_debug("player: sent message 'cycle pause' to mpv", 2)
            self.playing = False

    def stop(self):
        if self.playing:
            self.send_cmd("cycle pause")
            self.print_debug("player: sent message 'cycle pause' to mpv", 2)
        self.playing = False

    def play(self):
        if not self.mpv_running:
            self.launch()
        else:
            if not self.playing:
                self.send_cmd("cycle pause")
                self.print_debug("player: sent message 'cycle pause' to mpv", 2)
        self.playing = True

    def quit(self):
        self.send_cmd("quit")
        self.print_debug("player: sent message 'quit' to mpv", 2)
        self.mpv_running = False
