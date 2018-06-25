#!/usr/bin/env python
import sys,os
import socket, logging, json, re
from multiprocessing import Process, Queue
import subprocess, threading, time
sys.path.append(os.path.join(os.path.dirname(__file__),"pyZabbixSender"))
from pyZabbixSender import pyZabbixSender

#logLevel = logging.WARNING 
logLevel = logging.INFO

class Metrics():
    _instance = None 
    metrics = { 
        "MSG_RECV_TOTAL" : 0,
        "MSG_SEND_TOTAL" : 0,
        "MSG_RECV_ERROR" : 0,
        "MSG_SEND_ERROR" : 0
    }
    zabbixHost='zabbixproxy'
    timeout = 600
    
    def __new__(cls):
        if Metrics.__instance is None:
            Metrics.__instance = object.__new__(cls)
        return Metrics.__instance
    
    @classmethod
    def send2Proxy(self, item, value):
        msg_template='ZSMSG,00000,{"Server" : "zabbix.dev.ath","Items" : [{"host" : "%s","item" : "%s","value" : "%s"}]}'
        msg = (msg_template % (self.zabbixHost, item, value))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(msg, ("localhost", port))

    @classmethod
    def incrMetric(self, metric, by):
        zItemKeys = {
                "MSG_RECV_TOTAL" : 'ZABBIX.PROXY.MSG.RECV.TOTAL',
                "MSG_SEND_TOTAL" : 'ZABBIX.PROXY.MSG.SEND.TOTAL',
                "MSG_RECV_ERROR" : 'ZABBIX.PROXY.MSG.RECV.ERROR',
                "MSG_SEND_ERROR" : 'ZABBIX.PROXY.MSG.SEND.ERROR'
            }
        try:
	    if by:
		self.metrics[metric] += by
            else:
		self.metrics[metric] += 1
            zValue = self.metrics[metric]
            zItem = zItemKeys[metric]
            #all error counters should be sent immediately:
            if metric == "MSG_RECV_ERROR" or metric == "MSG_SEND_ERROR": 
                self.send2Proxy(zItem, zValue) 
        except Exception as e:
            print ('Cant increment, cuz: %s' % e)

    @classmethod
    def serve(self):
        while True:
            print ('Sending ZabbixProxy metrics')
            try:
                self.send2Proxy('ZABBIX.PROXY.MSG.RECV.TOTAL', self.metrics['MSG_RECV_TOTAL'])
                self.send2Proxy('ZABBIX.PROXY.MSG.SEND.TOTAL', self.metrics['MSG_SEND_TOTAL'])
            except Exception as e:
                print ('ZabbixProxy metrics sending failed with: %s' % e)
            time.sleep(Metrics.timeout)


class ProxyServer:
    def __init__(self):
        logging.getLogger().setLevel(logLevel)
        logging.info('Initializing server on port %s', port)
	self.dump = Queue(maxsize=0)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,3000000)
        self.sock.bind(('', port))
        self.clients_list = []

    def sendToZabbix(self, log, zabbix_server, host, item, value):
        try:
            rCode = sender.sendSingle(host, item, value)
            if rCode[0] != sender.RC_OK:
                    log.warning("Message sent failed with return code: %s\n\t\tMessage: %s %s %s\n\t\tResponse from zabbix server: %s" % (rCode[0], host, item, value, rCode[1]))
                    return 1
        except Exception as e:
                log.warning('Message sent failed with exception: %s', e)
                return 1
        return 0

    def processMsg(self, client, msg):
        if client[0] != '127.0.0.1' : Metrics.incrMetric('MSG_RECV_TOTAL', None)
        log = logging.getLogger()
        msg = bytes.decode(msg)
        msg = msg.replace('\n', '').replace('\r', '')
        log.info("%s||Received message from %s : '%s'", time.strftime("%H:%M:%S"), client, msg) 
        # remove multilines
        msg = re.sub( r"\r", " ", msg)
        msg = re.sub( r"\n", " ", msg)

        regex = re.match("(ZSMSG),(\d+),(.*)$", msg, re.MULTILINE)
        if regex is None or len(regex.groups()) < 3:
            log.warning("Not correct format of message")
            Metrics.incrMetric('MSG_RECV_ERROR', None)
            return
        msgType = regex.group(1)
        checkSum = regex.group(2)
        body = regex.group(3)
        log.debug("msgType = %s", msgType)
        log.debug("length = %s", checkSum)
        log.debug("body = '%s'", body)

        try:
            decodedJSON = json.loads(body)
            zabbix_server = decodedJSON['Server']
            items = decodedJSON['Items']
        except Exception as e:
            log.warning("Can't decode message: %s", body)
            log.warning(e)
            Metrics.incrMetric('MSG_RECV_ERROR', None)
            return
        log.debug("msgType: %s, checkSum: %s, message: %s", msgType, checkSum, decodedJSON)
        if len(zabbix_server) == 0:
            log.warning("Zabbix server is not specified")
            Metrics.incrMetric('MSG_RECV_ERROR', None)
            return
        if len(items) < 1:
            log.warning("At least one item required")
            Metrics.incrMetric('MSG_RECV_ERROR', None)
            return
	recvErr=0
	sendErr=0
	sendTot=0
        for curitem in items:
            log.debug(curitem)
            try:
                host = curitem['host']
                item = curitem['item']
                value = curitem['value']
            except Exception as e:
                log.warning("One of required parameters are not specified(host,item,value)")
		recvErr += 1
                continue
            attempt=0
            while True:
                RCMsg = self.sendToZabbix(log, zabbix_server, host, item, value)
	        if RCMsg == 0:
                    sendTot += 1
                    break
	        elif attempt < 2:
                    attempt += 1
                    continue
                sendErr += 1
                break
	if recvErr != 0:
	    Metrics.incrMetric('MSG_RECV_ERROR', recvErr)
	if sendErr != 0 and client[0] != '127.0.0.1':
	    Metrics.incrMetric('MSG_SEND_ERROR', sendErr)
	Metrics.incrMetric('MSG_SEND_TOTAL', sendTot)

    def dump_packets(self):
        while True:
            msg, addr = self.sock.recvfrom(42000)
            self.dump.put((msg,addr))
    
    def read_packets(self):
        while True:
            msg, addr = self.dump.get()
            self.processMsg(addr,msg)
    
    def listen_requests(self):
        dumper = threading.Thread(target=self.dump_packets)
        reader = threading.Thread(target=self.read_packets)
        dumper.daemon = True
        reader.daemon = True
	dumper.start()
        reader.start()
	dumper.join()
        reader.join()

if __name__ == '__main__':
    try:
        port = int(sys.argv[1])
    except Exception:
        logging.warning('Port should be specified')
        sys.exit(1)
    sender = pyZabbixSender(server="zabbix.dev.ath", port=10051)
    metrics=threading.Thread(target=Metrics.serve)
    metrics.daemon = True
    metrics.start()
    server = ProxyServer()
    server.listen_requests()



    
