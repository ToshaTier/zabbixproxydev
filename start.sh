#!/bin/bash
cd /home/athuser/zabbixProxyDev
(nohup python ./zabbix_server_new.py 31992 1>zabbix_server.log 2>&1)&

