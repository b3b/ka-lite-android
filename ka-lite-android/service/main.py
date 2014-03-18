import os
import BaseHTTPServer
from SimpleHTTPServer import SimpleHTTPRequestHandler


def run(port=8032):
    os.chdir('../khan-exercises')
    addr = ('', int(port))
    server = BaseHTTPServer.HTTPServer(addr, SimpleHTTPRequestHandler)
    server.serve_forever()

if __name__ == '__main__':
    run()
